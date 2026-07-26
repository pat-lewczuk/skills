#!/usr/bin/env python3
"""Model-judged rewrite fidelity, for the part the deterministic graders cannot see.

The skill promises a purely subtractive edit: nothing invented, nothing silently
reworded into a different rule. Word-overlap heuristics catch the crude version of that
failure; a paraphrase that quietly widens "do not import pg in packages/api" into "do
not import pg" needs a reader.

Writes `judge.json` into the run directory. Re-run `grade.py` afterwards and the
fidelity figure folds into the preservation metric.

    python3 harness/judge.py [runs/<run-id>]
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from evallib import agent  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

SCHEMA = {
    "type": "object",
    "properties": {
        "invented_rules": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"text": {"type": "string"}, "why": {"type": "string"}},
                "required": ["text", "why"],
            },
        },
        "lost_information": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"original": {"type": "string"}, "why": {"type": "string"}},
                "required": ["original", "why"],
            },
        },
        "widened_or_narrowed": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"before": {"type": "string"}, "after": {"type": "string"},
                               "why": {"type": "string"}},
                "required": ["before", "after", "why"],
            },
        },
        "fidelity": {"type": "number", "minimum": 0, "maximum": 1},
        "summary": {"type": "string"},
    },
    "required": ["invented_rules", "lost_information", "widened_or_narrowed", "fidelity",
                 "summary"],
}

PROMPT = """You are checking one property of a proposed edit: that it is purely subtractive.

ORIGINAL instruction file:
<original>
{original}
</original>

PROPOSED REWRITE:
<rewrite>
{rewrite}
</rewrite>

The report that accompanies the rewrite, which lists every directive it deliberately removed
and why:
<report>
{report}
</report>

A subtractive edit may delete a directive, compress its wording, or merge duplicates. It may
NOT introduce a rule that was not there, and it may NOT quietly change what a *surviving* rule
requires — including by dropping a qualifier, a path, a threshold, or a scope condition.

Report:
- invented_rules: directives in the rewrite that impose something the original did not.
  Reformatting, shortening and merging are not inventions.
- lost_information: information that disappeared **silently** — a command, path, number,
  condition or recovery step that is gone from the rewrite and is NOT accounted for in the
  report. A directive the report lists as CUT, MERGE or MOVE is a declared decision that is
  judged elsewhere; its removal is never a loss for your purposes, however concrete it was.
  What you are looking for is the qualifier that fell off a rule that survived, or the second
  half of a merged pair that nobody mentioned.
- widened_or_narrowed: surviving rules whose scope or strength changed. A vague rule rewritten
  into a specific, checkable one counts here — say so and note whether the new version is
  narrower or broader than the old.
- fidelity: 1.0 for a clean subtractive edit, 0.0 for one that cannot be trusted. Charge
  invented rules hardest, then silent losses, then scope changes. Declared cuts cost nothing.

Judge only these properties. Whether a given cut was *wise* is decided elsewhere and is not
your question."""


def judge_case(raw_path: Path, model: str) -> dict | None:
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    if raw.get("kind") == "trigger":
        return None
    art = raw.get("artifacts") or {}
    if not (art.get("rewrite") or "").strip():
        return {"case": raw["case"], "fidelity": None, "skipped": "no rewrite"}
    result = agent.structured_call(
        PROMPT.format(original=art["original"][:24000], rewrite=art["rewrite"][:24000],
                      report=(art.get("report") or "(no report produced)")[:24000]),
        SCHEMA, model=model, cwd=ROOT)
    if result is None:
        return {"case": raw["case"], "fidelity": None, "skipped": "judge call failed"}
    result["case"] = raw["case"]
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", nargs="?", default=None)
    ap.add_argument("--model", default=None)
    args = ap.parse_args()

    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    model = args.model or cfg.get("judge_model", "opus")

    import grade
    run_dir = Path(args.run_dir).resolve() if args.run_dir else grade.newest_run(ROOT)
    if not run_dir:
        print("error: no run directory", file=sys.stderr)
        return 1

    raws = sorted(run_dir.glob("*/raw.json"))
    with ThreadPoolExecutor(max_workers=cfg.get("concurrency", 3)) as ex:
        results = [r for r in ex.map(lambda p: judge_case(p, model), raws) if r]

    (run_dir / "judge.json").write_text(json.dumps({"results": results}, indent=2),
                                        encoding="utf-8")
    for r in results:
        if r.get("skipped"):
            print(f"  [{r['case']}] skipped: {r['skipped']}")
        else:
            print(f"  [{r['case']}] fidelity {r['fidelity']} · "
                  f"invented {len(r['invented_rules'])} · lost {len(r['lost_information'])} · "
                  f"scope-changed {len(r['widened_or_narrowed'])}")
    print(f"\nwrote {run_dir / 'judge.json'} — re-run grade.py to fold it in")
    return 0


if __name__ == "__main__":
    sys.exit(main())
