"""Case loading, sandbox construction, and artifact collection."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

IGNORE = shutil.ignore_patterns(".DS_Store", "__pycache__", "*.pyc")
# Files the agent is expected to produce, so they never count as stray output.
ARTIFACT_HINTS = ("report", "rewrite", "analysis.json")


def cases_dir(root: Path) -> Path:
    return root / "cases"


def load_cases(root: Path, ids: list | None = None, split: str | None = None) -> list:
    out = []
    for case_json in sorted(cases_dir(root).glob("*/case.json")):
        case = json.loads(case_json.read_text(encoding="utf-8"))
        case["id"] = case.get("id", case_json.parent.name)
        case["dir"] = str(case_json.parent)
        if ids and case["id"] not in ids:
            continue
        if split and case.get("split", "train") != split:
            continue
        out.append(case)
    return out


def load_labels(case: dict) -> list:
    p = Path(case["dir"]) / "labels.json"
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    return data["labels"] if isinstance(data, dict) else data


def build_sandbox(case: dict, dest: Path) -> Path:
    """Fresh copy of the case workspace. Never reuse — agents leave state behind."""
    if dest.exists():
        shutil.rmtree(dest)
    src = Path(case["dir"]) / "workspace"
    shutil.copytree(src, dest, ignore=IGNORE)
    return dest


def snapshot(workspace: Path) -> dict:
    """path -> sha256, for detecting in-place edits and new files."""
    out = {}
    for p in sorted(workspace.rglob("*")):
        if p.is_file() and ".claude" not in p.parts:
            rel = str(p.relative_to(workspace))
            out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""


def collect_artifacts(case: dict, sandbox: Path, before: dict, meta: dict,
                      out_dir: Path) -> dict:
    """Find the report and the rewrite, and check the original survived untouched."""
    target_rel = case["target"]
    target = sandbox / target_rel
    original = _read(Path(case["dir"]) / "workspace" / target_rel)
    after = _read(target) if target.exists() else None

    now = snapshot(sandbox)
    created = [rel for rel in now if rel not in before]
    modified = [rel for rel in now if rel in before and now[rel] != before[rel]]

    report_path = _pick(sandbox, created, ("report",), (".md",))
    # No suffix filter: a dotfile target legitimately produces `.cursorrules.rewrite`, whose
    # suffix is `.rewrite`. The name needle is discriminating enough on its own.
    rewrite_path = _pick(sandbox, created, ("rewrite",), (),
                         exclude=(report_path.name if report_path else "",))
    if rewrite_path is None:
        stem = Path(target_rel).stem
        rewrite_path = _pick(sandbox, created, (stem.lower(),), (".md",),
                             exclude=(report_path.name if report_path else "",))

    report_text = _read(report_path) if report_path else ""
    report_from_file = bool(report_text.strip())
    if not report_from_file:
        tail = meta.get("final_text", "") or ""
        if "|" in tail and any(k in tail.lower() for k in ("cut", "keep", "finding")):
            report_text = tail

    tgt = Path(target_rel)
    expected_names = {f"{tgt.stem}.rewrite{tgt.suffix}", f"{tgt.stem}.rewrite.md",
                      f"{tgt.name}.rewrite", f"{tgt.name}.rewrite.md"}
    rewrite_ok = bool(rewrite_path and rewrite_path.name in expected_names
                      and rewrite_path.parent == target.parent)

    # Keep the agent's real output next to the transcript for later inspection.
    keep = out_dir / "artifacts"
    keep.mkdir(parents=True, exist_ok=True)
    for rel in created + modified:
        src = sandbox / rel
        if src.is_file() and src.stat().st_size < 400_000:
            dst = keep / rel.replace("/", "__")
            dst.write_bytes(src.read_bytes())

    return {
        "report": report_text,
        "report_path": str(report_path.relative_to(sandbox)) if report_path else None,
        "report_from_file": report_from_file,
        "rewrite": _read(rewrite_path) if rewrite_path else "",
        "rewrite_path": str(rewrite_path.relative_to(sandbox)) if rewrite_path else None,
        "rewrite_path_ok": rewrite_ok,
        "original": original,
        "original_after": after,
        "files_created": created,
        "files_modified": modified,
        "triggered": meta.get("triggered"),
        "read_taxonomy": meta.get("read_taxonomy"),
        "ran_analyze": meta.get("ran_analyze"),
    }


def _pick(sandbox: Path, created: list, name_needles: tuple, suffixes: tuple,
          exclude: tuple = ()) -> Path | None:
    best = None
    for rel in created:
        p = sandbox / rel
        if p.name in exclude:
            continue
        low = p.name.lower()
        if not any(n in low for n in name_needles):
            continue
        if suffixes and p.suffix.lower() not in suffixes:
            continue
        # Shallowest match wins: a report beside the target beats one in a subdir.
        depth = len(Path(rel).parts)
        if best is None or depth < best[0]:
            best = (depth, p)
    return best[1] if best else None
