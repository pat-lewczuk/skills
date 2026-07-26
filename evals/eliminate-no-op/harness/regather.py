#!/usr/bin/env python3
"""Re-derive a run's artifacts from the files it saved, without re-running the agents.

`run.py` copies every file the agent created or modified into `<case>/artifacts/`. When the
collector in `evallib/cases.py` changes — a new naming convention for the rewrite, say — this
replays that saved output through the current collector and rewrites `raw.json`, so an old
run can be re-graded instead of re-paid for.

    python3 harness/regather.py runs/<id>
    python3 harness/grade.py runs/<id>
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from evallib import cases as C  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def regather_case(case: dict, case_run_dir: Path) -> dict | None:
    raw_path = case_run_dir / "raw.json"
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    if raw.get("kind") == "trigger":
        return None
    saved = case_run_dir / "artifacts"
    if not saved.exists():
        return None

    with tempfile.TemporaryDirectory() as tmp:
        sandbox = Path(tmp) / "sandbox"
        C.build_sandbox(case, sandbox)
        before = C.snapshot(sandbox)
        for f in saved.iterdir():
            if not f.is_file():
                continue
            dest = sandbox / f.name.replace("__", "/")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(f.read_bytes())
        artifacts = C.collect_artifacts(case, sandbox, before, raw.get("meta", {}),
                                        Path(tmp) / "out")

    before_paths = (raw["artifacts"].get("report_path"), raw["artifacts"].get("rewrite_path"))
    raw["artifacts"] = artifacts
    if not raw_path.with_suffix(".json.bak").exists():
        raw_path.with_suffix(".json.bak").write_text(
            json.dumps(json.loads(raw_path.read_text(encoding="utf-8")), indent=2),
            encoding="utf-8")
    raw_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    return {"case": case["id"], "was": before_paths,
            "now": (artifacts["report_path"], artifacts["rewrite_path"])}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    args = ap.parse_args()
    run_dir = Path(args.run_dir).resolve()
    all_cases = {c["id"]: c for c in C.load_cases(ROOT)}

    for raw_path in sorted(run_dir.glob("*/raw.json")):
        case = all_cases.get(raw_path.parent.name)
        if not case:
            continue
        changed = regather_case(case, raw_path.parent)
        if changed and changed["was"] != changed["now"]:
            print(f"  [{changed['case']}] {changed['was']} -> {changed['now']}")
        elif changed:
            print(f"  [{changed['case']}] unchanged")
    print("\nre-run grade.py to score the repaired run")
    return 0


if __name__ == "__main__":
    sys.exit(main())
