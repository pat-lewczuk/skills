"""Deterministic checks — the cheap, reliable half of the score.

A check is a small JSON object in a case file:

    {"id": "original-untouched", "type": "file_unchanged", "path": "AGENTS.md",
     "metric": "safety", "weight": 3, "gate": true,
     "why": "the skill promises it never edits in place"}

`metric` says which bucket the result lands in, `weight` how much it counts inside that
bucket, and `gate: true` makes a failure zero the whole case. Everything a check needs comes
from the sandbox after the run, the pre-run copy of the workspace, and the transcript — so
checks are re-runnable for free against a stored run.

Write the expensive, subjective criteria as rubric items instead (see rubric.py). Anything a
regex can settle belongs here: it costs nothing and never drifts.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

TYPES = (
    "file_exists", "file_absent", "file_unchanged", "file_changed",
    "file_matches", "file_not_matches", "output_matches", "output_not_matches",
    "file_size_ratio", "json_valid", "command", "tool_used", "tool_not_used",
    "skill_fired", "skill_not_fired", "files_created_max",
)

# A handler returns SKIP when the check does not apply to what the run produced. Skipped
# checks count toward neither side of their metric.
SKIP = "skip"


class Context:
    """Everything a check can see."""

    def __init__(self, sandbox: Path, originals: dict, meta: dict,
                 created: list, modified: list):
        self.sandbox = sandbox
        self.originals = originals          # relpath -> text, as the case shipped it
        self.meta = meta                    # transcript summary
        self.created = created
        self.modified = modified

    def resolve(self, pattern: str) -> Path | None:
        """First match for a path or glob, or None."""
        direct = self.sandbox / pattern
        if direct.exists():
            return direct
        hits = sorted(self.sandbox.glob(pattern))
        return hits[0] if hits else None

    def read(self, pattern: str) -> str | None:
        p = self.resolve(pattern)
        if p is None or not p.is_file():
            return None
        return p.read_text(encoding="utf-8", errors="replace")

    @property
    def output(self) -> str:
        return self.meta.get("final_text", "") or ""

    def tool_calls(self) -> list:
        return self.meta.get("tool_calls", []) or []


def run_check(spec: dict, ctx: Context) -> dict:
    kind = spec.get("type")
    fn = _HANDLERS.get(kind)
    if fn is None:
        return _fail(spec, f"unknown check type {kind!r}")
    try:
        passed, detail = fn(spec, ctx)
    except Exception as exc:                      # a broken check must not kill the run
        return _fail(spec, f"check raised {type(exc).__name__}: {exc}")
    return {
        "id": spec.get("id", kind),
        "type": kind,
        "metric": spec.get("metric", "correctness"),
        "weight": float(spec.get("weight", 1)),
        "gate": bool(spec.get("gate", False)),
        "passed": passed is not SKIP and bool(passed),
        "skipped": passed is SKIP,
        "detail": detail,
        "why": spec.get("why", ""),
    }


def _fail(spec: dict, detail: str) -> dict:
    return {"id": spec.get("id", "?"), "type": spec.get("type"),
            "metric": spec.get("metric", "correctness"),
            "weight": float(spec.get("weight", 1)), "gate": bool(spec.get("gate", False)),
            "passed": False, "skipped": False, "detail": detail, "why": spec.get("why", "")}


def _rx(spec: dict) -> re.Pattern:
    flags = 0
    for f in (spec.get("flags") or "im"):
        flags |= {"i": re.I, "m": re.M, "s": re.S}.get(f, 0)
    return re.compile(spec["pattern"], flags)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


# --------------------------------------------------------------------------- handlers


def _file_exists(spec, ctx):
    p = ctx.resolve(spec["path"])
    return (p is not None), (f"found {p.relative_to(ctx.sandbox)}" if p else
                             f"no file matching {spec['path']}")


def _file_absent(spec, ctx):
    p = ctx.resolve(spec["path"])
    return (p is None), ("absent" if p is None else
                         f"{p.relative_to(ctx.sandbox)} exists but should not")


def _file_unchanged(spec, ctx):
    rel = spec["path"]
    before = ctx.originals.get(rel)
    if before is None:
        return False, f"{rel} was not in the case workspace, so 'unchanged' is meaningless"
    after = ctx.read(rel)
    if after is None:
        return False, f"{rel} was deleted"
    return _norm(before) == _norm(after), ("unchanged" if _norm(before) == _norm(after)
                                           else f"{rel} was modified in place")


def _file_changed(spec, ctx):
    rel = spec["path"]
    before, after = ctx.originals.get(rel), ctx.read(rel)
    if after is None:
        return False, f"{rel} does not exist"
    return _norm(before or "") != _norm(after), "changed" if before != after else "unchanged"


def _file_matches(spec, ctx):
    text = ctx.read(spec["path"])
    if text is None:
        return False, f"no file matching {spec['path']}"
    m = _rx(spec).search(text)
    return bool(m), (f"matched {m.group(0)[:60]!r}" if m else
                     f"{spec['pattern']!r} not found in {spec['path']}")


def _file_not_matches(spec, ctx):
    text = ctx.read(spec["path"])
    if text is None:
        # No file, so nothing can contain the forbidden thing. Counting that as a pass would
        # pay an agent that produced nothing at all — the single easiest way to inflate a
        # suite. Skip instead: it contributes to neither side of the metric, and a separate
        # file_exists check owns the "did it produce anything" question.
        return SKIP, f"{spec['path']} absent — check does not apply"
    m = _rx(spec).search(text)
    return (not m), ("clean" if not m else f"found forbidden {m.group(0)[:60]!r}")


def _output_matches(spec, ctx):
    m = _rx(spec).search(ctx.output)
    return bool(m), (f"matched {m.group(0)[:60]!r}" if m else
                     f"{spec['pattern']!r} not in the final response")


def _output_not_matches(spec, ctx):
    m = _rx(spec).search(ctx.output)
    return (not m), ("clean" if not m else f"found forbidden {m.group(0)[:60]!r}")


def _file_size_ratio(spec, ctx):
    text = ctx.read(spec["path"])
    if text is None:
        return False, f"no file matching {spec['path']}"
    base = ctx.originals.get(spec["vs"]) or ctx.read(spec["vs"])
    if not base:
        return False, f"reference file {spec['vs']} not found"
    ratio = len(text) / max(1, len(base))
    lo, hi = float(spec.get("min", 0)), float(spec.get("max", 10))
    return lo <= ratio <= hi, f"ratio {ratio:.2f} vs allowed {lo}–{hi}"


def _json_valid(spec, ctx):
    text = ctx.read(spec["path"])
    if text is None:
        return False, f"no file matching {spec['path']}"
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return False, f"invalid JSON: {exc}"
    missing = [k for k in spec.get("required_keys", [])
               if not isinstance(data, dict) or k not in data]
    return not missing, ("valid" if not missing else f"missing keys {missing}")


def _command(spec, ctx):
    proc = subprocess.run(spec["run"], shell=True, cwd=str(ctx.sandbox),
                          capture_output=True, text=True,
                          timeout=int(spec.get("timeout", 120)))
    want = int(spec.get("expect_exit", 0))
    tail = (proc.stderr or proc.stdout or "")[-200:].strip()
    return proc.returncode == want, f"exit {proc.returncode} (wanted {want}) {tail}"


def _tool_used(spec, ctx):
    hits = _tool_hits(spec, ctx)
    return bool(hits), (f"{len(hits)} call(s)" if hits else f"{spec['name']} never called")


def _tool_not_used(spec, ctx):
    hits = _tool_hits(spec, ctx)
    return (not hits), ("not used" if not hits else
                        f"{spec['name']} called {len(hits)}x: {hits[0][:80]}")


def _tool_hits(spec, ctx) -> list:
    pat = re.compile(spec["input_pattern"], re.I) if spec.get("input_pattern") else None
    out = []
    for c in ctx.tool_calls():
        if spec.get("name") and c.get("name") != spec["name"]:
            continue
        blob = json.dumps(c.get("input", {}))
        if pat and not pat.search(blob):
            continue
        out.append(blob)
    return out


def _skill_fired(spec, ctx):
    return bool(ctx.meta.get("triggered")), ("skill fired" if ctx.meta.get("triggered")
                                             else "skill did not fire")


def _skill_not_fired(spec, ctx):
    return (not ctx.meta.get("triggered")), ("stayed quiet" if not ctx.meta.get("triggered")
                                             else "skill fired when it should not have")


def _files_created_max(spec, ctx):
    n = int(spec.get("n", 3))
    ignore = [re.compile(p) for p in spec.get("ignore", [])]
    stray = [f for f in ctx.created if not any(p.search(f) for p in ignore)]
    return len(stray) <= n, f"{len(stray)} file(s) created, limit {n}: {stray[:6]}"


_HANDLERS = {
    "file_exists": _file_exists, "file_absent": _file_absent,
    "file_unchanged": _file_unchanged, "file_changed": _file_changed,
    "file_matches": _file_matches, "file_not_matches": _file_not_matches,
    "output_matches": _output_matches, "output_not_matches": _output_not_matches,
    "file_size_ratio": _file_size_ratio, "json_valid": _json_valid,
    "command": _command, "tool_used": _tool_used, "tool_not_used": _tool_not_used,
    "skill_fired": _skill_fired, "skill_not_fired": _skill_not_fired,
    "files_created_max": _files_created_max,
}


def validate_spec(spec: dict) -> list:
    """Problems with a check definition, before any run happens."""
    errs = []
    kind = spec.get("type")
    if kind not in TYPES:
        return [f"unknown type {kind!r} (expected one of {', '.join(TYPES)})"]
    need = {
        "file_exists": ["path"], "file_absent": ["path"], "file_unchanged": ["path"],
        "file_changed": ["path"], "file_matches": ["path", "pattern"],
        "file_not_matches": ["path", "pattern"], "output_matches": ["pattern"],
        "output_not_matches": ["pattern"], "file_size_ratio": ["path", "vs"],
        "json_valid": ["path"], "command": ["run"], "tool_used": ["name"],
        "tool_not_used": ["name"],
    }.get(kind, [])
    for key in need:
        if not spec.get(key):
            errs.append(f"{kind} needs {key!r}")
    for key in ("pattern", "input_pattern"):
        if spec.get(key):
            try:
                re.compile(spec[key])
            except re.error as exc:
                errs.append(f"bad regex in {key}: {exc}")
    return errs
