# Scoreboard

Every candidate the loop has evaluated, newest last. `train` is the split the optimiser saw; `holdout` it never did. A candidate is accepted only if it gains on train without regressing on holdout.

| # | when | label | train | holdout | adjusted | SKILL.md | guard | verdict |
|---|---|---|---|---|---|---|---|---|
| 0 | 2026-07-26 14:56 | baseline | 0.9630 | 0.9752 | 0.9676 | 9772 | ok | baseline |
| 1 | 2026-07-26 15:05 | iter1 | — | — | — | 10161 | blocked | rejected |
| 2 | 2026-07-26 15:06 | baseline | 0.9630 | 0.9752 | 0.9676 | 9772 | ok | baseline |
| 3 | 2026-07-26 15:06 | iter1 | 0.9695 | — | — | 10161 | ok | rejected |

## Notes

- **0 baseline** — metric means — safety 0.99 · recall 0.98 · preservation 1.00 · compliance 0.99 · code accuracy 0.89 · calibration 1.00
- **1 iter1** — overfit guard: .cursorrules, node_modules — later confirmed a guard false positive: `.cursorrules` was already in the skill's own description and `node_modules` appears in several fixtures. The guard now exempts tokens present in the baseline skill or in more than one case; this same candidate passes cleanly as entry 3.
- **2 baseline** — metric means — safety 0.99 · recall 0.98 · preservation 1.00 · compliance 0.99 · code accuracy 0.89 · calibration 1.00 (re-run of the same measured baseline after the guard fix)
- **3 iter1** — train gain +0.0065 below the 0.01 threshold. It did fix real things — code_accuracy 0.889 -> 0.949, stale-migration 0.95 -> 1.00 — but the description grew 155 -> 252 always-in-context tokens, and the trigger over-fire count did not move: one prompt still fires wrongly, just a different one. Below threshold is the right call at n=1.
