#!/usr/bin/env python3
"""Create an eval suite for a skill: config, a copy of the harness, and case skeletons.

    python3 scaffold.py --skill eliminate-no-op \
        --case bloated:train --case healthy:train --case unseen:holdout \
        --case triggers:train:trigger

    python3 scaffold.py --skill /path/to/skill --into /path/to/evals/my-skill

The harness is *copied* into the suite rather than referenced, so the eval keeps working
after the evaluate-skill skill is uninstalled or changed. Cases are skeletons — the checks
are the part that has to be written by someone who knows what the skill is for.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_WEIGHTS = {"safety": 0.35, "correctness": 0.30, "quality": 0.20, "compliance": 0.15}

SKELETON = {
    "task": {
        "kind": "task",
        "split": "train",
        "invoke": "explicit",
        "prompt": "TODO: what the user asks for, in their words.",
        "description": "TODO: what this case is here to catch. One sentence, specific.",
        "checks": [
            {"id": "TODO-produced-output", "type": "file_exists", "path": "TODO.md",
             "metric": "compliance", "weight": 1,
             "why": "TODO: why this matters"},
            {"id": "TODO-did-no-damage", "type": "file_unchanged", "path": "TODO-input.md",
             "metric": "safety", "weight": 3, "gate": True,
             "why": "TODO: the thing this skill must never do"},
        ],
        "rubric": [
            {"id": "TODO-quality", "metric": "quality", "weight": 1,
             "criterion": "TODO: one thing a regex cannot check, stated so two readers "
                          "would grade it the same way."}
        ],
    },
    "trigger": {
        "kind": "trigger",
        "split": "train",
        "description": "Does the description field fire on the right prompts and stay quiet "
                       "on adjacent ones.",
        "metric": "compliance",
        "probes": [
            {"prompt": "TODO: a prompt that should invoke the skill", "should_fire": True},
            {"prompt": "TODO: another, worded differently", "should_fire": True},
            {"prompt": "TODO: adjacent work the skill must NOT hijack", "should_fire": False},
        ],
    },
}

README = """# Eval suite: `{skill}`

Built by the `evaluate-skill` skill. The harness is a copy — this suite keeps working on its
own.

```bash
python3 harness/selftest.py       # validate the instrument, free, no API calls
python3 harness/run.py            # run the suite (costs money: one agent per case)
python3 harness/grade.py runs/<id>            # re-grade for free after editing checks
python3 harness/report_html.py    # -> results.html
./harness/screenshot.sh           # -> docs/results-{{light,dark}}.png
python3 harness/loop.py --iterations 2        # measure, revise, re-measure
```

## Layout

```
config.json          weights, model, thresholds, path to the skill under test
cases/<id>/case.json prompt + checks + rubric for one case
cases/<id>/workspace the files the sandbox starts with
runs/                one directory per run (gitignored)
scoreboard.md        every candidate the loop has judged
```

## Before trusting a number

Run `harness/selftest.py`. It scores two synthetic runs against every case: one that did
nothing, which must score near zero, and one built to satisfy every check, which must score
near one. A case that cannot separate those two is not measuring anything.
"""

GITIGNORE = "runs/*\n!runs/.gitkeep\n"


def find_skill(name: str, start: Path) -> Path:
    p = Path(name)
    if (p / "SKILL.md").exists():
        return p.resolve()
    roots = [start] + list(start.parents)[:4]
    for root in roots:
        for rel in (f".claude/skills/{name}", f"skills/{name}", name):
            cand = root / rel
            if (cand / "SKILL.md").exists():
                return cand.resolve()
    raise SystemExit(
        f"error: no skill named {name!r} found. Looked for .claude/skills/{name}/SKILL.md "
        f"and skills/{name}/SKILL.md upward from {start}. Pass a path instead.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skill", required=True, help="skill name or directory")
    ap.add_argument("--into", default=None, help="where to create the suite")
    ap.add_argument("--case", action="append", default=[],
                    help="name[:split[:kind]] — repeatable")
    ap.add_argument("--metrics", default=None,
                    help="comma-separated metric names (default: safety,correctness,"
                         "quality,compliance)")
    ap.add_argument("--model", default="opus")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    cwd = Path.cwd()
    skill_dir = find_skill(args.skill, cwd)
    name = skill_dir.name

    root = Path(args.into) if args.into else (cwd / "evals" / name)
    if root.exists() and any(root.iterdir()) and not args.force:
        raise SystemExit(f"error: {root} already exists and is not empty (use --force)")
    root.mkdir(parents=True, exist_ok=True)

    shutil.copytree(HERE / "harness", root / "harness", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for sh in (root / "harness").glob("*.sh"):
        sh.chmod(0o755)

    weights = DEFAULT_WEIGHTS
    if args.metrics:
        names = [m.strip() for m in args.metrics.split(",") if m.strip()]
        weights = {m: round(1 / len(names), 4) for m in names}

    skill_md = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    try:
        rel_skill = str(Path(skill_dir).relative_to(root.parent.parent))
        rel_skill = str(Path("../..") / rel_skill)
    except ValueError:
        rel_skill = str(skill_dir)

    (root / "config.json").write_text(json.dumps({
        "target_skill": name,
        "skill_dir": rel_skill,
        "model": args.model,
        "judge_model": args.model,
        "concurrency": 3,
        "probe_concurrency": 4,
        "max_usd_per_case": 2.0,
        "max_usd_per_probe": 0.5,
        "timeout_seconds": 1800,
        "probe_timeout_seconds": 420,
        "rubric_enabled": True,
        "weights": weights,
        "skill_token_baseline": max(1, round(len(skill_md) / 4)),
        "smoke_test": "",
        "loop": {"accept_min_train_gain": 0.01, "accept_max_holdout_regression": 0.02,
                 "max_iterations": 3},
    }, indent=2) + "\n", encoding="utf-8")

    (root / "README.md").write_text(README.format(skill=name), encoding="utf-8")
    (root / ".gitignore").write_text(GITIGNORE, encoding="utf-8")
    (root / "runs").mkdir(exist_ok=True)
    (root / "runs" / ".gitkeep").touch()
    (root / "cases").mkdir(exist_ok=True)

    made = []
    for spec in args.case:
        parts = spec.split(":")
        cid = parts[0]
        split = parts[1] if len(parts) > 1 and parts[1] else "train"
        kind = parts[2] if len(parts) > 2 and parts[2] else "task"
        cdir = root / "cases" / cid
        if cdir.exists() and not args.force:
            print(f"  skip {cid} (exists)")
            continue
        (cdir / "workspace").mkdir(parents=True, exist_ok=True)
        (cdir / "workspace" / ".gitkeep").touch()
        body = json.loads(json.dumps(SKELETON[kind]))
        body["id"] = cid
        body["split"] = split
        (cdir / "case.json").write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
        made.append(f"{cid} ({split}, {kind})")

    print(f"created {root}")
    print(f"  skill under test: {skill_dir}")
    print(f"  metrics: {', '.join(weights)}")
    for m in made:
        print(f"  case: {m}")
    print("\nnext: fill in each case.json and its workspace/, then run "
          "`python3 harness/selftest.py`")
    return 0


if __name__ == "__main__":
    sys.exit(main())
