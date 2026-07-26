# Eval suite: `eliminate-no-op`

Measures whether the skill actually does its job, then uses the failures to revise the skill
and re-measures to decide whether the revision was real.

The thing being tested is a judgement call — which lines in an instruction file are dead
weight — so the suite is built around labelled fixtures. Each case is a small synthetic repo
with an instruction file whose every consequential directive has a known-correct verdict, and
74 of those 179 directives are **traps**: lines that read like platitudes but are
load-bearing. Cutting one costs three times what missing a genuine no-op does, because that
is the real cost ordering for a user.

```
harness/run.py       run cases -> runs/<id>/            (costs money: one agent per case)
harness/grade.py     runs/<id>/ -> scores.json          (free, deterministic, re-runnable)
harness/judge.py     rewrite fidelity, model-judged     (optional, cheap)
harness/improve.py   scores.json -> failure digest -> candidate skill revision
harness/loop.py      the whole loop with accept/reject and a scoreboard
harness/selftest.py  validates the graders without spending anything
harness/report_html.py  scores.json -> results.html (the dashboard below)
harness/screenshot.sh   results.html -> docs/results-{light,dark}.png
harness/regather.py     re-derive artifacts from a past run after a collector fix
```

## Run it

```bash
python3 harness/selftest.py                      # first: check the graders still work
python3 harness/run.py                           # full suite, current skill (~$6, ~10 min)
python3 harness/run.py --cases lean-cli          # one case
python3 harness/run.py --split train
python3 harness/grade.py runs/<id>               # re-grade without re-running
python3 harness/judge.py runs/<id> && python3 harness/grade.py runs/<id>
python3 harness/loop.py --iterations 2           # measure, revise, re-measure
python3 harness/loop.py --iterations 2 --promote  # ...and install a winner
```

Each case runs in a throwaway sandbox: the case workspace is copied, the skill under test is
installed as a project skill, and `claude -p` is invoked with `--permission-mode
bypassPermissions` inside it. Nothing touches your working tree. `runs/` is gitignored.

## Cases

| Case | Split | What it is there to catch |
|---|---|---|
| `bloated-webapp` | train | The canonical audit. 129 lines, every no-op family present, 12 traps, two dead references, six rules already enforced by prettier/eslint/tsconfig/husky. |
| `lean-cli` | train | Over-cutting. 40 lines that are almost all thresholds, scope boundaries and recovery paths, with exactly two real no-ops. The correct answer is "this file is healthy". |
| `duplicated-hierarchy` | train | Reading the whole hierarchy. Root `AGENTS.md` duplicates `CLAUDE.md` and `packages/api/AGENTS.md`; two rules belong in a nested file. Scores `MERGE`/`MOVE`, not `CUT`. |
| `stale-migration` | train | Repo evidence in both directions. Three transitions are genuinely finished; two that look identical are still live. Target is a `.cursorrules`, not markdown. |
| `trigger-suite` | train | The `description` field — the only always-in-context part of the skill. Five prompts that should fire it, four adjacent ones that should not. |
| `no-repo-paste` | holdout | Evidence-limited mode. No repo, so every path and tool reference must come back "unverified" rather than cut. |
| `skill-md-target` | holdout | Calibration by file type. A `SKILL.md` body gets a looser budget, but its 152-token description field is the most expensive line in the file. |
| `long-but-dense` | holdout | "Your file is long because your project is complicated." 93 dense lines, three planted platitudes; a large cut here is a failure even though the user asked for one. |

Holdout cases never enter the improvement digest. They exist to catch a revision that learned
the training files instead of the method.

### Adding a case

```
cases/<id>/
  case.json     kind, split, target, prompt, expect{}
  labels.json   one entry per consequential directive
  workspace/    the sandbox contents — instruction files, tooling config, real source files
```

A label is `{id, line, line_start?, line_end?, truth, accept?, codes, severity?, text,
must_keep_nouns?}`. `truth` is one of the skill's five verdicts. `severity: "trap"` marks a
load-bearing lookalike. `must_keep_nouns` are strings that must survive verbatim into the
rewrite. `expect.reduction_pct` is the defensible token-reduction band, `expect.must_mention`
regexes the report has to satisfy.

Two rules that keep the fixtures honest:

- **Tooling config must actually enforce what the label says it enforces.** An `N6` label needs
  the rule present in a real `.prettierrc`/eslint config/`tsconfig.json` in the workspace.
- **Nothing in a fixture may sabotage the workflow under test.** A fixture that says "never
  create new files" would block the rewrite step and score the skill on the wrong thing.

## Metrics

| Metric | Weight | What it measures |
|---|---|---|
| `safety` | 0.35 | Load-bearing directives that were *not* cut. Traps count triple. |
| `recall` | 0.25 | Genuine no-ops that got the right verdict. Conservative errors get partial credit; destructive ones get none. |
| `preservation` | 0.15 | Required commands, paths and thresholds surviving into the rewrite, times the judge's fidelity score if `judge.py` has run. |
| `compliance` | 0.12 | Report sections present, cuts reproduced verbatim, figures quantified, original untouched, rewrite written beside it, `expect.must_mention` satisfied. |
| `code_accuracy` | 0.08 | Correct N-code / L-code on directives that were otherwise classified right. |
| `calibration` | 0.05 | Token reduction inside the band this file deserves. |

Two hard gates zero a case regardless of everything else: **editing the target in place** and
**producing no report**. Both make the output unusable.

`judge.py` covers the one property no string comparison reaches: whether a rule that *survived*
quietly changed meaning. It gets the original, the rewrite, and the report, and is told that a
directive the report declares as CUT/MERGE/MOVE is never a loss — its removal is judged by the
labels. Without that framing it counts every deliberate cut of a dead path or a tool-enforced
rule as information loss, scores 0.65–0.95 on a clean audit, and pushes the loop toward cutting
less. Scoped properly it finds dropped qualifiers and invented parentheticals, and nothing else.

The suite aggregate then subtracts a **context penalty** proportional to `SKILL.md` growth
past the baseline. The skill's own subject is context economy; a candidate that scores better
by appending 300 lines of new rules has not improved it.

### Why the credit matrix is asymmetric

`CUT`-truth directives get partial credit for `TRIM`/`MERGE`/`MOVE` — the waste was seen, the
response was cautious. `KEEP`-truth directives get zero for `CUT` and nothing else counts. A
symmetric F1 would let a candidate trade a destroyed safety rule for two platitudes removed,
which is exactly the trade the skill exists to refuse.

## Measured baseline

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/results-dark.png">
  <img src="docs/results-light.png" alt="Results dashboard: adjusted suite score 0.9625, train 0.9579, holdout 0.9702. Zero of 74 load-bearing lines cut. Per-case meters from 0.88 to 1.00, metric means from 0.89 to 1.00, 179 labelled directives by verdict, grader calibration ranking perfect 1.00 / lazy 0.71 / butcher 0.54 / vandal 0.00, and the improvement-loop history.">
</picture>

`results.html` is the live version of the above — hover any row for the case brief or the
metric definition, and the same numbers are in a table at the bottom. Regenerate both from any
graded run:

```bash
python3 harness/report_html.py runs/<id>   # -> results.html
./harness/screenshot.sh                    # -> docs/results-{light,dark}.png
```

Full suite against the skill as committed, 2026-07-26, Opus, one sample per case, $5.90 plus
$0.30 for the judge:

| Case | Split | Score | Safety | Recall | Preserv | Compl | Code | Calib |
|---|---|---|---|---|---|---|---|---|
| lean-cli | train | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| bloated-webapp | train | 0.99 | 1.00 | 1.00 | 0.93 | 1.00 | 1.00 | 1.00 |
| duplicated-hierarchy | train | 0.99 | 1.00 | 1.00 | 1.00 | 0.98 | 0.85 | 1.00 |
| stale-migration | train | 0.94 | 0.97 | 0.94 | 0.90 | 0.98 | 0.78 | 1.00 |
| trigger-suite | train | 0.88 | fire 1.00 | quiet 0.75 | — | — | — | — |
| no-repo-paste | holdout | 0.99 | 1.00 | 1.00 | 0.98 | 1.00 | 0.89 | 1.00 |
| long-but-dense | holdout | 0.97 | 0.99 | 1.00 | 0.96 | 1.00 | 0.80 | 1.00 |
| skill-md-target | holdout | 0.95 | 0.96 | 0.91 | 0.96 | 0.99 | 0.91 | 1.00 |

**Adjusted 0.9625** · train 0.9579 · holdout 0.9702. (Without the judge: 0.9676 / 0.9630 /
0.9752 — `preservation` is the only metric it touches.)

Where the skill is weakest, in order:

- **Triggering.** It fires on one prompt that is ordinary engineering work, not an instruction
  audit. The description is the only thing in context at that moment, so this is a description
  problem.
- **Code accuracy** (0.89). Right verdict, wrong N-code — most often N1 where the line is
  really N2 or N10, since "be thorough" reads like a best practice but has no artifact at all.
- **Silent scope changes in the rewrite**, which only the judge sees. On `stale-migration` the
  rewrite compressed "New code must use `httpx`" into "HTTP calls use `httpx`, not `requests`",
  dropping the *new code* qualifier and widening the rule. On `no-repo-paste`, "focused and
  reasonably sized" survived as "focused" — the size constraint fell off a rule that was not
  supposed to change. Both are the exact failure the "subtractive edit" rule exists to prevent,
  and neither is visible to word-matching.
- **`SKILL.md` bodies.** It kept two of three interchangeable examples.

Safety is 0.99: 101 of the 179 labelled directives are load-bearing and 74 of those are traps
that read like platitudes. It cut none of them.

Two ground-truth labels were corrected against this run rather than the other way round. On
`duplicated-hierarchy` the audit kept the root copy of a duplicated rule and recommended
deleting the `CLAUDE.md` copy — deduplication has to pick a canonical home, and for a
repo-wide convention that home is the root file. On the same case it deliberately kept an auth
rule duplicated across two files and argued the trade in the report. Both were defensible and
the labels now accept them; the `note` fields record why.

## The improvement loop

```
  digest the current best run        failures with the auditor's own rationale, train split only
    -> optimiser edits a copy        never the installed skill
    -> overfit guard                 reject patches that memorise fixture content
    -> analyze.py smoke test         must still run stdlib-only on this repo's AGENTS.md
    -> re-run train, compare
    -> if train improved, run holdout
    -> accept only if holdout held
```

Thresholds live in `config.json` (`accept_min_train_gain`, `accept_max_holdout_regression`).
Every candidate, accepted or not, lands in `scoreboard.md` with the reason.

The first iteration, recorded in `scoreboard.md`, is a fair picture of what the loop does. The
optimiser made three method-level edits: it narrowed the description to exclude ordinary
engineering work, added a "choosing between codes" section to the taxonomy, and taught
`analyze.py` the names of instruction files. Train went 0.9630 → 0.9695 — real gains on
`code_accuracy` (0.889 → 0.949) and `stale-migration` (0.95 → 1.00), but **+0.0065 is under the
0.01 threshold, so it was rejected**. That is the intended behaviour at one sample per case: the
description also grew from 155 to 252 always-in-context tokens, and the over-fire count did not
move — one prompt still fires wrongly, just a different one. A gain that small is not
distinguishable from run-to-run variance, and the loop is built to say so rather than to
accumulate plausible-looking edits.

`--evaluate <dir>` runs the same guard/smoke/train/holdout gauntlet on a candidate you wrote by
hand, or on one the optimiser already produced.

The **overfit guard** (`harness/evallib/guard.py`) is the load-bearing part. Feed failures to a
model with edit access and it will happily write "the rule about port 4310 is load-bearing" —
scoring well, teaching nothing. The guard diffs the candidate against the baseline and rejects
added lines containing any fixture filename, any distinctive fixture token (paths,
identifiers, anything with a digit), or a twelve-word verbatim span from a fixture. Generic
phrasing is unaffected, so guidance like "check the linter config before coding a rule as
tool-enforced" passes while the memorised version does not.

## Working on the harness

`selftest.py` grades four synthetic auditors against the real cases and asserts the ranking:

```
perfect  the labels rendered as a compliant report and a faithful rewrite   ~1.00
lazy     finds nothing, keeps everything                                    0.64-0.80
butcher  cuts everything, including every trap                              0.50-0.57
vandal   rewrites the target in place                                       0.00
```

Run it after touching anything in `evallib/`. It costs nothing and it catches the failure mode
where a grader change silently starts rewarding the wrong behaviour.

```bash
python3 harness/selftest.py --emit-run lazy    # synthetic run dir, for testing grade/improve
python3 harness/grade.py runs/selftest-lazy
python3 harness/improve.py --run runs/selftest-lazy --digest-only
```

### Known limits

- **Ceiling effects.** The current skill already scores ~0.99 on `bloated-webapp` and
  `lean-cli`, so the headroom lives in the harder cases. When a case stops discriminating, the
  fix is a harder case, not a looser grader.
- **Single sample per case.** Run-to-run variance is real and unmeasured. A gain under ~0.02
  on one run is noise; that is why `accept_min_train_gain` exists.
- **The fixture repo root is in the agent's context.** A root `AGENTS.md` in a sandbox is
  auto-loaded as the agent's own instructions, exactly as it would be for a real user.
- **Labels are opinions.** They were written to be defensible, and where a real run made a
  better call than the label, the label was corrected — `lean-cli` L30 is the worked example,
  and its `note` field records why.
