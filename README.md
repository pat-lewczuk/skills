# Skills

Agent skills for real engineering work.

These skills are small, easy to adapt, and composable. They work with any model. Hack around
with them, make them your own.

## Install

With the [skills.sh](https://skills.sh) installer:

```bash
npx skills@latest add pat-lewczuk/skills
```

Or copy the directory you want straight into your project:

```bash
cp -r skills/eliminate-no-op /path/to/your-project/.claude/skills/
```

## Skills

### eliminate-no-op

Audits agent instruction files — `AGENTS.md`, `CLAUDE.md`, `SKILL.md`, `.cursorrules`, system
prompts — for directives that burn context without changing behavior.

Instruction files rot. Every incident adds a rule, no one ever removes one, and the file drifts
into a wall of well-meant text the model already agreed with. That text occupies context on
every turn and dilutes attention away from the rules that actually encode project knowledge.

The skill runs a mechanical pass (duplicate detection, dead path references, token cost per
section), then classifies every directive as `KEEP` / `TRIM` / `MERGE` / `MOVE` / `CUT` against
five survival tests. It produces a findings report and writes the rewrite *beside* the original
— never in place — so you review a diff before anything is applied.

It is deliberately conservative: deleting a line that was quietly preventing a recurring bug
costs far more than leaving three redundant lines alone.

#### What it recovers

Measured on the eval suite's seven audit cases, from the rewrites the skill actually produced
(baseline run, 2026-07-26):

| Case | Target | Lines | Est. tokens | Saved | Cut |
|---|---|---|---|---|---|
| bloated-webapp | `AGENTS.md` | 129 → 63 | 1,229 → 527 | **702** | 57.1% |
| skill-md-target | `SKILL.md` | 94 → 61 | 930 → 492 | **438** | 47.1% |
| duplicated-hierarchy | `AGENTS.md` | 59 → 33 | 436 → 249 | **187** | 42.9% |
| no-repo-paste | `colleague-AGENTS.md` | 48 → 36 | 471 → 329 | **142** | 30.1% |
| stale-migration | `.cursorrules` | 19 → 12 | 316 → 194 | **122** | 38.6% |
| long-but-dense | `AGENTS.md` | 93 → 88 | 1,271 → 1,172 | **99** | 7.8% |
| lean-cli | `AGENTS.md` | 40 → 37 | 424 → 406 | **18** | 4.2% |
| **Total** | 7 files | 482 → 330 | **5,077 → 3,369** | **1,708** | 33.6% |

Read the spread, not the mean. The bottom two rows are the healthy files, whose labels expect
0–25% and 0–22% — a large cut there scores as a *failure*. Maximising tokens removed across
this table would mean destroying them, which is why the suite scores cut size against a
per-file band instead of rewarding volume.

What a saving is worth depends on where it lands. `AGENTS.md`, `CLAUDE.md` and `.cursorrules`
load on every turn, so 702 tokens off `bloated-webapp` is 702 tokens back on every turn in that
repo, permanently. A `SKILL.md` body only loads when the skill fires — there the resident cost
is the description field, which that audit cut from 152 tokens to a tight trigger sentence.

Two things the table undercounts: `duplicated-hierarchy` also recommended deleting `CLAUDE.md`
outright (~135 tokens, four of its six lines duplicated the root file), and directives verdicted
`MOVE` leave the always-loaded root for a nested file that loads only in its own subtree.

Figures are the `len/4` estimate `analyze.py` uses. Files this dense with backticked paths and
flags tokenize worse than plain prose, so treat the absolutes as ±15%; the ratios hold. Each
audit cost $0.73–$1.04 and 13–18 turns to produce.

### evaluate-skill

Builds an eval suite for another skill, runs it, and reports — optionally with a loop that
revises the skill from its own failures.

A skill is a prompt, and a prompt is untested code. The usual way to improve one is to read it,
decide a paragraph feels weak, and rewrite it. That has no error signal: the edit that makes a
skill read better and the edit that makes it work better are not the same edit.

Given a skill name it asks three things — what the skill must get right and what it must never
do, whether you want to supply the cases or have them generated, and whether you want the
improvement loop. Cases you describe in the chat get converted into real ones, copying the
workspace from a real project if you point at it; a failure you actually remember is better
ground truth than anything a model invents.

From there it scaffolds the suite, verifies the instrument against a do-nothing run and a
perfect run before spending anything, runs it, and writes an HTML dashboard. Ask for the loop
and it additionally revises the skill, rejects patches that memorised the fixtures, and keeps a
revision only if it holds up on cases it was never tuned against.

It refuses to start without a named target skill.

```bash
python3 scripts/scaffold.py --skill my-skill --case happy:train --case restraint:train \
  --case unseen:holdout --case triggers:train:trigger
```

## Evals

`evals/eliminate-no-op/` holds the eval suite for that skill: eight labelled cases, weighted
metrics that punish deleting a load-bearing line three times harder than missing a platitude,
and a loop that revises the skill from its own failures and keeps a revision only if it holds
up on cases it was never tuned against.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="evals/eliminate-no-op/docs/results-dark.png">
  <img src="evals/eliminate-no-op/docs/results-light.png" alt="Eval results dashboard: adjusted suite score 0.9625, zero of 74 load-bearing lines cut, per-case and per-metric scores, suite composition, grader calibration, and the improvement-loop history.">
</picture>

```bash
cd evals/eliminate-no-op
python3 harness/selftest.py     # validate the graders, free
python3 harness/run.py          # run the suite
python3 harness/loop.py --iterations 2
python3 harness/report_html.py  # regenerate results.html + the image above
```

Details, case-by-case, in [`evals/eliminate-no-op/README.md`](./evals/eliminate-no-op/README.md).

## License

[MIT](./LICENSE)
