"""Reject skill edits that memorise the eval instead of improving the method.

Feed failures to a model with edit access and it will, given the chance, hardcode answers:
"the rule about port 4310 is load-bearing", "the file at src/db.ts must never be touched".
That scores well on the next run and teaches the skill nothing.

Three checks, run against added lines only:

  1. no case id or fixture filename
  2. no distinctive token from any fixture (paths, identifiers, anything with a digit)
  3. no long verbatim span from a fixture that was not already in the skill

Two exemptions keep it from blocking honest edits — both added after real false positives:

- **Already in the baseline skill.** A token the skill already used is not something it
  memorised from a fixture.
- **Appears in more than one case.** Memorisation is case-specific by nature; a token found
  in two independent fixtures (`node_modules`, `package.json`) is vocabulary, not an answer.
"""

from __future__ import annotations

import difflib
import re
from pathlib import Path

_WORD = re.compile(r"[a-z0-9][\w./:$-]*", re.I)
_DISTINCTIVE = re.compile(
    r"""^(?:
        [\w.-]*/[\w./*-]+
        | \w+\.(?:ts|tsx|js|jsx|py|mjs|go|rs|rb|java|kt|sql|toml|ya?ml|json|sh|md|env)$
        | [a-z]+_[a-z_]+
        | [a-z]+[A-Z]\w+
        | [A-Z]{2,}[\w_]*
        | \w*\d[\w.-]*
    )$""",
    re.X,
)
_COMMON = {
    "utf-8", "python3", "readme.md", "agents.md", "claude.md", "skill.md",
    "package.json", "tsconfig.json", "pre-commit", "node_modules", "dist", "build",
    "coverage", "vendor", "target", "venv", "__pycache__", "config.json", "case.json",
    "labels.json", "scores.json", "results.html", "report.md",
}
_GENERIC_NAMES = {"case.json", "labels.json", ".ds_store", "agents.md", "claude.md",
                  "skill.md", "readme.md", "package.json", "config.json"}


def _case_of(path: Path, cases_dir: Path) -> str:
    rel = path.relative_to(cases_dir).parts
    return rel[0] if rel else "?"


def fixture_vocabulary(cases_dir: Path) -> tuple:
    """(token -> the cases it appears in, normalised fixture lines)."""
    tokens: dict = {}
    lines: list = []
    for path in cases_dir.rglob("*"):
        if not path.is_file() or path.suffix in (".pyc", ".png", ".jpg", ".gif"):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="strict")
        except (UnicodeDecodeError, OSError):
            continue
        case = _case_of(path, cases_dir)
        for raw in text.splitlines():
            norm = " ".join(_WORD.findall(raw.lower()))
            if len(norm.split()) >= 6:
                lines.append(norm)
        for tok in _WORD.findall(text):
            low = tok.lower().strip(".,:;)(")
            if low in _COMMON or len(low) < 3:
                continue
            if _DISTINCTIVE.match(tok):
                tokens.setdefault(low, set()).add(case)
    return tokens, lines


def added_lines(before_dir: Path, after_dir: Path) -> list:
    out = []
    for after in sorted(after_dir.rglob("*")):
        if not after.is_file() or after.suffix not in (".md", ".py", ".txt", ".json", ".sh"):
            continue
        rel = after.relative_to(after_dir)
        before = before_dir / rel
        old = (before.read_text(encoding="utf-8", errors="replace").splitlines()
               if before.exists() else [])
        new = after.read_text(encoding="utf-8", errors="replace").splitlines()
        for line in difflib.unified_diff(old, new, n=0, lineterm=""):
            if line.startswith("+") and not line.startswith("+++"):
                out.append((str(rel), line[1:]))
    return out


def check(before_dir: Path, after_dir: Path, cases_dir: Path, case_ids: list) -> dict:
    tokens, fixture_lines = fixture_vocabulary(cases_dir)
    baseline_text = " ".join(
        p.read_text(encoding="utf-8", errors="replace").lower()
        for p in before_dir.rglob("*") if p.is_file() and p.suffix in (".md", ".py", ".sh"))

    names: dict = {cid.lower(): {cid} for cid in case_ids}
    for p in cases_dir.rglob("*"):
        if p.is_file() and p.name.lower() not in _GENERIC_NAMES:
            names.setdefault(p.name.lower(), set()).add(_case_of(p, cases_dir))

    violations = []
    for rel, line in added_lines(before_dir, after_dir):
        low = line.lower()
        for name, in_cases in names.items():
            if len(name) > 5 and name in low and len(in_cases) == 1 \
                    and name not in baseline_text:
                violations.append({"kind": "fixture_name", "file": rel,
                                   "line": line[:150], "hit": name})
        for tok in _WORD.findall(line):
            t = tok.lower().strip(".,:;)(")
            in_cases = tokens.get(t)
            if in_cases and len(in_cases) == 1 and t not in baseline_text:
                violations.append({"kind": "fixture_token", "file": rel,
                                   "line": line[:150], "hit": t})
        words = " ".join(_WORD.findall(low)).split()
        if len(words) >= 12:
            for i in range(len(words) - 11):
                span = " ".join(words[i:i + 12])
                if any(span in fl for fl in fixture_lines) and span not in baseline_text:
                    violations.append({"kind": "verbatim_span", "file": rel,
                                       "line": line[:150], "hit": span[:90]})
                    break

    seen, unique = set(), []
    for v in violations:
        key = (v["kind"], v["hit"], v["file"])
        if key not in seen:
            seen.add(key)
            unique.append(v)
    return {"ok": not unique, "violations": unique}
