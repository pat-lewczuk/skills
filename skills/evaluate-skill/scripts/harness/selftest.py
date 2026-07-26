#!/usr/bin/env python3
"""Check the instrument before trusting it. Costs nothing — no API calls.

Three passes:

1. **Lint** every case: check specs valid, metrics declared in config, both splits present,
   at least one gate, at least one must-never-happen check.
2. **Null run** — nothing produced, empty response. Must score near zero. If a case scores
   well on an agent that did nothing, its checks are not testing anything.
3. **Oracle run** — a synthetic sandbox built to satisfy every check the harness can
   construct an artifact for. Must score near one. A check that stays red against the oracle
   is either unsatisfiable or mis-specified, and is reported by name.

Run it after editing cases or checks. A suite that cannot separate the null from the oracle
cannot separate a good skill revision from a bad one.

    python3 harness/selftest.py
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from evallib import cases as C, checks as CH, metrics as M  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
NULL_MAX = 0.40
ORACLE_MIN = 0.80

# Check types that demand the skill actually did something. A case built only from the
# others — "did not touch X", "does not contain Y" — is passed by an agent that never ran.
PRODUCING = {"file_exists", "file_matches", "file_changed", "output_matches", "command",
             "json_valid", "file_size_ratio", "skill_fired", "tool_used"}


def sample_for(pattern: str) -> str | None:
    """A string that matches `pattern`, for simple patterns. None when unsure.

    Deliberately conservative: a wrong guess would make the oracle fail a check that is
    actually fine, which is worse than reporting the check as unverifiable.
    """
    depth = 0
    top_alts = [""]
    for ch in pattern:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "|" and depth == 0:
            top_alts.append("")
            continue
        top_alts[-1] += ch
    body = top_alts[0]

    out, i = [], 0
    while i < len(body):
        ch = body[i]
        if ch == "\\":
            nxt = body[i + 1] if i + 1 < len(body) else ""
            out.append({"d": "1", "w": "x", "s": " ", "b": "", "n": "\n",
                        ".": ".", "/": "/", "-": "-"}.get(nxt, nxt))
            i += 2
            continue
        if ch == "[":
            end = body.find("]", i)
            if end == -1:
                return None
            cls = body[i + 1:end].lstrip("^")
            if not cls or "^" in body[i + 1:i + 2]:
                return None
            first = cls[0]
            if first == "\\":
                first = {"d": "1", "w": "x", "s": " "}.get(cls[1], "x")
            out.append(first)
            i = end + 1
            if i < len(body) and body[i] in "*?":
                i += 1
            elif i < len(body) and body[i] == "+":
                i += 1
            continue
        if ch in "()":
            i += 1
            continue
        if ch in ".^$":
            out.append("x" if ch == "." else "")
            i += 1
            continue
        if ch in "*?":
            if out:
                out.pop()          # the previous atom is optional; drop it
            i += 1
            continue
        if ch == "+":
            i += 1
            continue
        if ch in "{}":
            return None
        out.append(ch)
        i += 1
    text = "".join(out)
    return text if text.strip() else None


def build_oracle(case: dict, sandbox: Path) -> tuple:
    """Materialise artifacts that satisfy what can be satisfied. Returns (output, unmet)."""
    wanted: dict = {}
    output_bits: list = []
    unverifiable: list = []

    for spec in case.get("checks", []):
        kind = spec.get("type")
        if kind in ("file_exists", "json_valid", "file_changed"):
            wanted.setdefault(spec["path"], [])
            if kind == "json_valid":
                keys = spec.get("required_keys", [])
                wanted[spec["path"]] = [json.dumps({k: "x" for k in keys} or {"ok": True})]
        elif kind == "file_matches":
            sample = sample_for(spec["pattern"])
            if sample is None:
                unverifiable.append(spec.get("id", spec["pattern"]))
                continue
            wanted.setdefault(spec["path"], []).append(sample)
        elif kind == "output_matches":
            sample = sample_for(spec["pattern"])
            if sample is None:
                unverifiable.append(spec.get("id", spec["pattern"]))
                continue
            output_bits.append(sample)
        elif kind == "file_size_ratio":
            base = (C.workspace(case) / spec["vs"])
            n = len(base.read_text(encoding="utf-8", errors="replace")) if base.exists() else 400
            mid = (float(spec.get("min", 0)) + float(spec.get("max", 1))) / 2
            wanted.setdefault(spec["path"], []).append("x" * max(1, int(n * mid)))
        elif kind in ("command", "tool_used", "skill_fired"):
            unverifiable.append(spec.get("id", kind))

    for rel, bits in wanted.items():
        path = sandbox / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        path.write_text(existing + "\n" + "\n".join(bits) + "\n", encoding="utf-8")

    return " ".join(output_bits), unverifiable


def score_synthetic(case: dict, cfg: dict, mode: str) -> tuple:
    with tempfile.TemporaryDirectory() as tmp:
        sandbox = C.build_sandbox(case, Path(tmp) / "sandbox")
        before = C.snapshot(sandbox)
        output, unverifiable = ("", []) if mode == "null" else build_oracle(case, sandbox)
        now = C.snapshot(sandbox)
        created = [r for r in now if r not in before]
        meta = {"final_text": output, "tool_calls": [],
                "triggered": mode == "oracle"}
        ctx = CH.Context(sandbox, C.originals(case), meta, created,
                         [r for r in now if r in before and now[r] != before[r]])
        results = [CH.run_check(spec, ctx) for spec in case.get("checks", [])]
    scored = M.score_case(case, results, [], cfg.get("weights"))
    return scored, results, unverifiable


def main() -> int:
    cfg = C.load_config(ROOT)
    cfg.setdefault("weights", M.DEFAULT_WEIGHTS)
    all_cases = C.load_cases(ROOT)
    problems: list = []

    if not all_cases:
        print("error: no cases found under cases/", file=sys.stderr)
        return 1

    print(f"suite: {cfg.get('target_skill')} · {len(all_cases)} case(s)\n")

    # ---- 1. lint --------------------------------------------------------------------
    splits = {c.get("split", "train") for c in all_cases}
    if "holdout" not in splits:
        problems.append("no holdout case: nothing will catch a revision that overfits")
    gates = sum(1 for c in all_cases for k in c.get("checks", []) if k.get("gate"))
    if not gates:
        problems.append("no check has gate:true — nothing is treated as unacceptable")
    safety = sum(1 for c in all_cases for k in c.get("checks", [])
                 if k.get("metric") == "safety")
    if not safety:
        problems.append("no check lands in the safety metric — the suite only rewards "
                        "doing more, never punishes doing damage")

    for case in all_cases:
        if case.get("kind") == "trigger":
            if not case.get("probes"):
                problems.append(f"{case['id']}: trigger case with no probes")
            elif not any(not p["should_fire"] for p in case["probes"]):
                problems.append(f"{case['id']}: every probe expects a fire — nothing tests "
                                f"over-triggering")
            continue
        if not case.get("checks") and not case.get("rubric"):
            problems.append(f"{case['id']}: no checks and no rubric")
        if not any(k.get("type") in PRODUCING for k in case.get("checks", [])) \
                and not case.get("rubric"):
            problems.append(
                f"{case['id']}: nothing requires the skill to produce anything. Checks like "
                f"file_unchanged and file_not_matches are satisfied by an agent that did "
                f"nothing at all — pair them with a file_exists or file_matches")
        for spec in case.get("checks", []):
            for err in CH.validate_spec(spec):
                problems.append(f"{case['id']}/{spec.get('id', '?')}: {err}")
            if spec.get("metric") not in cfg["weights"]:
                problems.append(f"{case['id']}/{spec.get('id', '?')}: metric "
                                f"{spec.get('metric')!r} is not in config weights")
        for item in case.get("rubric", []):
            if item.get("metric") and item["metric"] not in cfg["weights"]:
                problems.append(f"{case['id']}/{item.get('id')}: rubric metric "
                                f"{item['metric']!r} is not in config weights")

    # ---- 2 & 3. null and oracle ------------------------------------------------------
    print(f"{'case':28} {'null':>6} {'oracle':>7}   unverifiable checks")
    print("-" * 78)
    for case in all_cases:
        if case.get("kind") == "trigger":
            print(f"{case['id']:28} {'—':>6} {'—':>7}   (trigger case, probes run live)")
            continue
        null, _, _ = score_synthetic(case, cfg, "null")
        oracle, results, unverifiable = score_synthetic(case, cfg, "oracle")
        still_red = [r["id"] for r in results
                     if not r["passed"] and r["id"] not in unverifiable]
        note = ", ".join(unverifiable) or "—"
        print(f"{case['id']:28} {null['score']:6.2f} {oracle['score']:7.2f}   {note}")
        if null["score"] > NULL_MAX:
            problems.append(f"{case['id']}: an agent that did nothing scores "
                            f"{null['score']:.2f} — the checks are not testing enough")
        if oracle["score"] < ORACLE_MIN and not unverifiable:
            problems.append(f"{case['id']}: the oracle only reaches {oracle['score']:.2f}; "
                            f"checks still failing: {still_red}")
        elif still_red and not unverifiable:
            problems.append(f"{case['id']}: unsatisfiable check(s) {still_red}")

    print()
    if problems:
        print(f"{len(problems)} problem(s):")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("instrument looks sound: null runs score low, oracle runs score high, "
          "specs valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
