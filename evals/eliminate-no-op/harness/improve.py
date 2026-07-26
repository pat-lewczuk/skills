#!/usr/bin/env python3
"""Turn a graded run into a candidate skill revision.

Two steps. First build a failure digest from `scores.json`: every mis-verdicted directive
with the rationale the auditor gave for it, plus the compliance and process misses,
aggregated so systematic patterns are visible. Second, hand that digest to an optimiser
agent that may edit a *copy* of the skill — never the installed one.

    python3 harness/improve.py --run runs/<id> --candidate runs/<id>/candidate
    python3 harness/improve.py --run runs/<id> --digest-only

Only train-split cases reach the digest. The holdout exists to catch the case where the
optimiser has learned the four training files rather than the method.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from evallib import agent, cases as C, guard  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

OPTIMISER_PROMPT = """You maintain the `eliminate-no-op` skill in `{skill_rel}`. An eval suite
just ran it against several instruction files with known-correct verdicts. `{digest_rel}` is
the failure report.

Read the digest, then read the skill (`SKILL.md`, `references/taxonomy.md`,
`references/report-template.md`, `scripts/analyze.py`). Change the skill so the same
failures do not recur.

Rules for your edits:

1. Fix the method, never the instance. The digest names specific directives from specific
   fixture repos. Those exact files will never be audited again. If the digest shows six
   tool-enforced rules were missed, the fix is guidance on how to check tooling config —
   not a list of the rules that were missed. A patch containing a fixture's paths, ports,
   package names, or identifiers is rejected automatically, and so is a patch that quotes a
   fixture line.
2. This skill's own subject is context cost. `SKILL.md` must stay under {budget} characters
   ({budget_tokens} estimated tokens). If you need room, take it from the weakest existing
   prose — every addition should replace something, not stack on top of it. Detail belongs
   in `references/`, which loads on demand; `SKILL.md` says when to read it.
3. Prefer a mechanical fix to a prose fix. If `scripts/analyze.py` could have produced the
   evidence the auditor lacked, extend the script. It is stdlib-only and must keep working
   on any markdown or plain-text instruction file.
4. Each edit needs a reason in the digest — two or more failures, or one systematic one.
   Do not fix things the digest does not show. Do not restructure for taste.
5. `references/report-template.md` defines the report layout that readers and tooling
   depend on. You may change it, but renaming or dropping sections has a real cost.

When you are done, output a short changelog: for each edit, the file, what changed, and the
digest evidence behind it. Then state what you deliberately did not change and why."""


def build_digest(run_dir: Path, split: str = "train") -> str:
    payload = json.loads((run_dir / "scores.json").read_text(encoding="utf-8"))
    cases = {c["id"]: c for c in C.load_cases(ROOT)}
    picked = [c for c in payload["cases"] if c["split"] == split]
    s = payload["summary"]

    out = ["# Failure digest", "",
           f"Run `{Path(s['run_dir']).name}` · adjusted score **{s['adjusted_score']}** "
           f"(train {s['train_score']}, holdout {s['holdout_score']})", "",
           "Metric means across the suite:", ""]
    for k, v in s["metric_means"].items():
        out.append(f"- {k}: {v}")
    out += ["", "Weights: safety 0.35, recall 0.25, preservation 0.15, compliance 0.12, "
                "code_accuracy 0.08, calibration 0.05. `safety` measures directives that "
                "were load-bearing and got cut anyway; it is weighted highest on purpose.",
            ""]

    code_missed, code_wrong = Counter(), Counter()

    for c in sorted(picked, key=lambda c: c["score"]):
        case = cases.get(c["case"], {})
        out += [f"## {c['case']} — score {c['score']}", ""]
        if c["kind"] == "trigger":
            d = c["details"]
            out += [f"Skill fired on {c['metrics'].get('fire_rate')} of the prompts that "
                    f"should trigger it, and stayed quiet on "
                    f"{c['metrics'].get('quiet_rate')} of the prompts that should not.", ""]
            for p in d.get("missed", []):
                out.append(f"- did not fire: \"{p}\"")
            for p in d.get("over_fired", []):
                out.append(f"- fired when it should not have: \"{p}\"")
            out += ["", "The `description` field in the frontmatter is the only part of the "
                        "skill in context when this decision is made.", ""]
            continue

        out += [f"Target: `{case.get('target')}` · metrics: "
                + ", ".join(f"{k} {v}" for k, v in c["metrics"].items() if v is not None), ""]
        if c["violations"]:
            out += [f"**Violations: {', '.join(c['violations'])}**", ""]

        d = c["details"]
        labels = {lab["id"]: lab for lab in C.load_labels(case)}
        by_id = {p["id"]: p for p in d.get("per_label", [])}

        rows = []
        for pid in d.get("false_cuts", []):
            p, lab = by_id.get(pid), labels.get(pid)
            if not p:
                continue
            rows.append(("CUT a load-bearing directive", p, lab))
            for code in (lab or {}).get("codes", []):
                code_missed[f"kept-as-{code}"] += 1
        for pid in d.get("missed_waste", []):
            p, lab = by_id.get(pid), labels.get(pid)
            if not p or pid in d.get("false_cuts", []):
                continue
            rows.append((f"should have been {p['truth']}, was {p['got']}", p, lab))
            for code in (lab or {}).get("codes", []):
                code_missed[f"missed-{code}"] += 1

        if rows:
            out += ["Mis-verdicted directives:", ""]
            for headline, p, lab in rows:
                out.append(f"- **{headline}** — \"{p['text']}\"")
                out.append(f"  - correct verdict `{p['truth']}` "
                           f"({', '.join(lab.get('codes', [])) if lab else '?'}); "
                           f"the audit said `{p['got']}`")
                if p.get("rationale"):
                    out.append(f"  - its stated rationale: \"{p['rationale']}\"")
            out.append("")

        wrong_code = [p for p in d.get("per_label", [])
                      if p.get("got_code") and p.get("expected_codes")
                      and p["got_code"] not in p["expected_codes"] and p["credit"] >= 0.5]
        if wrong_code:
            out += ["Right verdict, wrong code:", ""]
            for p in wrong_code[:8]:
                out.append(f"- \"{p['text'][:90]}\" — coded `{p['got_code']}`, "
                           f"should be `{'/'.join(p['expected_codes'])}`")
                code_wrong[f"{p['got_code']}->{'/'.join(p['expected_codes'])}"] += 1
            out.append("")

        checks = d.get("compliance_checks", {})
        failed = {k: v for k, v in checks.items() if v < 1.0}
        if failed:
            out += ["Process and report problems:", ""]
            for k, v in failed.items():
                out.append(f"- `{k}` scored {v}")
            out.append("")
        if d.get("missing_sections"):
            out.append(f"- report was missing these sections: "
                       f"{', '.join(d['missing_sections'])}\n")
        if d.get("missing_nouns"):
            out.append(f"- the rewrite dropped: {d['missing_nouns']}\n")
        if d.get("added_content"):
            out += ["- a word-overlap heuristic flagged these rewrite sentences as containing "
                    "material absent from the original; the edit is supposed to be "
                    "subtractive, but rewording a vague rule into its actionable form will "
                    "also trip this — check against the original before acting on it:"]
            for a in d["added_content"][:4]:
                out.append(f"  - \"{a}\"")
            out.append("")
        if d.get("reduction_pct") is not None:
            band = case.get("expect", {}).get("reduction_pct")
            out.append(f"- token reduction {d['reduction_pct']}% "
                       f"(defensible range for this file: {band})\n")
        out += [f"- ran `analyze.py`: {d.get('ran_analyze')} · "
                f"read `taxonomy.md`: {d.get('read_taxonomy')}", ""]
        for n in c.get("notes", []):
            out.append(f"- {n}")
        out.append("")

    if code_missed or code_wrong:
        out += ["## Patterns across cases", ""]
        for k, v in code_missed.most_common():
            out.append(f"- {k}: {v} occurrence(s)")
        for k, v in code_wrong.most_common():
            out.append(f"- miscoded {k}: {v} occurrence(s)")
        out.append("")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--candidate", default=None, help="where to write the candidate skill")
    ap.add_argument("--digest-only", action="store_true")
    ap.add_argument("--model", default=None)
    ap.add_argument("--split", default="train")
    args = ap.parse_args()

    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    run_dir = Path(args.run).resolve()
    digest = build_digest(run_dir, args.split)
    (run_dir / "digest.md").write_text(digest, encoding="utf-8")
    print(f"digest: {run_dir / 'digest.md'} ({len(digest)} chars)")
    if args.digest_only:
        print("\n" + digest)
        return 0

    cand_root = Path(args.candidate or (run_dir / "candidate")).resolve()
    if cand_root.exists():
        shutil.rmtree(cand_root)
    cand_root.mkdir(parents=True)
    baseline = run_dir / "skill-snapshot"
    skill_dir = cand_root / "eliminate-no-op"
    shutil.copytree(baseline, skill_dir, ignore=C.IGNORE)
    (cand_root / "digest.md").write_text(digest, encoding="utf-8")

    budget = int(len((baseline / "SKILL.md").read_text(encoding="utf-8")) * 1.15)
    prompt = OPTIMISER_PROMPT.format(
        skill_rel="eliminate-no-op", digest_rel="digest.md",
        budget=budget, budget_tokens=round(budget / 4))

    meta = agent.run_agent(cand_root, prompt, cand_root / "optimiser",
                           model=args.model or cfg.get("model", "opus"),
                           max_usd=cfg.get("max_usd_per_case", 2.5),
                           timeout=cfg.get("timeout_seconds", 1800))
    (cand_root / "changelog.md").write_text(meta.get("final_text", ""), encoding="utf-8")

    verdict = guard.check(baseline, skill_dir, ROOT / "cases",
                          [c["id"] for c in C.load_cases(ROOT)])
    (cand_root / "guard.json").write_text(json.dumps(verdict, indent=2), encoding="utf-8")

    grew = len((skill_dir / "SKILL.md").read_text(encoding="utf-8"))
    print(f"\ncandidate: {skill_dir}")
    print(f"SKILL.md {grew} chars (budget {budget})")
    print(f"guard: {'clean' if verdict['ok'] else str(len(verdict['violations'])) + ' violation(s)'}")
    for v in verdict["violations"][:10]:
        print(f"  {v['kind']}: {v['hit']} — {v['file']}: {v['line'][:80]}")
    return 0 if verdict["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
