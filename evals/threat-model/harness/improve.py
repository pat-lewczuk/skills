#!/usr/bin/env python3
"""Turn a graded run into a candidate skill revision.

    python3 harness/improve.py --run runs/<id> --digest-only
    python3 harness/improve.py --run runs/<id> --candidate runs/<id>/candidate

Two steps: build a failure digest from `scores.json` — every failed check with the reason
the case gives for caring about it, every weak rubric verdict with the judge's evidence,
aggregated so repeated failures are visible — then hand it to an optimiser that may edit a
*copy* of the skill, never the installed one.

Only train-split cases reach the digest. The holdout exists to catch a revision that learned
the training cases rather than the job.
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

OPTIMISER_PROMPT = """You maintain the `{skill}` skill, in `{skill_rel}/`. An eval suite just
ran it against cases with known-correct outcomes. `digest.md` is the failure report.

Read the digest, then read the skill in full. Change the skill so the same failures stop
happening.

Rules for your edits:

1. **Fix the method, never the instance.** The digest names specific files and values from
   specific test fixtures. Those exact fixtures will never be seen again. If four cases show
   the skill missing a class of problem, the fix is guidance on how to find that class — not
   a list of the four things it missed. A patch containing a fixture's paths, identifiers or
   values is rejected automatically, and so is one that quotes a fixture line.
2. **Every addition replaces something.** `SKILL.md` must stay under {budget} characters
   (~{budget_tokens} tokens). Instruction files are read by a model with finite attention:
   an extra paragraph costs the sharpness of everything around it. Take the room from the
   weakest existing prose. Detail belongs in `references/`, which loads on demand; `SKILL.md`
   says *when* to read it.
3. **Prefer a mechanical fix to a prose fix.** If a script in the skill could produce the
   evidence the run lacked, extend the script. Scripts are stdlib-only.
4. **Each edit needs evidence in the digest** — two or more failures, or one systematic one.
   Do not fix what the digest does not show. Do not restructure for taste.
5. If a failure looks like the *eval* being wrong rather than the skill, say so in your
   changelog instead of contorting the skill to satisfy it. That is a real outcome and the
   maintainer needs to hear it.

When you are done, output a short changelog: for each edit, the file, what changed, and the
digest evidence behind it. Then state what you deliberately did not change, and why."""


def build_digest(run_dir: Path, split: str = "train") -> str:
    payload = json.loads((run_dir / "scores.json").read_text(encoding="utf-8"))
    defs = {c["id"]: c for c in C.load_cases(ROOT)}
    picked = [c for c in payload["cases"] if c["split"] == split]
    s = payload["summary"]

    def num(v) -> str:
        return "not run" if v is None else f"{v}"

    out = ["# Failure digest", "",
           f"Skill `{s['target_skill']}` · run `{Path(s['run_dir']).name}` · "
           f"adjusted **{s['adjusted_score']}** "
           f"(train {num(s['train_score'])}, holdout {num(s['holdout_score'])})", "",
           "Metric means, with their weights:", ""]
    for k, v in s["metric_means"].items():
        out.append(f"- {k}: {v} (weight {payload['weights'].get(k)})")
    out.append("")

    repeated = Counter()
    for c in picked:
        for f in c["failed_checks"]:
            repeated[f["id"]] += 1
        for r in c["weak_rubric"]:
            repeated[f"rubric:{r['id']}"] += 1

    for c in sorted(picked, key=lambda c: c["score"]):
        case = defs.get(c["case"], {})
        out += [f"## {c['case']} — score {c['score']}", ""]
        if case.get("description"):
            out += [f"*What this case tests:* {case['description']}", ""]
        if c["kind"] == "trigger":
            wrong = [i for i in c["detail"].get("compliance", {}).get("items", [])
                     if i["score"] < 1]
            for i in wrong:
                out.append(f"- {i['detail']} — {i['why']}")
            out += ["", "Only the `description` field is in context when this decision is "
                        "made.", ""]
            continue

        if c["gates_failed"]:
            out += [f"**Gate failed — the case scores zero regardless of anything else: "
                    f"{', '.join(c['gates_failed'])}**", ""]
        if c["failed_checks"]:
            out += ["Failed checks:", ""]
            for f in c["failed_checks"]:
                out.append(f"- `{f['id']}` ({f['metric']}, weight {f['weight']}) — "
                           f"{f['detail']}")
                if f.get("why"):
                    out.append(f"  - why this matters: {f['why']}")
            out.append("")
        if c["weak_rubric"]:
            out += ["Weak on rubric:", ""]
            for r in c["weak_rubric"]:
                out.append(f"- `{r['id']}` scored {r['score']:.2f} — {r['criterion']}")
                out.append(f"  - judge said: {r['reason'][:300]}")
            out.append("")

    recurring = [k for k, v in repeated.items() if v > 1]
    if recurring:
        out += ["## Failing in more than one case", "",
                "These are the systematic ones. Fix these first — a fix that only helps one "
                "case is usually a fix aimed at the fixture.", ""]
        for k in sorted(recurring, key=lambda k: -repeated[k]):
            out.append(f"- `{k}`: {repeated[k]} cases")
        out.append("")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--candidate", default=None)
    ap.add_argument("--digest-only", action="store_true")
    ap.add_argument("--model", default=None)
    ap.add_argument("--split", default="train")
    args = ap.parse_args()

    cfg = C.load_config(ROOT)
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
    skill_dir = cand_root / cfg["target_skill"]
    shutil.copytree(baseline, skill_dir, ignore=C.IGNORE)
    (cand_root / "digest.md").write_text(digest, encoding="utf-8")

    budget = int(len((baseline / "SKILL.md").read_text(encoding="utf-8")) * 1.15)
    meta = agent.run_agent(
        cand_root,
        OPTIMISER_PROMPT.format(skill=cfg["target_skill"], skill_rel=cfg["target_skill"],
                                budget=budget, budget_tokens=round(budget / 4)),
        cand_root / "optimiser",
        model=args.model or cfg.get("model", "opus"),
        max_usd=cfg.get("max_usd_per_case", 2.0),
        timeout=cfg.get("timeout_seconds", 1800))
    (cand_root / "changelog.md").write_text(meta.get("final_text", ""), encoding="utf-8")

    verdict = guard.check(baseline, skill_dir, ROOT / "cases",
                          [c["id"] for c in C.load_cases(ROOT)])
    (cand_root / "guard.json").write_text(json.dumps(verdict, indent=2), encoding="utf-8")

    print(f"\ncandidate: {skill_dir}")
    print(f"SKILL.md {len((skill_dir / 'SKILL.md').read_text(encoding='utf-8'))} chars "
          f"(budget {budget})")
    print("guard: " + ("clean" if verdict["ok"]
                       else f"{len(verdict['violations'])} violation(s)"))
    for v in verdict["violations"][:10]:
        print(f"  {v['kind']}: {v['hit']} — {v['file']}: {v['line'][:80]}")
    return 0 if verdict["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
