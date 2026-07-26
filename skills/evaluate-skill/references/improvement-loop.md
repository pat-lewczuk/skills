# The improvement loop

Measure, revise, re-measure, keep or discard. The loop's value is not that it writes better
prose than you — it is that it cannot keep a revision it cannot justify.

Contents:
- [One iteration](#one-iteration)
- [The digest](#the-digest)
- [The overfit guard](#the-overfit-guard)
- [Accept and reject](#accept-and-reject)
- [When the eval is the thing that is wrong](#when-the-eval-is-the-thing-that-is-wrong)
- [Reading the scoreboard](#reading-the-scoreboard)

---

## One iteration

```
digest the current best run   failures from the train split only
  -> optimiser edits a COPY   never the installed skill
  -> overfit guard            reject patches that memorised fixture content
  -> smoke test               whatever the skill ships must still run
  -> re-run train, compare
  -> if train improved, run holdout
  -> accept only if holdout did not regress
```

```bash
python3 harness/loop.py --iterations 2
python3 harness/loop.py --iterations 2 --baseline-run runs/<id>   # reuse a measured baseline
python3 harness/loop.py --iterations 1 --evaluate /path/to/skill  # judge a hand-written revision
python3 harness/loop.py --iterations 1 --promote                  # install an accepted winner
```

Budget: an iteration costs the train split once, plus the holdout if the train gain clears the
threshold, plus one optimiser run. On an eight-case suite that is roughly three times a plain
evaluation.

## The digest

Built from `scores.json`: every failed check with its `why`, every weak rubric verdict with the
judge's reasoning, and a section listing what failed in more than one case. That last section
is the useful one — a fix that only helps a single case is usually a fix aimed at the fixture.

Only train-split cases enter the digest. This is what makes the holdout meaningful.

## The overfit guard

Give a model your failures and edit access and it will write the shortest thing that makes the
failures stop:

> The rule about port 4310 is load-bearing and must never be cut.

That scores beautifully on the next run and teaches the skill nothing. The guard diffs the
candidate against the baseline and rejects added lines containing any fixture filename, any
distinctive fixture token (paths, identifiers, anything with a digit), or a twelve-word
verbatim span from a fixture.

Two exemptions stop it blocking honest work, both added after real false positives:

- **already in the baseline skill** — a token the skill itself already used is not memorisation
- **appears in more than one case** — a token in two independent fixtures is vocabulary, not an
  answer

Generic guidance passes: *"before treating a rule as tool-enforced, open the linter config and
confirm it is actually there"* is fine. The memorised version of the same fix is not.

## Accept and reject

From `config.json`:

```json
"loop": {"accept_min_train_gain": 0.01, "accept_max_holdout_regression": 0.02,
         "max_iterations": 3}
```

A candidate is accepted only if train improves by at least the threshold **and** holdout does
not fall by more than the allowance. Everything else is rejected and recorded.

**Expect rejections.** In the reference suite, the first candidate made three sensible
method-level edits, improved one metric from 0.89 to 0.95, and was rejected: its total train
gain was +0.0065, under the 0.01 threshold, while the always-in-context description grew from
155 to 252 tokens. At one sample per case a gain that small is indistinguishable from noise,
and a loop that banks it accumulates plausible-looking edits that nobody can defend later.

The context penalty is why the description growth mattered: the aggregate subtracts a term
proportional to `SKILL.md` growth past `skill_token_baseline`. Without it, the cheapest way to
raise any score is to append rules forever, which makes the skill worse in the way that is
hardest to see.

## When the eval is the thing that is wrong

A failing check means one of two things, and you have to look to know which:

1. the skill did something wrong, or
2. the case demanded something unreasonable.

Both are common. In the reference suite, two ground-truth labels were wrong and the skill's
reasoning was better than the label's — it kept a duplicated rule and argued the trade in its
report, which was defensible and had been scored as a failure.

The optimiser prompt tells the candidate to say so rather than contort the skill. When it does,
believe it long enough to check. Fix the case, record why in the case file, and re-run. An eval
that has never been corrected is an eval nobody has audited.

## Reading the scoreboard

`scoreboard.md` keeps every candidate, accepted or not, with the reason. It is append-only:
when a rejection later turns out to have been the harness's fault, annotate the row rather than
deleting it. The record of what the loop got wrong is worth as much as the record of what it
got right.

Rows to be suspicious of:

- **A large train gain with a flat holdout.** Usually memorisation the guard did not catch.
  Read the diff.
- **Several accepted candidates in a row, each +0.01.** Check whether `SKILL.md` has quietly
  doubled.
- **An accepted candidate that changed only prose.** Re-run the baseline once more before
  believing it; at n=1 that is within noise.
