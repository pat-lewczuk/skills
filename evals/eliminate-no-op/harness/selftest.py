#!/usr/bin/env python3
"""Validate the graders against synthetic agent output. No API calls, no cost.

Four synthetic auditors are graded against the real cases:

  perfect  — the labels, rendered as a compliant report and a faithful rewrite
  butcher  — cuts everything, including every trap
  lazy     — finds nothing, keeps everything
  vandal   — rewrites the target in place

If the graders are working, they rank these four in that order and fire the right
violations. Run this after touching anything in evallib/.

    python3 harness/selftest.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from evallib import cases as C, metrics as M  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FAILURES: list = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  pass  {name}")
    else:
        print(f"  FAIL  {name} {detail}")
        FAILURES.append(name)


def _lt(value, bound: float) -> bool:
    """`value < bound`, treating an absent metric as a failure rather than as zero."""
    return value is not None and value < bound


def original_lines(case: dict) -> list:
    target = Path(case["dir"]) / "workspace" / case["target"]
    return target.read_text(encoding="utf-8").splitlines()


def render_report(case: dict, labels: list, mode: str) -> str:
    """Build a template-compliant report expressing one of the synthetic strategies."""
    lines = original_lines(case)
    rows, cut_block, kept_rows = [], [], []
    for lab in labels:
        truth = lab["truth"]
        if mode == "perfect":
            verdict = truth
        elif mode == "butcher":
            verdict = "CUT"
        else:  # lazy
            verdict = "KEEP"
        code = (lab.get("codes") or ["N1"])[0]
        span = (f"{lab.get('line_start', lab['line'])}-{lab.get('line_end', lab['line'])}"
                if lab.get("line_end", lab["line"]) != lab["line"] else str(lab["line"]))
        text = lab.get("text", "")[:110].replace("|", "/")
        if verdict == "KEEP":
            kept_rows.append(f"| {span} | {code} | keeps a project-specific fact |")
            continue
        rows.append(f"| {span} | {verdict} | {code} | {text} | synthetic |")
        if verdict == "CUT":
            i = lab["line"] - 1
            raw = lines[i].strip() if 0 <= i < len(lines) else text
            cut_block.append(f"> **L{lab['line']}** — {raw}")

    before = len(lines)
    return "\n".join([
        f"# No-op audit: {case['target']}", "",
        "**Audited:** 2026-07-26 · **Mode:** full",
        "**Also read for cross-file duplication:** CLAUDE.md, packages/api/AGENTS.md", "",
        "## Summary", "",
        "| | Before | After | Δ |", "|---|---|---|---|",
        f"| Directives | {len(labels)} | {len(kept_rows)} | -{len(rows)} |",
        f"| Lines | {before} | {before - len(rows)} | -{len(rows)} |",
        "| Est. tokens | 1229 | 620 | -49% |",
        "| Signal density | 0.55 | 0.95 | +40pp |", "",
        "Synthetic report for grader self-test. Signal density was moderate; the dominant "
        "waste pattern is generic best-practice prose. Mentions dev-setup and "
        "docs/architecture, evidence-limited handling, unverified references, the "
        "description field is always in context on every turn, celery, CLAUDE.md, "
        "packages/api/AGENTS.md, and recommends a routing structure with per-domain "
        "references loaded on demand.", "",
        "## Verdict breakdown", "", "| Verdict | Count | Est. tokens |", "|---|---|---|",
        f"| KEEP | {len(kept_rows)} | 400 |", f"| CUT | {len(rows)} | 600 |", "",
        "## Findings", "",
        "| Line | Verdict | Code | Directive (abbreviated) | Rationale |",
        "|---|---|---|---|---|",
        *rows, "",
        "## Cut lines, verbatim", "", *cut_block, "",
        "## Kept despite looking generic", "", "| Line | Code | Why it stays |",
        "|---|---|---|", *kept_rows, "",
        "## Open questions", "", "- What is the actual file-size threshold?", "",
        "## Observations", "", "- Synthetic.", "",
        "## Proposed rewrite", "", f"Written to `{case['target']}.rewrite.md`.", "",
    ])


def render_rewrite(case: dict, labels: list, mode: str) -> str:
    """Subtract the lines this strategy removes; everything unlabelled survives.

    Keeping unlabelled lines matters: several cases label only a sample of a dense body,
    and a rewrite that dropped the rest would misreport the token reduction.
    """
    lines = original_lines(case)
    drop = set()
    for lab in labels:
        leaves = lab["truth"] in ("CUT", "MERGE", "MOVE")
        if mode == "butcher" or (mode == "perfect" and leaves):
            a = lab.get("line_start", lab["line"])
            b = lab.get("line_end", lab["line"])
            drop.update(range(a, b + 1))
    out = [ln for i, ln in enumerate(lines, start=1) if i not in drop]
    for noun in case.get("expect", {}).get("must_keep_nouns", []):
        if noun not in "\n".join(out):
            out.append(f"- {noun}")
    return "\n".join(out) + "\n"


def synth(case: dict, labels: list, mode: str) -> dict:
    original = "\n".join(original_lines(case)) + "\n"
    report = render_report(case, labels, "lazy" if mode in ("lazy", "vandal") else mode)
    rewrite = render_rewrite(case, labels, mode)
    return {
        "report": report, "report_from_file": True,
        "report_path": "no-op-report.md",
        "rewrite": rewrite,
        "rewrite_path": f"{Path(case['target']).with_suffix('')}.rewrite.md",
        "rewrite_path_ok": True,
        "original": original,
        # the vandal applied its edit straight to the target instead of writing beside it
        "original_after": (render_rewrite(case, labels, "perfect") if mode == "vandal"
                           else original),
        "files_created": [], "files_modified": [],
        "triggered": True, "read_taxonomy": True, "ran_analyze": True,
    }


def emit_run(mode: str) -> Path:
    """Write a synthetic run directory so grade/improve/loop can be exercised for free."""
    import shutil
    run_dir = ROOT / "runs" / f"selftest-{mode}"
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)
    skill = ROOT.parent.parent / "skills" / "eliminate-no-op"
    shutil.copytree(skill, run_dir / "skill-snapshot", ignore=C.IGNORE)

    ids = []
    for case in C.load_cases(ROOT):
        ids.append(case["id"])
        out = run_dir / case["id"]
        out.mkdir(parents=True)
        if case.get("kind") == "trigger":
            probes = [{"prompt": p["prompt"], "should_fire": p["should_fire"],
                       "fired": p["should_fire"] if mode == "perfect" else True,
                       "cost_usd": 0.0} for p in case["probes"]]
            raw = {"case": case["id"], "kind": "trigger", "probes": probes}
        else:
            labels = C.load_labels(case)
            raw = {"case": case["id"], "kind": "audit", "prompt": "synthetic",
                   "elapsed_s": 0.0, "meta": {"cost_usd": 0.0, "triggered": True},
                   "tool_calls": [], "artifacts": synth(case, labels, mode)}
        (out / "raw.json").write_text(json.dumps(raw, indent=2), encoding="utf-8")

    (run_dir / "run.json").write_text(json.dumps({
        "run_id": run_dir.name, "label": f"selftest-{mode}", "skill_dir": str(skill),
        "model": "none", "started": "synthetic", "cases": ids}, indent=2), encoding="utf-8")
    print(f"wrote synthetic run: {run_dir}")
    return run_dir


def main() -> int:
    if len(sys.argv) > 2 and sys.argv[1] == "--emit-run":
        emit_run(sys.argv[2])
        return 0

    all_cases = C.load_cases(ROOT)
    audit = [c for c in all_cases if c.get("kind", "audit") == "audit"]
    print(f"cases discovered: {[c['id'] for c in all_cases]}\n")

    for case in audit:
        labels = C.load_labels(case)
        print(f"{case['id']} ({len(labels)} labels)")
        if not labels:
            FAILURES.append(f"{case['id']}: no labels")
            print("  FAIL  no labels")
            continue

        scores = {m: M.score_case(case, labels, synth(case, labels, m))
                  for m in ("perfect", "butcher", "lazy", "vandal")}
        p, b, lz, v = (scores[k] for k in ("perfect", "butcher", "lazy", "vandal"))

        check(f"{case['id']}: perfect beats lazy", p["score"] > lz["score"],
              f"{p['score']} vs {lz['score']}")
        check(f"{case['id']}: perfect beats butcher", p["score"] > b["score"],
              f"{p['score']} vs {b['score']}")
        check(f"{case['id']}: perfect safety is 1.0", p["metrics"]["safety"] == 1.0,
              str(p["metrics"]["safety"]))
        check(f"{case['id']}: perfect recall >= 0.95", (p["metrics"]["recall"] or 0) >= 0.95,
              str(p["metrics"]["recall"]))
        check(f"{case['id']}: perfect preservation is 1.0",
              p["metrics"]["preservation"] in (None, 1.0), str(p["metrics"]["preservation"]))
        check(f"{case['id']}: perfect report has every section",
              not p["details"]["missing_sections"], str(p["details"]["missing_sections"]))
        check(f"{case['id']}: perfect meets must_mention",
              all(v_ == 1.0 for k, v_ in p["details"]["compliance_checks"].items()
                  if k.startswith("mentions:")),
              str(p["details"]["compliance_checks"]))
        traps = [x for x in labels if x.get("severity") == "trap"]
        if traps:
            check(f"{case['id']}: butcher flagged for cutting load-bearing lines",
                  "cut_load_bearing_line" in b["violations"], str(b["violations"]))
            check(f"{case['id']}: butcher safety near zero", _lt(b["metrics"]["safety"], 0.2),
                  str(b["metrics"]["safety"]))
        check(f"{case['id']}: lazy recall near zero", _lt(lz["metrics"]["recall"], 0.35),
              str(lz["metrics"]["recall"]))
        check(f"{case['id']}: in-place edit scores zero", v["score"] == 0.0
              and "in_place_edit" in v["violations"], f"{v['score']} {v['violations']}")
        print(f"  scores: perfect {p['score']} · lazy {lz['score']} · "
              f"butcher {b['score']} · vandal {v['score']}")
        print(f"  perfect metrics: {p['metrics']}")
        print(f"  perfect reduction: {p['details']['reduction_pct']}% "
              f"(band {case['expect'].get('reduction_pct')}, "
              f"calibration {p['metrics']['calibration']})\n")

    trig = [c for c in all_cases if c.get("kind") == "trigger"]
    for case in trig:
        good = [{"prompt": p["prompt"], "should_fire": p["should_fire"], "fired": p["should_fire"]}
                for p in case["probes"]]
        bad = [{"prompt": p["prompt"], "should_fire": p["should_fire"], "fired": True}
               for p in case["probes"]]
        print(f"{case['id']}")
        check(f"{case['id']}: perfect trigger scores 1.0",
              M.score_trigger_case(case, good)["score"] == 1.0)
        check(f"{case['id']}: always-fires is penalised",
              M.score_trigger_case(case, bad)["score"] < 0.75)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} grader check(s) failed:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("all grader checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
