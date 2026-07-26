#!/usr/bin/env python3
"""Grade a run directory. Deterministic and re-runnable.

    python3 harness/grade.py                       # newest run
    python3 harness/grade.py runs/20260726-...     # a specific run

Writes `scores.json` (machine-readable, consumed by loop.py and improve.py) and
`report.md` (human-readable) into the run directory.

The aggregate carries a context-cost penalty: the skill under test is *about* context
economy, so a candidate that improves scores by appending 400 lines of new rules to
SKILL.md is not an improvement. Growth beyond the baseline is charged against the
score.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from evallib import cases as C, metrics as M  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
COST_PENALTY_RATE = 0.05   # score points charged per 100% growth over baseline


def newest_run(root: Path) -> Path | None:
    runs = [p for p in (root / "runs").glob("*") if (p / "run.json").exists()]
    return max(runs, key=lambda p: p.stat().st_mtime) if runs else None


def skill_cost(skill_dir: Path) -> dict:
    sm = skill_dir / "SKILL.md"
    text = sm.read_text(encoding="utf-8", errors="replace") if sm.exists() else ""
    desc = ""
    if text.startswith("---"):
        fm = text.split("---", 2)
        if len(fm) >= 3:
            for line in fm[1].splitlines():
                if line.startswith("description:"):
                    desc = line.split(":", 1)[1].strip()
    refs = sum(M.est_tokens(p.read_text(encoding="utf-8", errors="replace"))
               for p in (skill_dir / "references").glob("*.md")) \
        if (skill_dir / "references").exists() else 0
    return {"skill_md_tokens": M.est_tokens(text), "description_tokens": M.est_tokens(desc),
            "reference_tokens": refs, "always_loaded_tokens": M.est_tokens(desc)}


def grade_run(run_dir: Path, config: dict | None = None) -> int:
    cfg = config or (json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
                     if (ROOT / "config.json").exists() else {})
    all_cases = {c["id"]: c for c in C.load_cases(ROOT)}
    judged = {}
    if (run_dir / "judge.json").exists():
        for r in json.loads((run_dir / "judge.json").read_text(encoding="utf-8"))["results"]:
            judged[r["case"]] = r

    scored = []
    for raw_path in sorted(run_dir.glob("*/raw.json")):
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
        case = all_cases.get(raw["case"])
        if case is None:
            continue
        if raw.get("kind") == "trigger":
            s = M.score_trigger_case(case, raw.get("probes", []))
        else:
            artifacts = dict(raw["artifacts"])
            j = judged.get(raw["case"])
            if j and j.get("fidelity") is not None:
                artifacts["fidelity"] = j["fidelity"]
                artifacts["judge_notes"] = (
                    [f"judge: invented rule — {i['text'][:90]}" for i in j["invented_rules"]]
                    + [f"judge: lost — {i['original'][:90]}" for i in j["lost_information"]]
                    + [f"judge: scope changed — {i['after'][:90]}"
                       for i in j["widened_or_narrowed"]])
            s = M.score_case(case, C.load_labels(case), artifacts)
            s["cost_usd"] = (raw.get("meta") or {}).get("cost_usd")
            s["elapsed_s"] = raw.get("elapsed_s")
        scored.append(s)

    missing = sorted(set(json.loads((run_dir / "run.json").read_text())["cases"])
                     - {s["case"] for s in scored})
    for cid in missing:
        scored.append({"case": cid, "kind": all_cases.get(cid, {}).get("kind", "audit"),
                       "split": all_cases.get(cid, {}).get("split", "train"),
                       "score": 0.0, "metrics": {}, "violations": ["case_did_not_run"],
                       "notes": [], "details": {}})

    cost = skill_cost(run_dir / "skill-snapshot")
    baseline = cfg.get("skill_token_baseline") or cost["skill_md_tokens"]
    growth = max(0.0, cost["skill_md_tokens"] / max(1, baseline) - 1)
    penalty = round(COST_PENALTY_RATE * growth, 4)

    def mean(items: list):
        # None, not 0.0 — a split with no cases in this run has no score, and reporting
        # zero would make a train-only run look like a holdout collapse.
        return round(sum(i["score"] for i in items) / len(items), 4) if items else None

    train = [s for s in scored if s["split"] == "train"]
    holdout = [s for s in scored if s["split"] == "holdout"]
    overall = mean(scored)

    summary = {
        "run_dir": str(run_dir),
        "cases": len(scored),
        "raw_score": overall,
        "train_score": mean(train),
        "holdout_score": mean(holdout),
        "skill_cost": cost,
        "skill_token_baseline": baseline,
        "context_penalty": penalty,
        "adjusted_score": round(overall - penalty, 4),
        "critical_violations": sorted({v for s in scored for v in s["violations"]}),
        "total_cost_usd": round(sum(s.get("cost_usd") or 0 for s in scored), 2),
        "metric_means": _metric_means(scored),
    }
    payload = {"summary": summary, "cases": scored}
    (run_dir / "scores.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (run_dir / "report.md").write_text(render(payload), encoding="utf-8")
    print("\n" + render(payload))
    return 0


def _or_dash(v) -> str:
    return "—" if v is None else f"{v}"


def _metric_means(scored: list) -> dict:
    out = {}
    for key in M.WEIGHTS:
        vals = [s["metrics"].get(key) for s in scored if s["metrics"].get(key) is not None]
        out[key] = round(sum(vals) / len(vals), 4) if vals else None
    return out


def render(payload: dict) -> str:
    s = payload["summary"]
    lines = [f"# Eval report — {Path(s['run_dir']).name}", ""]
    lines += [
        f"**Adjusted score {s['adjusted_score']}** "
        f"(raw {s['raw_score']} − context penalty {s['context_penalty']})  ",
        f"train {_or_dash(s['train_score'])} · holdout {_or_dash(s['holdout_score'])} · "
        f"{s['cases']} cases · ${s['total_cost_usd']}  ",
        f"SKILL.md {s['skill_cost']['skill_md_tokens']} tok "
        f"(baseline {s['skill_token_baseline']}), description "
        f"{s['skill_cost']['description_tokens']} tok always in context",
        "",
        "| Case | Split | Score | Safety | Recall | Preserv | Compl | Code | Calib |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for c in sorted(payload["cases"], key=lambda c: (c["split"], c["case"])):
        m = c.get("metrics", {})
        def f(k):
            v = m.get(k)
            return "—" if v is None else f"{v:.2f}"
        if c["kind"] == "trigger":
            lines.append(f"| {c['case']} | {c['split']} | {c['score']:.2f} | "
                         f"fire {f('fire_rate')} | quiet {f('quiet_rate')} | — | — | — | — |")
        else:
            lines.append(f"| {c['case']} | {c['split']} | {c['score']:.2f} | {f('safety')} | "
                         f"{f('recall')} | {f('preservation')} | {f('compliance')} | "
                         f"{f('code_accuracy')} | {f('calibration')} |")
    lines += ["", "## Metric means", ""]
    lines += [f"- {k}: {v}" for k, v in s["metric_means"].items()]

    if s["critical_violations"]:
        lines += ["", "## Violations", ""]
        for c in payload["cases"]:
            if c["violations"]:
                lines.append(f"- **{c['case']}**: {', '.join(c['violations'])}")

    lines += ["", "## Failures worth reading", ""]
    for c in payload["cases"]:
        d = c.get("details", {})
        bits = []
        if d.get("false_cuts"):
            bits.append(f"cut load-bearing: {', '.join(map(str, d['false_cuts']))}")
        if d.get("missed_waste"):
            bits.append(f"missed no-ops: {', '.join(map(str, d['missed_waste']))}")
        if d.get("missing_nouns"):
            bits.append(f"dropped from rewrite: {d['missing_nouns']}")
        if d.get("missing_sections"):
            bits.append(f"report missing: {', '.join(d['missing_sections'])}")
        if d.get("added_content"):
            bits.append(f"invented content: {len(d['added_content'])} sentence(s)")
        if d.get("missed"):
            bits.append(f"skill did not fire: {len(d['missed'])} prompt(s)")
        if d.get("over_fired"):
            bits.append(f"skill over-fired: {len(d['over_fired'])} prompt(s)")
        if c.get("notes"):
            bits += c["notes"]
        if bits:
            lines.append(f"- **{c['case']}** — " + "; ".join(bits))
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", nargs="?", default=None)
    args = ap.parse_args()
    run_dir = Path(args.run_dir).resolve() if args.run_dir else newest_run(ROOT)
    if not run_dir or not run_dir.exists():
        print("error: no run directory found", file=sys.stderr)
        return 1
    return grade_run(run_dir)


if __name__ == "__main__":
    sys.exit(main())
