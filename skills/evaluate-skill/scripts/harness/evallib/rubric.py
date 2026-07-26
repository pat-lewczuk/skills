"""Rubric judging — the half of the score a regex cannot settle.

Each rubric item is one criterion with its own metric bucket:

    {"id": "evidence", "metric": "quality", "weight": 2,
     "criterion": "Every removal names the specific evidence behind it — a config file,
                   a missing path, a duplicate location — rather than asserting it."}

All of a case's criteria are judged in one call, with the case brief and the produced
artifacts in the prompt. Two rules keep the judge honest, both learned the hard way:

- **Give it the ground truth it needs.** A judge that cannot see the case's intent invents
  its own standard and marks down correct work. Whatever the checks already establish is
  handed to it as fact.
- **Score the criterion, not the vibe.** Each item gets an independent 0–1 with a reason
  that quotes the artifact. An overall impression score is not requested and not used.
"""

from __future__ import annotations

from pathlib import Path

from . import agent

SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "score": {"type": "number", "minimum": 0, "maximum": 1},
                    "reason": {"type": "string"},
                    "evidence": {"type": "string"},
                },
                "required": ["id", "score", "reason"],
            },
        }
    },
    "required": ["items"],
}

PROMPT = """You are grading one run of an agent skill against fixed criteria.

WHAT THE SKILL WAS ASKED TO DO:
{prompt}

WHAT THIS CASE IS TESTING:
{description}

FACTS ALREADY ESTABLISHED by deterministic checks — treat these as settled, do not re-litigate:
{facts}

WHAT THE RUN PRODUCED:
{artifacts}

FINAL RESPONSE TO THE USER:
<response>
{output}
</response>

Score each criterion independently, 0.0 to 1.0:

{criteria}

Rules:
- Judge only the criterion in front of you. Do not average in a general impression, and do
  not penalise a criterion for a problem another criterion covers.
- Quote the artifact in `evidence`. A score without a quote is a guess.
- 1.0 means fully met, 0.5 partially, 0.0 not at all. Use the range — a wall of 0.9s carries
  no information.
- Work that is defensible but different from what you would have done is not a deduction.
  Only mark down what the criterion actually rules out."""


def judge_case(case: dict, artifacts: dict, check_results: list, sandbox_files: dict,
               model: str = "opus", cwd: Path | None = None) -> list:
    items = case.get("rubric") or []
    if not items:
        return []

    criteria = "\n".join(
        f"- id `{it['id']}`: {it['criterion']}" for it in items)
    facts = "\n".join(
        f"- {'PASS' if r['passed'] else 'FAIL'} {r['id']}: {r['detail']}"
        for r in check_results) or "- (none)"

    blobs = []
    for name, text in list(sandbox_files.items())[:12]:
        blobs.append(f"--- {name} ---\n{text[:6000]}")
    artifact_text = "\n\n".join(blobs) or "(the run produced no files)"

    result = agent.structured_call(
        PROMPT.format(prompt=case.get("prompt", ""),
                      description=case.get("description", "(not stated)"),
                      facts=facts, artifacts=artifact_text[:40000],
                      output=(artifacts.get("final_text") or "")[:8000],
                      criteria=criteria),
        SCHEMA, model=model, cwd=cwd)

    by_id = {it["id"]: it for it in items}
    out = []
    seen = set()
    for got in (result or {}).get("items", []):
        spec = by_id.get(got.get("id"))
        if not spec or spec["id"] in seen:
            continue
        seen.add(spec["id"])
        out.append({"id": spec["id"], "metric": spec.get("metric", "quality"),
                    "weight": float(spec.get("weight", 1)),
                    "score": max(0.0, min(1.0, float(got.get("score", 0)))),
                    "criterion": spec["criterion"],
                    "reason": got.get("reason", ""), "evidence": got.get("evidence", "")})
    # A judge that failed or skipped an item scores it 0 with the reason recorded, rather
    # than silently dropping the criterion and inflating the metric.
    for spec in items:
        if spec["id"] not in seen:
            out.append({"id": spec["id"], "metric": spec.get("metric", "quality"),
                        "weight": float(spec.get("weight", 1)), "score": 0.0,
                        "criterion": spec["criterion"],
                        "reason": "judge returned no verdict for this criterion",
                        "evidence": ""})
    return out
