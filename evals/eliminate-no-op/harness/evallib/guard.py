"""Reject skill edits that memorise the eval instead of improving the method.

A loop that feeds failures back into a prompt will, given the chance, hardcode answers:
"the line about port 4310 is load-bearing", "docs/architecture.md does not exist". That
scores well and teaches the skill nothing. Three checks, run against added lines only:

  1. no case id or fixture filename
  2. no distinctive token from any fixture (paths, identifiers, numbers, invented names)
  3. no long verbatim span from any fixture that was not already in the skill

Check 2 does the real work. Generic phrases like "write clean code" appear in both the
fixtures and the taxonomy's own examples, so a naive n-gram check would fire on
legitimate edits; distinctive tokens do not have that problem.

Two exemptions keep the guard from blocking honest edits, both learned from false
positives on a real candidate:

- **Already in the baseline skill.** `.cursorrules` is named in the skill's own description.
  A token the skill already used is not something it memorised from a fixture.
- **Appears in more than one case.** Memorisation is case-specific by nature. A token found
  in two or more independent fixtures (`node_modules`, `package.json`) is vocabulary, not a
  leaked answer.
"""

from __future__ import annotations

import difflib
import re
from pathlib import Path

_WORD = re.compile(r"[a-z0-9][\w./:$-]*", re.I)
_DISTINCTIVE = re.compile(
    r"""^(?:
        [\w.-]*/[\w./*-]+            # paths
        | \w+\.(?:ts|tsx|py|mjs|sql|toml|yml|yaml|json|sh|md)$
        | [a-z]+_[a-z_]+             # snake_case
        | [a-z]+[A-Z]\w+             # camelCase
        | [A-Z]{2,}[\w_]*            # SCREAMING_CASE
        | \w*\d[\w.-]*               # anything with a digit
    )$""",
    re.X,
)
_COMMON = {
    "utf-8", "python3", "readme.md", "agents.md", "claude.md", "skill.md", "eslint",
    "prettier", "tsconfig.json", "package.json", "pre-commit", "n1", "n2", "n3", "n4",
    "n5", "n6", "n7", "n8", "n9", "n10", "n11", "n12", "l1", "l2", "l3", "l4", "l5", "l6",
    "analysis.json", "analyze.py", "taxonomy.md", "report-template.md", "no-op-report.md",
    "node_modules", "dist", "build", "coverage", "vendor", "target", "venv", "__pycache__",
    "300", "200", "100", "40", "2", "3", "5", "1", "0", "45", "60", "4",
}


def fixture_vocabulary(cases_dir: Path) -> tuple:
    """(token -> the cases it appears in, normalised fixture lines) across all workspaces."""
    tokens: dict = {}
    lines = []
    for path in cases_dir.rglob("*"):
        if not path.is_file() or path.suffix in (".pyc",):
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


def _case_of(path: Path, cases_dir: Path) -> str:
    rel = path.relative_to(cases_dir).parts
    return rel[0] if rel else "?"


def added_lines(before_dir: Path, after_dir: Path) -> list:
    """Lines present in the candidate skill and absent from the baseline."""
    out = []
    for after in sorted(after_dir.rglob("*")):
        if not after.is_file() or after.suffix not in (".md", ".py", ".txt", ".json"):
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
        for p in before_dir.rglob("*") if p.is_file() and p.suffix in (".md", ".py"))

    names: dict = {cid.lower(): {cid} for cid in case_ids}
    for p in cases_dir.rglob("*"):
        if not p.is_file():
            continue
        name = p.name.lower()
        if name in ("case.json", "labels.json", ".ds_store", "agents.md", "claude.md",
                    "skill.md", "readme.md"):
            continue
        names.setdefault(name, set()).add(_case_of(p, cases_dir))

    violations = []
    for rel, line in added_lines(before_dir, after_dir):
        low = line.lower()
        for name, in_cases in names.items():
            if len(name) > 5 and name in low and len(in_cases) == 1 \
                    and name not in baseline_text:
                violations.append({"kind": "fixture_name", "file": rel, "line": line[:150],
                                   "hit": name})
        for tok in _WORD.findall(line):
            t = tok.lower().strip(".,:;)(")
            in_cases = tokens.get(t)
            if in_cases and len(in_cases) == 1 and t not in baseline_text:
                violations.append({"kind": "fixture_token", "file": rel, "line": line[:150],
                                   "hit": t})
        norm = " ".join(_WORD.findall(low))
        words = norm.split()
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
