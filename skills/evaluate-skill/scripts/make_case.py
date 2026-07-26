#!/usr/bin/env python3
"""Materialise a case from a spec — for turning what a user described into a real case.

    python3 make_case.py --into evals/my-skill spec.json
    cat spec.json | python3 make_case.py --into evals/my-skill -

The spec is one JSON object: the case fields, plus a `workspace` key saying where the
sandbox files come from. Everything outside `workspace` is written to `case.json` as-is.

    {
      "id": "payout-incident",
      "split": "train",
      "prompt": "what the user actually asked for, in their words",
      "description": "what this case is here to catch",
      "workspace": {
        "copy_from": "~/work/ledger",           // optional: a real project
        "include": ["AGENTS.md", "src/**/*.ts"], // optional: globs, default everything
        "files": {"README.md": "inline content"} // optional: written after the copy
      },
      "checks": [ ... ],
      "rubric": [ ... ]
    }

Copying from a real project is where the sharpest cases come from and also where secrets
leak. Anything that looks like a credential is skipped and reported, as are large files and
the usual build directories — but **read the file list it prints** before committing. This
script cannot know that `config/staging.json` holds a live token.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import shutil
import sys
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build",
             ".next", "target", ".pytest_cache", ".mypy_cache", ".ruff_cache", "vendor"}
SECRET_NAMES = ("*.pem", "*.key", "*.p12", "*.pfx", "id_rsa*", "id_ed25519*", ".env",
                ".env.*", "*.env", "credentials*", "*secret*", "*token*", "*.keystore")
MAX_FILE_BYTES = 120_000
MAX_FILES = 60


def looks_secret(rel: str) -> bool:
    name = Path(rel).name.lower()
    return any(fnmatch.fnmatch(name, pat) for pat in SECRET_NAMES)


def gather(src: Path, includes: list) -> tuple:
    """(kept, skipped) relative paths under src."""
    kept, skipped = [], []
    for p in sorted(src.rglob("*")):
        if not p.is_file():
            continue
        rel = str(p.relative_to(src))
        if any(part in SKIP_DIRS for part in p.relative_to(src).parts):
            continue
        if includes and not any(fnmatch.fnmatch(rel, pat) or
                                fnmatch.fnmatch(rel, pat.rstrip("/") + "/*")
                                for pat in includes):
            continue
        if looks_secret(rel):
            skipped.append((rel, "looks like a credential"))
            continue
        if p.stat().st_size > MAX_FILE_BYTES:
            skipped.append((rel, f"{p.stat().st_size // 1024}KB, over the size limit"))
            continue
        kept.append(rel)
    return kept, skipped


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("spec", help="path to a spec JSON file, or - for stdin")
    ap.add_argument("--into", required=True, help="the eval suite root")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    text = sys.stdin.read() if args.spec == "-" else Path(args.spec).read_text(encoding="utf-8")
    try:
        spec = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"error: spec is not valid JSON: {exc}")

    if not spec.get("id"):
        raise SystemExit("error: spec needs an id")
    root = Path(args.into).expanduser().resolve()
    if not (root / "config.json").exists():
        raise SystemExit(f"error: {root} is not an eval suite (no config.json) — "
                         f"run scaffold.py first")

    cdir = root / "cases" / spec["id"]
    if cdir.exists() and not args.force:
        raise SystemExit(f"error: {cdir} already exists (use --force)")
    ws = cdir / "workspace"
    ws.mkdir(parents=True, exist_ok=True)

    workspace = spec.pop("workspace", {}) or {}
    written, skipped = [], []

    src_raw = workspace.get("copy_from")
    if src_raw:
        src = Path(src_raw).expanduser().resolve()
        if not src.is_dir():
            raise SystemExit(f"error: copy_from {src} is not a directory")
        kept, skipped = gather(src, workspace.get("include") or [])
        if len(kept) > MAX_FILES:
            raise SystemExit(
                f"error: {len(kept)} files matched, limit is {MAX_FILES}. A case workspace "
                f"is a small realistic slice, not a repo — narrow `include`.")
        for rel in kept:
            dest = ws / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src / rel, dest)
            written.append(rel)

    for rel, content in (workspace.get("files") or {}).items():
        dest = ws / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        if rel not in written:
            written.append(rel)

    if not written:
        (ws / ".gitkeep").touch()

    spec.setdefault("kind", "task")
    spec.setdefault("split", "train")
    spec.setdefault("invoke", "explicit")
    (cdir / "case.json").write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")

    print(f"created {cdir}")
    print(f"  split {spec['split']} · {len(spec.get('checks', []))} check(s) · "
          f"{len(spec.get('rubric', []))} rubric item(s)")
    print(f"  workspace: {len(written)} file(s)")
    for rel in written[:40]:
        print(f"    {rel}")
    if len(written) > 40:
        print(f"    … and {len(written) - 40} more")
    if skipped:
        print(f"  skipped {len(skipped)}:")
        for rel, why in skipped[:20]:
            print(f"    {rel} — {why}")
    if src_raw:
        print("\n  Copied from a real project. Read that file list before committing: this "
              "script skips obvious credentials by name, not by content.")
    print("\nnext: python3 harness/selftest.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
