#!/usr/bin/env python3
"""Run the eval suite. This is the part that costs money — one agent per case.

    python3 harness/run.py                     # whole suite, skill from config.json
    python3 harness/run.py --split train
    python3 harness/run.py --cases my-case
    python3 harness/run.py --skill-dir /tmp/candidate --label cand-1

Each case gets a throwaway sandbox with the skill installed as a project skill. Nothing is
graded here beyond collecting artifacts — grading is separate and free, so a change to the
checks never means paying for the agent runs again.
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
TRIGGER_TOOLS = ["Skill", "Read", "Glob", "Grep"]


def resolve_skill(cfg: dict, override: str | None) -> Path:
    raw = override or cfg.get("skill_dir")
    if not raw:
        raise SystemExit("error: config.json needs skill_dir (path to the skill under test)")
    p = Path(raw)
    if not p.is_absolute():
        p = (ROOT / p).resolve()
    if not (p / "SKILL.md").exists():
        raise SystemExit(f"error: no SKILL.md in {p}")
    return p


def run_task_case(case: dict, run_dir: Path, skill_dir: Path, cfg: dict) -> dict:
    out_dir = run_dir / case["id"]
    sandbox = C.build_sandbox(case, out_dir / "sandbox")
    agent.install_skill(skill_dir, sandbox)
    before = C.snapshot(sandbox)

    prompt = case["prompt"]
    if case.get("invoke", "explicit") == "explicit":
        prompt = f"Use the {cfg['target_skill']} skill. {prompt}"

    t0 = time.time()
    meta = agent.run_agent(sandbox, prompt, out_dir,
                           model=cfg.get("model", "opus"),
                           max_usd=cfg.get("max_usd_per_case", 2.0),
                           timeout=cfg.get("timeout_seconds", 1800),
                           skill_name=cfg["target_skill"])
    artifacts = C.collect(case, sandbox, before, meta, out_dir)
    raw = {"case": case["id"], "kind": "task", "prompt": prompt,
           "elapsed_s": round(time.time() - t0, 1),
           "meta": {k: v for k, v in meta.items() if k != "tool_calls"},
           "tool_calls": meta.get("tool_calls", [])[:400],
           "artifacts": artifacts}
    (out_dir / "raw.json").write_text(json.dumps(raw, indent=2), encoding="utf-8")
    shutil.rmtree(sandbox, ignore_errors=True)
    print(f"  [{case['id']}] {len(artifacts['files_created'])} created · "
          f"{raw['elapsed_s']}s · ${meta.get('cost_usd') or 0:.2f}", flush=True)
    return raw


def run_trigger_case(case: dict, run_dir: Path, skill_dir: Path, cfg: dict) -> dict:
    """Probe the description field: does the skill fire when it should, and stay quiet
    otherwise. Write/Edit/Bash are withheld so each probe stops soon after the routing
    decision, which is the only thing being measured."""
    out_dir = run_dir / case["id"]

    def one(i: int, probe: dict) -> dict:
        pdir = out_dir / f"probe-{i:02d}"
        sandbox = C.build_sandbox(case, pdir / "sandbox")
        agent.install_skill(skill_dir, sandbox)
        meta = agent.run_agent(sandbox, probe["prompt"], pdir,
                               model=cfg.get("model", "opus"),
                               max_usd=cfg.get("max_usd_per_probe", 0.5),
                               timeout=cfg.get("probe_timeout_seconds", 420),
                               tools=TRIGGER_TOOLS, skill_name=cfg["target_skill"])
        shutil.rmtree(sandbox, ignore_errors=True)
        return {"prompt": probe["prompt"], "should_fire": probe["should_fire"],
                "fired": bool(meta.get("triggered")), "cost_usd": meta.get("cost_usd")}

    with ThreadPoolExecutor(max_workers=cfg.get("probe_concurrency", 4)) as ex:
        results = list(ex.map(lambda t: one(*t), enumerate(case["probes"])))

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
    ap.add_argument("--skill-dir", default=None)
    ap.add_argument("--label", default="baseline")
    ap.add_argument("--run-dir", default=None)
    ap.add_argument("--model", default=None)
    ap.add_argument("--concurrency", type=int, default=None)
    ap.add_argument("--no-grade", action="store_true")
    args = ap.parse_args()

    cfg = C.load_config(ROOT)
    if args.model:
        cfg["model"] = args.model
    if args.concurrency:
        cfg["concurrency"] = args.concurrency

    skill_dir = resolve_skill(cfg, args.skill_dir)
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
        "target_skill": cfg["target_skill"], "model": cfg.get("model", "opus"),
        "started": time.strftime("%Y-%m-%d %H:%M:%S"),
        "cases": [c["id"] for c in selected],
    }, indent=2), encoding="utf-8")

    print(f"run {run_id} · skill {skill_dir.name} · model {cfg.get('model', 'opus')} · "
          f"{len(selected)} case(s)")

    def dispatch(case: dict) -> dict:
        fn = run_trigger_case if case.get("kind") == "trigger" else run_task_case
        try:
            return fn(case, run_dir, skill_dir, cfg)
        except Exception as exc:      # one crashed case must not lose the rest of the suite
            print(f"  [{case['id']}] HARNESS ERROR {exc}", flush=True)
            return {"case": case["id"], "error": str(exc)}

    with ThreadPoolExecutor(max_workers=cfg.get("concurrency", 3)) as ex:
        list(ex.map(dispatch, selected))

    print(f"\nartifacts: {run_dir}")
    if not args.no_grade:
        import grade
        return grade.grade_run(run_dir, cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
