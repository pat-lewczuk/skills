#!/usr/bin/env python3
"""Grade a run. Deterministic, re-runnable, free apart from the rubric.

    python3 harness/grade.py                    # newest run
    python3 harness/grade.py runs/<id>
    python3 harness/grade.py runs/<id> --rejudge   # re-run the rubric judge

The post-run sandbox is rebuilt from the artifacts `run.py` saved, so changing a check and
re-grading costs nothing. Rubric verdicts are cached in `rubric.json` and reused unless
`--rejudge` is passed.

Writes `scores.json` (machine-readable, consumed by improve.py and loop.py) and `report.md`.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from evallib import cases as C, checks as CH, metrics as M, rubric as RB  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def newest_run(root: Path) -> Path | None:
    runs = [p for p in (root / "runs").glob("*") if (p / "run.json").exists()]
    return max(runs, key=lambda p: p.stat().st_mtime) if runs else None


def skill_tokens(skill_dir: Path) -> dict:
    sm = skill_dir / "SKILL.md"
    text = sm.read_text(encoding="utf-8", errors="replace") if sm.exists() else ""
    desc = ""
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].splitlines():
                if line.startswith("description:"):
                    desc = line.split(":", 1)[1].strip()
    return {"skill_md_tokens": M.est_tokens(text), "description_tokens": M.est_tokens(desc)}


def _trigger_checks(case: dict, raw: dict) -> list:
    metric = case.get("metric", "compliance")
    out = []
    for i, p in enumerate(raw.get("probes", [])):
        ok = p["fired"] == p["should_fire"]
        want = "fire" in ("fire" if p["should_fire"] else "quiet")
        out.append({
            "id": f"probe-{i:02d}", "type": "skill_fired" if p["should_fire"] else
            "skill_not_fired", "metric": metric, "weight": float(case.get("probe_weight", 1)),
            "gate": False, "passed": ok,
            "detail": ("correct" if ok else
                       ("did not fire" if p["should_fire"] else "fired when it should not")),
            "why": f'prompt: "{p["prompt"][:110]}"' + ("" if want else ""),
        })
    return out


def grade_case(case: dict, case_dir: Path, cfg: dict, cached: dict,
               rejudge: bool) -> tuple:
    raw = json.loads((case_dir / "raw.json").read_text(encoding="utf-8"))

    if raw.get("kind") == "trigger":
        results = _trigger_checks(case, raw)
        return M.score_case(case, results, [], cfg.get("weights")), []

    artifacts = raw.get("artifacts", {})
    with tempfile.TemporaryDirectory() as tmp:
        sandbox = C.restore_sandbox(case, case_dir, Path(tmp) / "sandbox")
        ctx = CH.Context(sandbox, C.originals(case), {**raw.get("meta", {}),
                                                      "tool_calls": raw.get("tool_calls", [])},
                         artifacts.get("files_created", []),
                         artifacts.get("files_modified", []))
        results = [CH.run_check(spec, ctx) for spec in case.get("checks", [])]

        rubric_results = cached.get(case["id"]) if not rejudge else None
        if rubric_results is None and case.get("rubric") and cfg.get("rubric_enabled", True):
            files = {}
            for rel in artifacts.get("files_created", []) + artifacts.get("files_modified", []):
                p = sandbox / rel
                if p.is_file() and p.stat().st_size < 200_000:
                    try:
                        files[rel] = p.read_text(encoding="utf-8")
                    except UnicodeDecodeError:
                        continue
            rubric_results = RB.judge_case(case, artifacts, results, files,
                                           model=cfg.get("judge_model",
                                                         cfg.get("model", "opus")),
                                           cwd=ROOT)
        rubric_results = rubric_results or []

    scored = M.score_case(case, results, rubric_results, cfg.get("weights"))
    scored["cost_usd"] = (raw.get("meta") or {}).get("cost_usd")
    scored["elapsed_s"] = raw.get("elapsed_s")
    return scored, rubric_results


def grade_run(run_dir: Path, cfg: dict | None = None, rejudge: bool = False) -> int:
    cfg = cfg or C.load_config(ROOT)
    weights = cfg.get("weights") or M.DEFAULT_WEIGHTS
    cfg["weights"] = weights
    all_cases = {c["id"]: c for c in C.load_cases(ROOT)}

    cache_path = run_dir / "rubric.json"
    cached = (json.loads(cache_path.read_text(encoding="utf-8"))
              if cache_path.exists() and not rejudge else {})

    todo = [(all_cases[p.parent.name], p.parent)
            for p in sorted(run_dir.glob("*/raw.json")) if p.parent.name in all_cases]

    scored, fresh = [], {}
    with ThreadPoolExecutor(max_workers=cfg.get("concurrency", 3)) as ex:
        for s, rb in ex.map(lambda t: grade_case(t[0], t[1], cfg, cached, rejudge), todo):
            scored.append(s)
            if rb:
                fresh[s["case"]] = rb
    if fresh:
        cache_path.write_text(json.dumps({**cached, **fresh}, indent=2), encoding="utf-8")

    listed = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))["cases"]
    for cid in sorted(set(listed) - {s["case"] for s in scored}):
        case = all_cases.get(cid, {"id": cid})
        scored.append({"case": cid, "split": case.get("split", "train"),
                       "kind": case.get("kind", "task"), "score": 0.0, "metrics": {},
                       "gates_failed": ["case_did_not_run"], "failed_checks": [],
                       "weak_rubric": [], "detail": {}})

    tok = skill_tokens(run_dir / "skill-snapshot")
    summary = M.aggregate(scored, weights, tok["skill_md_tokens"],
                          cfg.get("skill_token_baseline") or tok["skill_md_tokens"])
    summary.update({"run_dir": str(run_dir), "skill_cost": tok,
                    "target_skill": cfg.get("target_skill", "?"),
                    "total_cost_usd": round(sum(s.get("cost_usd") or 0 for s in scored), 2)})

    payload = {"summary": summary, "weights": weights, "cases": scored}
    (run_dir / "scores.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (run_dir / "report.md").write_text(render(payload), encoding="utf-8")
    print("\n" + render(payload))
    return 0


def render(payload: dict) -> str:
    s = payload["summary"]
    keys = list(payload["weights"])
    lines = [f"# Eval report — {Path(s['run_dir']).name} · {s['target_skill']}", "",
             f"**Adjusted score {s['adjusted_score']}** "
             f"(raw {s['raw_score']} − context penalty {s['context_penalty']})  ",
             f"train {_d(s['train_score'])} · holdout {_d(s['holdout_score'])} · "
             f"{s['cases']} cases · ${s['total_cost_usd']}  ",
             f"SKILL.md {s['skill_cost']['skill_md_tokens']} tok "
             f"(baseline {s['skill_token_baseline']}), description "
             f"{s['skill_cost']['description_tokens']} tok always in context", "",
             "| Case | Split | Score | " + " | ".join(keys) + " |",
             "|---|---|---|" + "---|" * len(keys)]
    for c in sorted(payload["cases"], key=lambda c: (c["split"], c["case"])):
        cells = [("—" if c["metrics"].get(k) is None else f"{c['metrics'][k]:.2f}")
                 for k in keys]
        lines.append(f"| {c['case']} | {c['split']} | {c['score']:.2f} | "
                     + " | ".join(cells) + " |")

    lines += ["", "## Metric means", ""]
    lines += [f"- {k}: {_d(v)} (weight {payload['weights'][k]})"
              for k, v in s["metric_means"].items()]

    if s["gated"]:
        lines += ["", "## Gate failures — these zero their case", ""]
        for c in payload["cases"]:
            for g in c["gates_failed"]:
                lines.append(f"- **{c['case']}**: {g}")

    lines += ["", "## What failed", ""]
    any_fail = False
    for c in payload["cases"]:
        bits = [f"`{f['id']}` — {f['detail']}" for f in c["failed_checks"]]
        bits += [f"rubric `{r['id']}` {r['score']:.1f} — {r['reason'][:120]}"
                 for r in c["weak_rubric"]]
        if bits:
            any_fail = True
            lines.append(f"**{c['case']}**")
            lines += [f"- {b}" for b in bits]
            lines.append("")
    if not any_fail:
        lines.append("Nothing failed. If that stays true across runs, the cases are too easy "
                     "— add a harder one rather than declaring victory.")
    return "\n".join(lines) + "\n"


def _d(v) -> str:
    return "—" if v is None else f"{v}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", nargs="?", default=None)
    ap.add_argument("--rejudge", action="store_true")
    args = ap.parse_args()
    run_dir = Path(args.run_dir).resolve() if args.run_dir else newest_run(ROOT)
    if not run_dir or not run_dir.exists():
        print("error: no run directory found", file=sys.stderr)
        return 1
    return grade_run(run_dir, rejudge=args.rejudge)


if __name__ == "__main__":
    sys.exit(main())
