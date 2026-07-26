"""Scoring for one audit case, plus suite aggregation.

Six metrics. `safety` dominates on purpose: the skill's central promise is that it
would rather leave three redundant lines than delete one load-bearing one, so an eval
that rewarded aggressive cutting would optimise the skill in exactly the wrong
direction.

Two hard gates zero a case outright — editing the target in place, and producing no
report — because both make the output unusable regardless of classification quality.
"""

from __future__ import annotations

import re

from . import report as R

WEIGHTS = {
    "safety": 0.35,
    "recall": 0.25,
    "preservation": 0.15,
    "compliance": 0.12,
    "code_accuracy": 0.08,
    "calibration": 0.05,
}

# truth -> reported verdict -> credit. Conservative errors cost less than destructive ones.
CREDIT = {
    "CUT":   {"CUT": 1.0, "MERGE": 0.7, "MOVE": 0.6, "TRIM": 0.5, "KEEP": 0.0},
    "MERGE": {"MERGE": 1.0, "CUT": 0.9, "MOVE": 0.5, "TRIM": 0.5, "KEEP": 0.0},
    "TRIM":  {"TRIM": 1.0, "MERGE": 0.6, "MOVE": 0.6, "KEEP": 0.5, "CUT": 0.1},
    "MOVE":  {"MOVE": 1.0, "TRIM": 0.6, "MERGE": 0.5, "KEEP": 0.4, "CUT": 0.1},
    "KEEP":  {"KEEP": 1.0, "TRIM": 0.8, "MOVE": 0.5, "MERGE": 0.5, "CUT": 0.0},
}

TRAP_WEIGHT = 3.0  # a cut load-bearing line counts triple against safety


def est_tokens(text: str) -> int:
    return max(1, round(len(text) / 4))


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def score_case(case: dict, labels: list, artifacts: dict) -> dict:
    """artifacts: {report, rewrite, original, original_after, files_created, transcript_meta}"""
    report_text = R.strip_fences(artifacts.get("report") or "")
    rewrite_text = artifacts.get("rewrite") or ""
    original_text = artifacts.get("original") or ""
    expect = case.get("expect", {})

    violations = []
    notes = []

    if artifacts.get("original_after") is not None and \
            _norm(artifacts["original_after"]) != _norm(original_text):
        violations.append("in_place_edit")
    if not report_text.strip():
        violations.append("no_report")
    if expect.get("rewrite", True) and not rewrite_text.strip():
        violations.append("no_rewrite")

    reported = R.findings(report_text)
    reported_actions = [r for r in reported if r["table"] == "findings"]

    # ---- per-label classification -------------------------------------------------
    per_label = []
    for lab in labels:
        span = (lab.get("line_start", lab.get("line")), lab.get("line_end", lab.get("line")))
        m = R.verdict_for(span, reported_actions, lab.get("text", ""))
        got = m["row"]["verdict"] if m else "KEEP"          # absent from findings == kept
        got_code = m["row"]["code"] if m else None
        truth = lab["truth"].upper()
        accept = {v.upper() for v in lab.get("accept", [])}
        credit = 1.0 if got in accept else CREDIT.get(truth, {}).get(got, 0.0)
        per_label.append({
            "id": lab.get("id"),
            "line": lab.get("line"),
            "truth": truth,
            "got": got,
            "credit": credit,
            "severity": lab.get("severity", "normal"),
            "expected_codes": lab.get("codes", []),
            "got_code": got_code,
            "matched_by": m["match"] if m else "absent",
            "text": lab.get("text", "")[:160],
            "rationale": (m["row"]["rationale"][:200] if m else ""),
        })

    waste = [p for p in per_label if p["truth"] != "KEEP"]
    keeps = [p for p in per_label if p["truth"] == "KEEP"]

    recall = (sum(p["credit"] for p in waste) / len(waste)) if waste else None

    # ---- safety --------------------------------------------------------------------
    safety_num = safety_den = 0.0
    false_cuts = []
    for p in keeps:
        w = TRAP_WEIGHT if p["severity"] == "trap" else 1.0
        safety_den += w
        safety_num += w * p["credit"]
        if p["got"] == "CUT":
            false_cuts.append(p)
    # cutting a TRIM-labelled trap is also destructive
    for p in waste:
        if p["severity"] == "trap" and p["got"] == "CUT" and p["truth"] != "CUT":
            safety_den += TRAP_WEIGHT
            safety_num += 0.0
            false_cuts.append(p)
    safety = (safety_num / safety_den) if safety_den else None
    if any(p["severity"] == "trap" for p in false_cuts):
        violations.append("cut_load_bearing_line")

    # ---- preservation: required nouns must survive into the rewrite -----------------
    # Only lines that stay in this file can be checked; MOVE/MERGE relocate their content.
    required = [n for lab in labels if lab["truth"].upper() in ("KEEP", "TRIM")
                for n in lab.get("must_keep_nouns", [])]
    required += expect.get("must_keep_nouns", [])
    haystack = _norm(rewrite_text)
    missing_nouns = [n for n in required if _norm(n) not in haystack]
    preservation = (1 - len(missing_nouns) / len(required)) if required else None
    if missing_nouns:
        notes.append(f"rewrite dropped {len(missing_nouns)} required noun(s)")

    # judge.py, when it has run, contributes the half of fidelity that word-matching misses
    fidelity = artifacts.get("fidelity")
    if fidelity is not None:
        preservation = fidelity if preservation is None else preservation * fidelity
        for item in artifacts.get("judge_notes", []):
            notes.append(item)

    # ---- no smuggled-in new rules ---------------------------------------------------
    added = _added_content(original_text, rewrite_text) if rewrite_text else []
    if added:
        notes.append(f"{len(added)} rewrite sentence(s) contain material absent from the original")

    # ---- code accuracy --------------------------------------------------------------
    coded = [p for p in per_label if p["expected_codes"] and p["got_code"]]
    code_accuracy = (sum(1 for p in coded if p["got_code"] in p["expected_codes"]) / len(coded)
                     if coded else None)

    # ---- calibration: token reduction inside the expected band ----------------------
    calibration = None
    reduction = None
    if rewrite_text and original_text:
        before, after = est_tokens(original_text), est_tokens(rewrite_text)
        reduction = round(100 * (1 - after / before), 1)
        band = expect.get("reduction_pct")
        if band:
            lo, hi = band
            if lo <= reduction <= hi:
                calibration = 1.0
            else:
                off = (lo - reduction) if reduction < lo else (reduction - hi)
                calibration = max(0.0, 1 - off / 25.0)

    # ---- compliance -----------------------------------------------------------------
    checks = {}
    missing = R.missing_sections(report_text)
    checks["report_sections"] = 1 - len(missing) / len(R.REQUIRED_SECTIONS)
    checks["original_untouched"] = 0.0 if "in_place_edit" in violations else 1.0
    checks["report_saved_to_file"] = 1.0 if artifacts.get("report_from_file") else 0.0
    if expect.get("rewrite", True):
        checks["rewrite_beside_original"] = 1.0 if artifacts.get("rewrite_path_ok") else 0.0
    if case.get("invoke") == "natural":
        checks["skill_triggered"] = 1.0 if artifacts.get("triggered") else 0.0

    cuts = [r for r in reported_actions if r["verdict"] == "CUT"]
    if cuts:
        block = _norm(R.cut_verbatim_block(report_text))
        orig_lines = original_text.splitlines()
        shown = sum(1 for r in cuts if _cut_shown(r, block, orig_lines))
        checks["cuts_shown_verbatim"] = shown / len(cuts)

    nums = R.summary_numbers(report_text)
    checks["quantified"] = 1.0 if any(len(v) >= 2 for v in nums.values()) else 0.0

    for pattern in expect.get("must_mention", []):
        hit = re.search(pattern, report_text, re.I) is not None
        checks[f"mentions:{pattern[:34]}"] = 1.0 if hit else 0.0
    for pattern in expect.get("must_not_mention", []):
        hit = re.search(pattern, report_text, re.I) is not None
        checks[f"avoids:{pattern[:34]}"] = 0.0 if hit else 1.0

    compliance = sum(checks.values()) / len(checks) if checks else None

    metrics = {
        "safety": safety, "recall": recall, "preservation": preservation,
        "compliance": compliance, "code_accuracy": code_accuracy, "calibration": calibration,
    }
    score = _weighted(metrics)
    if "in_place_edit" in violations or "no_report" in violations:
        score = 0.0

    return {
        "case": case["id"], "kind": case.get("kind", "audit"), "split": case.get("split", "train"),
        "score": round(score, 4),
        "metrics": {k: (round(v, 4) if v is not None else None) for k, v in metrics.items()},
        "violations": violations,
        "notes": notes,
        "details": {
            "per_label": per_label,
            "false_cuts": [p["id"] for p in false_cuts],
            "missed_waste": [p["id"] for p in waste if p["credit"] < 0.5],
            "missing_sections": missing,
            "missing_nouns": missing_nouns,
            "added_content": added[:8],
            "compliance_checks": {k: round(v, 3) for k, v in checks.items()},
            "reduction_pct": reduction,
            "reported_rows": len(reported_actions),
            "triggered": artifacts.get("triggered"),
            "read_taxonomy": artifacts.get("read_taxonomy"),
            "ran_analyze": artifacts.get("ran_analyze"),
        },
    }


def score_trigger_case(case: dict, results: list) -> dict:
    """results: [{prompt, should_fire, fired}] from the trigger probe."""
    if not results:
        return {"case": case["id"], "kind": "trigger", "split": case.get("split", "train"),
                "score": 0.0, "metrics": {}, "violations": ["no_probes"], "notes": [],
                "details": {}}
    pos = [r for r in results if r["should_fire"]]
    neg = [r for r in results if not r["should_fire"]]
    fire_rate = sum(1 for r in pos if r["fired"]) / len(pos) if pos else None
    quiet_rate = sum(1 for r in neg if not r["fired"]) / len(neg) if neg else None
    parts = [v for v in (fire_rate, quiet_rate) if v is not None]
    return {
        "case": case["id"], "kind": "trigger", "split": case.get("split", "train"),
        "score": round(sum(parts) / len(parts), 4),
        "metrics": {"fire_rate": fire_rate, "quiet_rate": quiet_rate},
        "violations": [], "notes": [],
        "details": {"probes": results,
                    "missed": [r["prompt"] for r in pos if not r["fired"]],
                    "over_fired": [r["prompt"] for r in neg if r["fired"]]},
    }


def _weighted(metrics: dict) -> float:
    live = {k: v for k, v in metrics.items() if v is not None}
    if not live:
        return 0.0
    total_w = sum(WEIGHTS[k] for k in live)
    return sum(WEIGHTS[k] * v for k, v in live.items()) / total_w


_SENT = re.compile(r"(?<=[.!?;:])\s+|\n")


def _added_content(original: str, rewrite: str) -> list:
    """Rewrite sentences whose content words are mostly absent from the original.

    A subtractive edit should introduce no new vocabulary. Cheap proxy for "did it
    invent a rule"; the LLM judge in judge.py handles the subtle cases.
    """
    src = R._words(original)
    out = []
    for sent in _SENT.split(rewrite):
        sent = sent.strip(" -*#|`")
        words = R._words(sent)
        if len(words) < 5:
            continue
        novel = words - src
        if len(novel) / len(words) > 0.55:
            out.append(sent[:180])
    return out


def _cut_shown(row: dict, block: str, orig_lines: list) -> bool:
    """Is this CUT's original text reproduced in the undo buffer?

    Checked against the source file rather than against the findings table's own quote:
    that quote is abbreviated, often with an ellipsis, so matching it would fail on
    reports that did reproduce the line correctly.
    """
    for a, b in row["spans"]:
        for i in range(a, min(b, a + 40) + 1):
            if not (1 <= i <= len(orig_lines)):
                continue
            words = R._words(orig_lines[i - 1])
            if len(words) < 4:
                continue
            probe = " ".join(_norm(orig_lines[i - 1]).split()[:6])
            if len(probe) >= 12 and probe in block:
                return True
    return _quote_present(row["text"], block)


def _quote_present(quoted: str, block: str) -> bool:
    q = _norm(quoted).strip('"“”…. ')
    q = re.sub(r"^l?\d+\s*[:.\-]\s*", "", q)
    if len(q) < 12:
        return bool(q) and q in block
    # abbreviated quotes in the findings table are matched on their longest run
    probe = q[:60]
    return probe in block or " ".join(q.split()[:6]) in block
