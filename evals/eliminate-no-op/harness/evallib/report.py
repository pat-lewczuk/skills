"""Parse a no-op audit report (markdown) into machine-checkable structure.

The graders read the artifact a real user gets — the markdown report — rather than a
JSON side-channel invented for the eval. That keeps the eval honest: if the report is
unparseable by a careful reader, that is a real defect, not a harness problem.

Tolerant by design: column order, `L12` vs `12`, en-dashes in ranges, and extra
sections are all accepted. Missing *required* sections are reported, not fatal.
"""

from __future__ import annotations

import re

VERDICTS = ("KEEP", "TRIM", "MERGE", "MOVE", "CUT")

# Section key -> substrings that identify its heading (lowercased, any match wins).
REQUIRED_SECTIONS = {
    "summary": ("summary",),
    "verdict_breakdown": ("verdict breakdown", "verdicts", "breakdown"),
    "findings": ("finding",),
    "cut_verbatim": ("cut lines", "cuts, verbatim", "verbatim"),
    "kept": ("kept despite", "looking generic", "kept "),
    "open_questions": ("open question", "questions for", "needs your"),
    "observations": ("observation",),
    "rewrite": ("proposed rewrite", "rewrite"),
}

HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
_RANGE = re.compile(r"(\d+)\s*(?:[-–—]|\bto\b|\.\.)\s*(\d+)")
_NUM = re.compile(r"\d+")
_VERDICT_RE = re.compile(r"\b(KEEP|TRIM|MERGE|MOVE|CUT)\b", re.I)
_CODE_RE = re.compile(r"\b([NL]\d{1,2})\b")


def strip_fences(text: str) -> str:
    """Reports are sometimes wrapped in a ```markdown fence. Unwrap a single outer one."""
    lines = text.splitlines()
    fences = [i for i, ln in enumerate(lines) if ln.strip().startswith("```")]
    if len(fences) >= 2 and fences[0] <= 2 and lines[fences[0]].strip().lower() in (
        "```markdown", "```md", "```",
    ):
        return "\n".join(lines[fences[0] + 1:fences[-1]])
    return text


def sections(text: str) -> dict:
    """Map heading title -> body text, in document order."""
    out: dict = {}
    current = "(root)"
    buf: list = []
    for ln in text.splitlines():
        m = HEADING.match(ln)
        if m:
            out[current] = out.get(current, "") + "\n".join(buf) + "\n"
            buf = []
            current = m.group(2).strip()
        else:
            buf.append(ln)
    out[current] = out.get(current, "") + "\n".join(buf) + "\n"
    return out


def missing_sections(text: str) -> list:
    titles = [t.lower() for t in sections(text)]
    blob = "\n".join(titles)
    missing = []
    for key, needles in REQUIRED_SECTIONS.items():
        if not any(n in blob for n in needles):
            missing.append(key)
    return missing


def _tables(body: str) -> list:
    """Extract markdown tables as list-of-rows (cells already stripped)."""
    tables = []
    rows: list = []
    for ln in body.splitlines():
        if ln.strip().startswith("|"):
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            rows.append(cells)
        else:
            if len(rows) >= 2:
                tables.append(rows)
            rows = []
    if len(rows) >= 2:
        tables.append(rows)
    return tables


def _is_separator(cells: list) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{2,}:?", c or "") for c in cells if c != "")


def parse_line_field(cell: str) -> list:
    """'L34-41' -> [(34,41)]; '12' -> [(12,12)]; 'L21, L45' -> [(21,21),(45,45)]."""
    cell = cell.replace("`", "")
    spans = []
    consumed = set()
    for m in _RANGE.finditer(cell):
        a, b = int(m.group(1)), int(m.group(2))
        spans.append((min(a, b), max(a, b)))
        consumed.update(range(m.start(), m.end()))
    for m in _NUM.finditer(cell):
        if m.start() in consumed:
            continue
        n = int(m.group(0))
        spans.append((n, n))
    return spans


def _column_map(header: list) -> dict:
    idx = {}
    for i, h in enumerate(header):
        h = h.lower()
        if "line" in h or h in ("id", "l#", "#"):
            idx.setdefault("line", i)
        elif "verdict" in h or "action" in h:
            idx.setdefault("verdict", i)
        elif "code" in h:
            idx.setdefault("code", i)
        elif "rationale" in h or "reason" in h or "why" in h or "evidence" in h:
            idx.setdefault("rationale", i)
        elif "directive" in h or "text" in h or "quote" in h or "content" in h:
            idx.setdefault("text", i)
    return idx


def findings(text: str) -> list:
    """Rows from any table that carries both a line-ish and a verdict-ish column.

    Returns [{spans, verdict, code, text, rationale}]. A row whose verdict cell is
    empty but whose table lives under a 'kept' heading is treated as KEEP.
    """
    rows_out = []
    for title, body in sections(text).items():
        tl = title.lower()
        kept_table = any(n in tl for n in ("kept despite", "looking generic"))
        for table in _tables(body):
            header = table[0]
            cmap = _column_map(header)
            if "line" not in cmap:
                continue
            has_verdict = "verdict" in cmap
            if not has_verdict and not kept_table:
                # Could still be a findings table with the verdict inline in a cell.
                if not any(_VERDICT_RE.search(" ".join(r)) for r in table[1:]):
                    continue
            for cells in table[1:]:
                if _is_separator(cells):
                    continue
                joined = " ".join(cells)
                spans = parse_line_field(cells[cmap["line"]] if cmap["line"] < len(cells) else "")
                if not spans:
                    continue
                vm = None
                if has_verdict and cmap["verdict"] < len(cells):
                    vm = _VERDICT_RE.search(cells[cmap["verdict"]])
                if vm is None:
                    vm = _VERDICT_RE.search(joined)
                verdict = vm.group(1).upper() if vm else ("KEEP" if kept_table else None)
                if verdict is None:
                    continue
                code_cell = cells[cmap["code"]] if "code" in cmap and cmap["code"] < len(cells) else joined
                code = _CODE_RE.search(code_cell)
                rows_out.append({
                    "spans": spans,
                    "verdict": verdict,
                    "code": code.group(1).upper() if code else None,
                    "text": cells[cmap["text"]] if "text" in cmap and cmap["text"] < len(cells) else "",
                    "rationale": (cells[cmap["rationale"]]
                                  if "rationale" in cmap and cmap["rationale"] < len(cells) else ""),
                    "table": "kept" if kept_table else "findings",
                })
    return rows_out


def cut_verbatim_block(text: str) -> str:
    for title, body in sections(text).items():
        tl = title.lower()
        if "cut" in tl and ("verbatim" in tl or "line" in tl):
            return body
    return ""


def summary_numbers(text: str) -> dict:
    """Pull before/after figures out of the summary table. Best-effort."""
    out: dict = {}
    for title, body in sections(text).items():
        if "summary" not in title.lower():
            continue
        for table in _tables(body):
            for cells in table:
                if _is_separator(cells) or not cells:
                    continue
                label = cells[0].lower().strip("* ")
                nums = [int(n.replace(",", "")) for c in cells[1:]
                        for n in re.findall(r"\d[\d,]*", c)]
                if not nums:
                    continue
                for key, needles in (("directives", ("directive",)),
                                     ("lines", ("line",)),
                                     ("tokens", ("token",)),
                                     ("density", ("density", "signal"))):
                    if any(n in label for n in needles):
                        out.setdefault(key, nums[:2])
    return out


def verdict_for(spans_and_text, reported: list, label_text: str = "") -> dict | None:
    """Best matching reported row for a labelled directive.

    Line-span overlap wins. Falls back to content-word similarity against the
    reported directive text so a report that renumbers lines still grades.
    """
    lo, hi = spans_and_text
    best = None
    for row in reported:
        if any(not (hi < a or lo > b) for a, b in row["spans"]):
            # Prefer the tightest overlapping span.
            width = min(b - a for a, b in row["spans"])
            if best is None or width < best[0]:
                best = (width, row, "line")
    if best:
        return {"row": best[1], "match": "line"}
    if label_text:
        target = _words(label_text)
        scored = []
        for row in reported:
            sim = _jaccard(target, _words(row["text"]))
            if sim >= 0.5:
                scored.append((sim, row))
        if scored:
            scored.sort(key=lambda t: -t[0])
            return {"row": scored[0][1], "match": "text", "similarity": round(scored[0][0], 2)}
    return None


_STOP = {"the", "a", "an", "and", "or", "of", "to", "in", "for", "with", "that", "this",
         "is", "are", "be", "it", "on", "as", "at", "by", "all", "you", "your", "do",
         "not", "always", "never", "should", "must"}


def _words(text: str) -> set:
    text = re.sub(r"[^a-z0-9\s./_-]", " ", (text or "").lower())
    return {w for w in text.split() if w and w not in _STOP and len(w) > 2}


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)
