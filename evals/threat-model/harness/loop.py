#!/usr/bin/env python3
"""The improvement loop: measure, revise, re-measure, keep or discard.

One iteration:

    digest the current best run  ->  optimiser edits a copy of the skill
    -> overfit guard             ->  smoke test (the skill's own scripts still run)
    -> re-run the train split    ->  compare
    -> if train improved, re-run the holdout split
    -> accept only if the holdout did not regress

A candidate is accepted only when it wins on cases it was tuned against *and* holds up on
cases it has never seen. Everything lands in `scoreboard.md`, and the installed skill is
never touched unless you pass --promote.

    python3 harness/loop.py --iterations 2
    python3 harness/loop.py --iterations 2 --baseline-run runs/<id>
    python3 harness/loop.py --iterations 1 --evaluate /path/to/candidate-skill
    python3 harness/loop.py --iterations 1 --promote
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import grade  # noqa: E402
from evallib import cases as C, guard  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable


def run_suite(skill_dir: Path, label: str, split: str | None, model: str | None) -> Path:
    run_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{label}"
    cmd = [PY, str(ROOT / "harness" / "run.py"), "--skill-dir", str(skill_dir),
           "--label", label, "--run-dir", run_id, "--no-grade"]
    if split:
        cmd += ["--split", split]
    if model:
        cmd += ["--model", model]
    subprocess.run(cmd, cwd=str(ROOT), check=True)
    run_dir = ROOT / "runs" / run_id
    grade.grade_run(run_dir)
    return run_dir


def summary(run_dir: Path) -> dict:
    return json.loads((run_dir / "scores.json").read_text(encoding="utf-8"))["summary"]


def smoke_test(skill_dir: Path, cfg: dict) -> tuple:
    """Whatever the skill ships must still run. Configured per suite because only the
    suite knows what 'still works' means for this skill."""
    cmd = cfg.get("smoke_test")
    if not cmd:
        return True, "no smoke_test configured"
    proc = subprocess.run(cmd, shell=True, cwd=str(skill_dir), capture_output=True,
                          text=True, timeout=300)
    return proc.returncode == 0, (proc.stderr or proc.stdout)[-500:]


def append_scoreboard(entry: dict) -> None:
    path = ROOT / "scoreboard.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    data.append(entry)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    render_scoreboard(data)


def render_scoreboard(data: list | None = None) -> None:
    if data is None:
        data = json.loads((ROOT / "scoreboard.json").read_text(encoding="utf-8"))
    lines = ["# Scoreboard", "",
             "Every candidate the loop has evaluated, newest last. `train` is the split the "
             "optimiser saw; `holdout` it never did. A candidate is accepted only if it "
             "gains on train without regressing on holdout.", "",
             "| # | when | label | train | holdout | SKILL.md | guard | verdict |",
             "|---|---|---|---|---|---|---|---|"]
    for i, e in enumerate(data):
        lines.append(f"| {i} | {e['when']} | {e['label']} | {_f(e.get('train'))} | "
                     f"{_f(e.get('holdout'))} | {e.get('skill_md_chars', '—')} | "
                     f"{'ok' if e.get('guard_ok') else 'blocked'} | {e['verdict']} |")
    lines += ["", "## Notes", ""]
    for i, e in enumerate(data):
        if e.get("reason"):
            lines.append(f"- **{i} {e['label']}** — {e['reason']}")
    (ROOT / "scoreboard.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _f(v) -> str:
    return "—" if v is None else f"{v:.4f}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iterations", type=int, default=None)
    ap.add_argument("--baseline-run", default=None)
    ap.add_argument("--skill-dir", default=None)
    ap.add_argument("--model", default=None)
    ap.add_argument("--promote", action="store_true")
    ap.add_argument("--evaluate", default=None,
                    help="evaluate this skill dir as the first candidate instead of "
                         "generating one")
    args = ap.parse_args()

    cfg = C.load_config(ROOT)
    loop_cfg = cfg.get("loop", {})
    iterations = args.iterations or loop_cfg.get("max_iterations", 3)
    min_gain = loop_cfg.get("accept_min_train_gain", 0.01)
    max_regress = loop_cfg.get("accept_max_holdout_regression", 0.02)

    import run as runner
    installed = runner.resolve_skill(cfg, args.skill_dir)
    best_skill = installed

    if args.baseline_run:
        best_run = Path(args.baseline_run).resolve()
        if not (best_run / "scores.json").exists():
            grade.grade_run(best_run)
    else:
        print("=== baseline: full suite ===")
        best_run = run_suite(best_skill, "baseline", None, args.model)

    base = summary(best_run)
    best_train, best_holdout = base["train_score"], base["holdout_score"]
    if best_train is None or best_holdout is None:
        print("error: the baseline must cover both splits", file=sys.stderr)
        return 1

    append_scoreboard({
        "when": time.strftime("%Y-%m-%d %H:%M"), "label": "baseline",
        "train": best_train, "holdout": best_holdout, "guard_ok": True,
        "skill_md_chars": len((best_run / "skill-snapshot" / "SKILL.md")
                              .read_text(encoding="utf-8")),
        "verdict": "baseline", "run_dir": str(best_run),
        "reason": "metric means — " + " · ".join(
            f"{k} {v:.2f}" for k, v in base["metric_means"].items() if v is not None),
    })
    print(f"\nbaseline: train {best_train} · holdout {best_holdout}")

    for i in range(1, iterations + 1):
        label = f"iter{i}"
        if i == 1 and args.evaluate:
            cand_skill = Path(args.evaluate).resolve()
            print(f"\n=== iteration {i}: evaluating {cand_skill} ===")
        else:
            print(f"\n=== iteration {i}: revise ===")
            cand_root = best_run / f"candidate-{label}"
            subprocess.run([PY, str(ROOT / "harness" / "improve.py"), "--run", str(best_run),
                            "--candidate", str(cand_root)]
                           + (["--model", args.model] if args.model else []),
                           cwd=str(ROOT), check=False)
            cand_skill = cand_root / cfg["target_skill"]
        if not (cand_skill / "SKILL.md").exists():
            print("no candidate produced; stopping")
            break

        verdict = guard.check(best_run / "skill-snapshot", cand_skill, ROOT / "cases",
                              [c["id"] for c in C.load_cases(ROOT)])
        entry = {"when": time.strftime("%Y-%m-%d %H:%M"), "label": label,
                 "skill_md_chars": len((cand_skill / "SKILL.md").read_text(encoding="utf-8")),
                 "guard_ok": verdict["ok"], "candidate": str(cand_skill),
                 "train": None, "holdout": None}

        if not verdict["ok"]:
            hits = ", ".join(sorted({v["hit"] for v in verdict["violations"]})[:6])
            entry.update({"verdict": "rejected", "reason": f"overfit guard: {hits}"})
            append_scoreboard(entry)
            print(f"rejected — candidate memorised fixture content: {hits}")
            continue

        ok, err = smoke_test(cand_skill, cfg)
        if not ok:
            entry.update({"verdict": "rejected", "reason": f"smoke test failed: {err[:200]}"})
            append_scoreboard(entry)
            print(f"rejected — smoke test failed:\n{err}")
            continue

        print(f"\n=== iteration {i}: re-measure train ===")
        train_run = run_suite(cand_skill, f"{label}-train", "train", args.model)
        cand_train = summary(train_run)["train_score"]
        gain = cand_train - best_train
        entry.update({"train": cand_train, "run_dir": str(train_run)})
        print(f"train {cand_train} vs {best_train} (gain {gain:+.4f})")

        if gain < min_gain:
            entry.update({"verdict": "rejected",
                          "reason": f"train gain {gain:+.4f} below the {min_gain} threshold"})
            append_scoreboard(entry)
            continue

        print(f"\n=== iteration {i}: check holdout ===")
        hold_run = run_suite(cand_skill, f"{label}-holdout", "holdout", args.model)
        cand_hold = summary(hold_run)["holdout_score"]
        regress = best_holdout - cand_hold
        entry.update({"holdout": cand_hold, "holdout_run_dir": str(hold_run)})
        print(f"holdout {cand_hold} vs {best_holdout} (change {-regress:+.4f})")

        if regress > max_regress:
            entry.update({"verdict": "rejected",
                          "reason": f"train +{gain:.4f} but holdout -{regress:.4f}: the "
                                    f"revision fits the training cases, not the job"})
            append_scoreboard(entry)
            continue

        entry.update({"verdict": "accepted",
                      "reason": f"train {gain:+.4f}, holdout {-regress:+.4f}"})
        append_scoreboard(entry)
        print("accepted")
        best_skill, best_train, best_holdout, best_run = (cand_skill, cand_train,
                                                          cand_hold, train_run)
        shutil.copytree(cand_skill, best_run / "skill-snapshot", dirs_exist_ok=True,
                        ignore=C.IGNORE)

    print(f"\nbest: {best_skill}\n  train {best_train} · holdout {best_holdout}")
    if args.promote and best_skill.resolve() != installed.resolve():
        shutil.rmtree(installed)
        shutil.copytree(best_skill, installed, ignore=C.IGNORE)
        print(f"promoted into {installed} — review with `git diff` before committing")
    elif args.promote:
        print("nothing to promote: no candidate beat the baseline")
    print(f"scoreboard: {ROOT / 'scoreboard.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
