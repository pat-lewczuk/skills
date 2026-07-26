#!/usr/bin/env python3
"""Mechanical pre-pass for a no-op audit of an agent instruction file.

Produces evidence, not verdicts. It splits the file into numbered directives, estimates
token cost per section, finds near-duplicates within and across files, extracts every
path/command reference and checks whether it exists, and measures vague-language density.
Classification is the model's job.

Usage:
    python3 analyze.py AGENTS.md [--repo .] [--also CLAUDE.md --also .cursorrules]
                       [--json analysis.json] [--quiet]

Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, asdict, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Heuristics tables. These flag candidates for human/model review — they never
# decide anything on their own.
# ---------------------------------------------------------------------------

VAGUE_QUANTIFIERS = [
    "reasonably", "appropriately", "properly", "adequately", "sufficiently",
    "as needed", "where appropriate", "when appropriate", "if necessary",
    "as necessary", "small", "large", "short", "long", "quickly", "clean",
    "simple", "complex", "good", "bad", "best practice", "best practices",
    "high quality", "well-structured", "maintainable", "readable", "robust",
    "efficient", "scalable", "idiomatic", "modern", "carefully", "thoroughly",
    "thoughtful", "thoughtfully", "sensible", "meaningful", "proper",
]

HEDGES = [
    "try to", "consider", "prefer", "generally", "usually", "typically",
    "ideally", "when possible", "if possible", "aim to", "strive", "should probably",
    "it is recommended", "it's recommended", "feel free",
]

SELF_REFERENCE = [
    "these instructions", "this file", "this document", "the guidelines below",
    "the rules above", "follow the above", "read this", "as stated above",
    "as mentioned", "the guidelines in this",
]

ABSOLUTES = ["never", "always", "must", "all ", "every ", "100%", "under no circumstances"]

# Words that mark a directive as plausibly project-specific.
PROJECT_NOUN_HINTS = re.compile(
    r"`[^`]+`|\b[\w.-]+\.(?:ts|tsx|js|jsx|py|go|rs|rb|php|java|kt|sh|sql|ya?ml|json|toml|md|env)\b"
    r"|\b(?:npm|pnpm|yarn|bun|make|cargo|go|poetry|uv|pip|docker|kubectl|git)\s+\w+"
    r"|\b[\w-]+/[\w./*-]+"
)

REF_PATTERNS = [
    re.compile(r"`([^`\n]+)`"),                       # inline code
    re.compile(r"\]\(([^)\s]+)\)"),                   # markdown link target
    re.compile(r"(?<![\w`])((?:\./|/)?[\w.-]+/[\w./*-]+)"),  # bare path-ish
]

# Things inside backticks that are not file paths worth existence-checking.
NON_PATH = re.compile(r"^(?:[A-Z_]{2,}|true|false|null|undefined|any|string|number|boolean)$")

CODE_FENCE = re.compile(r"^\s*(```|~~~)")
HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.*)$")
TABLE_ROW = re.compile(r"^\s*\|")


# ---------------------------------------------------------------------------


@dataclass
class Directive:
    id: int
    line: int
    end_line: int
    section: str
    kind: str            # bullet | prose | heading | table | code
    text: str
    tokens: int
    flags: list = field(default_factory=list)
    references: list = field(default_factory=list)


def est_tokens(text: str) -> int:
    """Rough token estimate. ~4 chars/token for English prose; good enough for budgeting."""
    return max(1, round(len(text) / 4))


STOPWORDS = {"the", "a", "an", "and", "or", "of", "to", "in", "for", "with", "that",
             "this", "is", "are", "be", "it", "on", "as", "at", "by", "all"}


def normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s/._-]", " ", text)
    return " ".join(text.split())


def content_words(text: str) -> list:
    words = (w.strip("._-") for w in normalize(text).split())
    return [w for w in words if w and w not in STOPWORDS]


def shingles(text: str) -> set:
    """Unigrams + bigrams over content words. Catches paraphrases that trigram
    shingling misses ('use conventional commits' vs 'follow the conventional
    commits spec') while identical commands still match strongly."""
    words = content_words(text)
    if not words:
        return set()
    grams = set(words)
    grams |= {" ".join(words[i:i + 2]) for i in range(len(words) - 1)}
    return grams


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def parse(path: Path) -> list:
    """Split a markdown instruction file into atomic directives with line numbers."""
    raw = path.read_text(encoding="utf-8", errors="replace").splitlines()
    directives: list = []
    section = "(root)"
    in_fence = False
    fence_start = 0
    fence_buf: list = []
    prose_buf: list = []
    prose_start = 0
    did = 0

    def flush_prose():
        nonlocal prose_buf, did
        if not prose_buf:
            return
        blob = " ".join(prose_buf).strip()
        prose_buf = []
        if not blob:
            return
        # One directive per sentence: instruction files hide several rules in a paragraph.
        parts = [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z`])", blob) if s.strip()]
        for part in parts:
            did += 1
            directives.append(Directive(did, prose_start, prose_start, section,
                                        "prose", part, est_tokens(part)))

    for i, line in enumerate(raw, start=1):
        if CODE_FENCE.match(line):
            if in_fence:
                did += 1
                body = "\n".join(fence_buf)
                directives.append(Directive(did, fence_start, i, section, "code",
                                            body[:400], est_tokens(body)))
                fence_buf = []
                in_fence = False
            else:
                flush_prose()
                in_fence = True
                fence_start = i
            continue
        if in_fence:
            fence_buf.append(line)
            continue

        h = HEADING.match(line)
        if h:
            flush_prose()
            section = h.group(2).strip()
            did += 1
            directives.append(Directive(did, i, i, section, "heading",
                                        line.strip(), est_tokens(line)))
            continue

        b = BULLET.match(line)
        if b:
            flush_prose()
            did += 1
            text = b.group(1).strip()
            directives.append(Directive(did, i, i, section, "bullet", text, est_tokens(text)))
            continue

        if TABLE_ROW.match(line):
            flush_prose()
            did += 1
            directives.append(Directive(did, i, i, section, "table",
                                        line.strip(), est_tokens(line)))
            continue

        if not line.strip():
            flush_prose()
            continue

        if not prose_buf:
            prose_start = i
        prose_buf.append(line.strip())

    flush_prose()
    return directives


def flag(d: Directive) -> None:
    low = " " + d.text.lower() + " "
    hits = []
    if any(w in low for w in VAGUE_QUANTIFIERS):
        hits.append("vague")
    if any(w in low for w in HEDGES):
        hits.append("hedge")
    if any(w in low for w in SELF_REFERENCE):
        hits.append("self-referential")
    if any(w in low for w in ABSOLUTES):
        hits.append("absolute")
    if PROJECT_NOUN_HINTS.search(d.text):
        hits.append("project-noun")
    if re.search(r"\b(?:don't|do not|never|avoid|no\s+\w+ing)\b", low):
        hits.append("negative-constraint")
    if len(normalize(d.text).split()) > 45 and d.kind == "prose":
        hits.append("long")
    d.flags = hits


def extract_refs(d: Directive, repo: Path | None) -> None:
    found = []
    seen = set()
    for pat in REF_PATTERNS:
        for m in pat.finditer(d.text):
            token = m.group(1).strip()
            if not token or token in seen:
                continue
            seen.add(token)
            candidate = token.split()[0].strip("()[],;:'\"")
            if NON_PATH.match(candidate) or len(candidate) < 3:
                continue
            looks_pathy = "/" in candidate or re.search(r"\.\w{1,5}$", candidate)
            if not looks_pathy:
                continue
            norm = candidate.lstrip("./").rstrip("/")
            if any(r["ref"].lstrip("./").rstrip("/") == norm for r in found):
                continue
            entry = {"ref": candidate, "exists": None}
            if repo:
                p = (repo / candidate.lstrip("./")).resolve()
                entry["exists"] = p.exists()
                if not entry["exists"] and "*" in candidate:
                    entry["exists"] = bool(list(repo.glob(candidate.lstrip("./"))))
            found.append(entry)
    d.references = found


def find_duplicates(groups: dict, threshold: float = 0.45) -> list:
    """Near-duplicate directive pairs, within and across files. Lexical only —
    semantic duplicates that share no vocabulary are the model's job to spot."""
    items = []
    for fname, ds in groups.items():
        for d in ds:
            if d.kind in ("heading", "code", "table"):
                continue
            if len(content_words(d.text)) < 3:
                continue
            items.append((fname, d, shingles(d.text)))

    pairs = []
    for i in range(len(items)):
        f1, d1, s1 = items[i]
        for j in range(i + 1, len(items)):
            f2, d2, s2 = items[j]
            score = jaccard(s1, s2)
            if score >= 0.28:
                pairs.append({
                    "similarity": round(score, 2),
                    "tier": "likely" if score >= threshold else "possible",
                    "cross_file": f1 != f2,
                    "a": {"file": f1, "line": d1.line, "text": d1.text[:160]},
                    "b": {"file": f2, "line": d2.line, "text": d2.text[:160]},
                })
    pairs.sort(key=lambda p: (-p["similarity"], p["a"]["line"]))
    return pairs


def section_costs(ds: list) -> list:
    out: dict = {}
    for d in ds:
        s = out.setdefault(d.section, {"section": d.section, "directives": 0, "tokens": 0,
                                       "first_line": d.line})
        s["directives"] += 1
        s["tokens"] += d.tokens
    rows = sorted(out.values(), key=lambda r: -r["tokens"])
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("target")
    ap.add_argument("--repo", default=None, help="repo root for reference existence checks")
    ap.add_argument("--also", action="append", default=[],
                    help="other instruction files to check for cross-file duplication")
    ap.add_argument("--json", default="analysis.json")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    target = Path(args.target)
    if not target.exists():
        print(f"error: {target} not found", file=sys.stderr)
        return 1
    repo = Path(args.repo).resolve() if args.repo else None
    if repo and not repo.exists():
        print(f"error: repo root {repo} not found", file=sys.stderr)
        return 1

    groups = {str(target): parse(target)}
    for extra in args.also:
        p = Path(extra)
        if p.exists():
            groups[str(p)] = parse(p)
        else:
            print(f"warning: --also {p} not found, skipping", file=sys.stderr)

    for ds in groups.values():
        for d in ds:
            flag(d)
            extract_refs(d, repo)

    main_ds = groups[str(target)]
    dupes = find_duplicates(groups)

    dead = [
        {"line": d.line, "ref": r["ref"], "text": d.text[:120]}
        for d in main_ds for r in d.references if r["exists"] is False
    ]

    total_tokens = sum(d.tokens for d in main_ds)
    actionable = [d for d in main_ds if d.kind != "heading"]
    with_noun = [d for d in actionable if "project-noun" in d.flags]
    vague = [d for d in actionable if "vague" in d.flags and "project-noun" not in d.flags]

    report = {
        "target": str(target),
        "repo": str(repo) if repo else None,
        "mode": "full" if repo else "evidence-limited",
        "totals": {
            "lines": len(target.read_text(encoding="utf-8", errors="replace").splitlines()),
            "directives": len(main_ds),
            "actionable_directives": len(actionable),
            "est_tokens": total_tokens,
            "directives_with_project_noun": len(with_noun),
            "project_noun_ratio": round(len(with_noun) / max(1, len(actionable)), 2),
            "vague_no_noun": len(vague),
        },
        "sections": section_costs(main_ds),
        "near_duplicates": dupes,
        "dead_references": dead,
        "directives": [asdict(d) for d in main_ds],
    }

    Path(args.json).write_text(json.dumps(report, indent=2), encoding="utf-8")

    if args.quiet:
        return 0

    t = report["totals"]
    print(f"\n=== {target} ({report['mode']}) ===")
    print(f"lines {t['lines']} · directives {t['directives']} "
          f"(actionable {t['actionable_directives']}) · est. tokens {t['est_tokens']}")
    print(f"project-noun ratio {t['project_noun_ratio']} "
          f"({t['directives_with_project_noun']}/{t['actionable_directives']}) "
          f"— low ratio suggests generic content")
    print(f"vague-without-project-noun: {t['vague_no_noun']} directives\n")

    print("-- heaviest sections --")
    for s in report["sections"][:10]:
        print(f"  {s['tokens']:>6} tok  {s['directives']:>3} dir  L{s['first_line']:<4} {s['section'][:60]}")

    if dupes:
        likely = [p for p in dupes if p["tier"] == "likely"]
        possible = [p for p in dupes if p["tier"] == "possible"]
        print(f"\n-- near-duplicates: {len(likely)} likely, {len(possible)} possible --")
        for p in dupes[:20]:
            tag = "CROSS-FILE" if p["cross_file"] else "same-file"
            print(f"  [{p['similarity']} {p['tier']}] {tag}")
            print(f"      {p['a']['file']}:{p['a']['line']}  {p['a']['text'][:90]}")
            print(f"      {p['b']['file']}:{p['b']['line']}  {p['b']['text'][:90]}")

    if dead:
        print(f"\n-- references not found in repo ({len(dead)}) --")
        for r in dead[:25]:
            print(f"  L{r['line']}: {r['ref']}")
    elif repo is None:
        print("\n-- reference existence unchecked (no --repo given) --")

    flagged = [d for d in actionable if d.flags and "project-noun" not in d.flags]
    print(f"\n-- candidates for review ({len(flagged)}) — flags only, not verdicts --")
    for d in flagged[:40]:
        print(f"  L{d.line:<4} [{','.join(d.flags)}] {d.text[:95]}")

    print(f"\nfull data: {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
