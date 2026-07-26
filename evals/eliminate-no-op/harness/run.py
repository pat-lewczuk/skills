#!/usr/bin/env python3
"""Run the eliminate-no-op eval suite.

Each case gets a throwaway sandbox with the skill installed as a project skill, then
one headless Claude Code invocation. Nothing is graded here beyond collecting
artifacts — grading is a separate, re-runnable pass so grader changes never require
paying for the agent runs again.

    python3 harness/run.py                        # whole suite, current skill
    python3 harness/run.py --split train
    python3 harness/run.py --cases bloated-webapp lean-cli
    python3 harness/run.py --skill-dir /tmp/candidate/eliminate-no-op --label cand-3
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from evallib import agent, cases as C  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT.parent.parent
DEFAULT_SKILL = REPO / "skills" / "eliminate-no-op"
TRIGGER_TOOLS = ["Skill", "Read", "Glob", "Grep"]


def load_config(root: Path) -> dict:
    p = root / "config.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def run_audit_case(case: dict, run_dir: Path, skill_dir: Path, cfg: dict) -> dict:
    out_dir = run_dir / case["id"]
    sandbox = C.build_sandbox(case, out_dir / "sandbox")
    agent.install_skill(skill_dir, sandbox)
    before = C.snapshot(sandbox)

    prompt = case["prompt"]
    if case.get("invoke", "explicit") == "explicit":
        prompt = f"Use the eliminate-no-op skill. {prompt}"

    t0 = time.time()
    meta = agent.run_agent(sandbox, prompt, out_dir,
                           model=cfg.get("model", "opus"),
                           max_usd=cfg.get("max_usd_per_case", 2.0),
                           timeout=cfg.get("timeout_seconds", 1800))
    artifacts = C.collect_artifacts(case, sandbox, before, meta, out_dir)
    raw = {"case": case["id"], "kind": "audit", "prompt": prompt,
           "elapsed_s": round(time.time() - t0, 1),
           "meta": {k: v for k, v in meta.items() if k != "tool_calls"},
           "tool_calls": meta.get("tool_calls", [])[:400],
           "artifacts": artifacts}
    (out_dir / "raw.json").write_text(json.dumps(raw, indent=2), encoding="utf-8")
    if cfg.get("discard_sandboxes", True):
        shutil.rmtree(sandbox, ignore_errors=True)
    status = "ok" if artifacts["report"].strip() else "NO REPORT"
    # flush: a redirected suite run should show progress, not one buffered dump at the end
    print(f"  [{case['id']}] {status} · {raw['elapsed_s']}s · ${meta.get('cost_usd') or 0:.2f}",
          flush=True)
    return raw


def run_trigger_case(case: dict, run_dir: Path, skill_dir: Path, cfg: dict) -> dict:
    out_dir = run_dir / case["id"]
    probes = case["probes"]

    def one(i: int, probe: dict) -> dict:
        pdir = out_dir / f"probe-{i:02d}"
        sandbox = C.build_sandbox(case, pdir / "sandbox")
        agent.install_skill(skill_dir, sandbox)
        meta = agent.run_agent(sandbox, probe["prompt"], pdir,
                               model=cfg.get("model", "opus"),
                               max_usd=cfg.get("max_usd_per_probe", 0.5),
                               timeout=cfg.get("probe_timeout_seconds", 420),
                               tools=TRIGGER_TOOLS)
        shutil.rmtree(sandbox, ignore_errors=True)
        return {"prompt": probe["prompt"], "should_fire": probe["should_fire"],
                "fired": bool(meta.get("triggered")), "cost_usd": meta.get("cost_usd")}

    with ThreadPoolExecutor(max_workers=cfg.get("probe_concurrency", 4)) as ex:
        results = list(ex.map(lambda t: one(*t), enumerate(probes)))

    raw = {"case": case["id"], "kind": "trigger", "probes": results}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "raw.json").write_text(json.dumps(raw, indent=2), encoding="utf-8")
    hits = sum(1 for r in results if r["fired"] == r["should_fire"])
    print(f"  [{case['id']}] {hits}/{len(results)} probes correct", flush=True)
    return raw


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", nargs="*", default=None)
    ap.add_argument("--split", default=None, choices=["train", "holdout"])
    ap.add_argument("--skill-dir", default=str(DEFAULT_SKILL))
    ap.add_argument("--label", default="baseline")
    ap.add_argument("--run-dir", default=None, help="reuse/overwrite a specific run dir")
    ap.add_argument("--model", default=None)
    ap.add_argument("--concurrency", type=int, default=None)
    ap.add_argument("--no-grade", action="store_true")
    args = ap.parse_args()

    cfg = load_config(ROOT)
    if args.model:
        cfg["model"] = args.model
    if args.concurrency:
        cfg["concurrency"] = args.concurrency

    skill_dir = Path(args.skill_dir).resolve()
    if not (skill_dir / "SKILL.md").exists():
        print(f"error: no SKILL.md in {skill_dir}", file=sys.stderr)
        return 1

    selected = C.load_cases(ROOT, args.cases, args.split)
    if not selected:
        print("error: no cases matched", file=sys.stderr)
        return 1

    run_id = args.run_dir or f"{time.strftime('%Y%m%d-%H%M%S')}-{args.label}"
    run_dir = ROOT / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(skill_dir, run_dir / "skill-snapshot", dirs_exist_ok=True,
                    ignore=C.IGNORE)
    (run_dir / "run.json").write_text(json.dumps({
        "run_id": run_id, "label": args.label, "skill_dir": str(skill_dir),
        "model": cfg.get("model", "opus"), "started": time.strftime("%Y-%m-%d %H:%M:%S"),
        "cases": [c["id"] for c in selected],
    }, indent=2), encoding="utf-8")

    print(f"run {run_id} · skill {skill_dir} · model {cfg.get('model', 'opus')} · "
          f"{len(selected)} case(s)")

    def dispatch(case: dict) -> dict:
        fn = run_trigger_case if case.get("kind") == "trigger" else run_audit_case
        try:
            return fn(case, run_dir, skill_dir, cfg)
        except Exception as exc:  # a crashed case must not lose the rest of the suite
            print(f"  [{case['id']}] HARNESS ERROR {exc}")
            return {"case": case["id"], "kind": case.get("kind", "audit"), "error": str(exc)}

    with ThreadPoolExecutor(max_workers=cfg.get("concurrency", 3)) as ex:
        list(ex.map(dispatch, selected))

    print(f"\nartifacts: {run_dir}")
    if not args.no_grade:
        import grade
        return grade.grade_run(run_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
