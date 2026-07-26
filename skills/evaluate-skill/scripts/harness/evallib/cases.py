"""Case loading, sandbox construction, and artifact collection."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

IGNORE = shutil.ignore_patterns(".DS_Store", "__pycache__", "*.pyc", ".git")
MAX_KEEP_BYTES = 400_000


def load_config(root: Path) -> dict:
    p = root / "config.json"
    if not p.exists():
        raise SystemExit(f"error: no config.json in {root}")
    return json.loads(p.read_text(encoding="utf-8"))


def load_cases(root: Path, ids: list | None = None, split: str | None = None) -> list:
    out = []
    for case_json in sorted((root / "cases").glob("*/case.json")):
        case = json.loads(case_json.read_text(encoding="utf-8"))
        case["id"] = case.get("id", case_json.parent.name)
        case["dir"] = str(case_json.parent)
        if ids and case["id"] not in ids:
            continue
        if split and case.get("split", "train") != split:
            continue
        out.append(case)
    return out


def workspace(case: dict) -> Path:
    return Path(case["dir"]) / "workspace"


def build_sandbox(case: dict, dest: Path) -> Path:
    """Fresh copy of the case workspace. Never reuse — agents leave state behind."""
    if dest.exists():
        shutil.rmtree(dest)
    src = workspace(case)
    if src.exists():
        shutil.copytree(src, dest, ignore=IGNORE)
    else:
        dest.mkdir(parents=True)
    return dest


def snapshot(sandbox: Path) -> dict:
    """relpath -> sha256 for every file outside .claude/."""
    out = {}
    for p in sorted(sandbox.rglob("*")):
        if p.is_file() and ".claude" not in p.parts:
            out[str(p.relative_to(sandbox))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def originals(case: dict) -> dict:
    """relpath -> text, as the case shipped it. Text files only."""
    out = {}
    src = workspace(case)
    if not src.exists():
        return out
    for p in sorted(src.rglob("*")):
        if not p.is_file() or p.stat().st_size > MAX_KEEP_BYTES:
            continue
        try:
            out[str(p.relative_to(src))] = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
    return out


def collect(case: dict, sandbox: Path, before: dict, meta: dict, out_dir: Path) -> dict:
    """What the agent left behind, plus copies of it for later inspection."""
    now = snapshot(sandbox)
    created = [rel for rel in now if rel not in before]
    modified = [rel for rel in now if rel in before and now[rel] != before[rel]]
    deleted = [rel for rel in before if rel not in now]

    keep = out_dir / "artifacts"
    keep.mkdir(parents=True, exist_ok=True)
    for rel in created + modified:
        src = sandbox / rel
        if src.is_file() and src.stat().st_size <= MAX_KEEP_BYTES:
            (keep / rel.replace("/", "__")).write_bytes(src.read_bytes())

    return {"files_created": created, "files_modified": modified, "files_deleted": deleted,
            "final_text": meta.get("final_text", ""), "triggered": meta.get("triggered")}


def restore_sandbox(case: dict, case_run_dir: Path, dest: Path) -> Path:
    """Rebuild a post-run sandbox from the saved artifacts, so a graded run can be
    re-checked for free after the checks change."""
    build_sandbox(case, dest)
    saved = case_run_dir / "artifacts"
    if saved.exists():
        for f in saved.iterdir():
            if f.is_file():
                target = dest / f.name.replace("__", "/")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(f.read_bytes())
    raw = json.loads((case_run_dir / "raw.json").read_text(encoding="utf-8"))
    for rel in raw.get("artifacts", {}).get("files_deleted", []):
        p = dest / rel
        if p.exists():
            p.unlink()
    return dest
