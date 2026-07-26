---
name: evaluate-skill
description: Build and run an eval suite for another agent skill — labelled cases, deterministic checks, a rubric judge, a scored report and an HTML dashboard — and optionally a self-improvement loop that revises the skill from its own failures and keeps a revision only if it survives a holdout split. Use whenever someone asks to evaluate, test, measure, benchmark, harden or improve a named skill, asks whether a skill actually works or how well it works, or wants regression coverage before editing one. Requires the name of the skill under test: if none was given, stop and ask rather than guessing.
---

# Evaluate Skill

A skill is a prompt, and a prompt is untested code. The usual way to "improve" one is to read
it, feel that a paragraph is weak, rewrite it, and feel better. That process has no error
signal: the edit that makes the skill read well and the edit that makes it work are not the
same edit, and nothing tells you which one you made.

This builds the missing instrument — cases with known-correct outcomes, checks that fail
loudly, and a loop that only keeps a revision that survives cases it was never tuned against.

## Before anything else: which skill?

**This skill does nothing without a named target.** If the request did not name a skill to
evaluate, stop and say so:

> I need the name of the skill to evaluate. Tell me which one — for example
> `/evaluate-skill my-skill-name` — and I'll take it from there.

Do not guess from context, do not pick the most recently edited skill, and do not evaluate
yourself. Resolve the name to a real directory (`.claude/skills/<name>/`, `skills/<name>/`, or
a path) and confirm `SKILL.md` exists. If the name matches nothing, list what is installed and
stop.

## Then: three questions, before building anything

Ask all three in one turn, and do not start work until they are answered.

1. **What does this skill have to get right, and what must it never do?** The second half
   matters more. Every skill has a failure that is expensive and one that is merely
   disappointing, and a suite that does not know the difference will happily optimise the
   skill toward confident damage.
2. **Do you want to supply the cases, or should I generate them?** Offer three ways: the user
   describes cases, I derive them from the skill's own claims, or — usually best — the user
   brings the one or two they care about and I fill in the rest. A case the user remembers
   going wrong is worth more than any number I invent, because it is a failure that actually
   happened.
3. **Evaluation only, or evaluation plus an improvement loop?** Evaluation measures and
   reports. The loop additionally revises the skill and re-measures, accepting a revision only
   if it holds up on a holdout split. The loop costs roughly three times as much and edits a
   *copy* — nothing installed changes unless the user promotes a winner.

State the cost before running. Each case is one real agent invocation: budget ~$1 per case per
run, and the loop runs the suite up to three more times.

## Workflow

### 1. Read the skill under test

Read its `SKILL.md`, every reference, and every script. You are looking for the claims it
makes: what it promises to produce, what it promises never to do, which steps it says are
mandatory, and what its description says should trigger it. Those claims are the first draft
of the case list — an eval is the question "does it do what it says".

### 2. Scaffold

```bash
python3 scripts/scaffold.py --skill <name> \
  --case <id>:train --case <id>:train --case <id>:holdout --case triggers:train:trigger
```

Creates `evals/<name>/` with `config.json`, a **copy** of the harness, and case skeletons. The
copy matters: the suite keeps working after this skill is uninstalled or changed.

### 3. Collect the cases the user is bringing

Skip this if they asked for everything generated. Otherwise take them one at a time in the
chat, and for each one get four things:

- **What did you ask for?** Their words, not the skill's vocabulary.
- **What was it looking at?** A path you can copy from, files pasted here, or a description
  you can reconstruct.
- **What should have happened?**
- **What went wrong, if it did?** This is the valuable one. A remembered failure converts
  directly into the highest-weighted check in the suite.

Ask for the whole set before building any of them — the checks are easier to write once you
can see which cases overlap. `references/designing-cases.md` § *Turning a description into a
case* has the mapping from what people say to what a check asserts.

Then convert each one:

```bash
python3 scripts/make_case.py --into evals/<name> spec.json
```

The spec is the case fields plus a `workspace` block that either copies from a real project or
writes files inline. When copying from a real project, **read the file list it prints** — it
skips things that look like credentials by name, which is not the same as by content.

### 4. Fill in the rest

Whatever the user did not supply, you write. Read `references/designing-cases.md` first — it
is the difference between a suite that measures something and a suite that congratulates the
skill.

The short version: four to eight cases total, each a small realistic workspace plus a prompt.
At least one case where the right answer is **do almost nothing**, at least one **holdout**
the improvement loop never sees, and one **trigger** case probing the description with prompts
that should fire it and adjacent ones that should not. If the user's own cases already cover
some of those roles, say which, and add only what is missing.

### 5. Write the checks

`references/scoring.md` has the check types, the metric buckets and the weighting rules. Two
things that decide whether the suite is any good:

- **Every case needs at least one safety check** — something the skill must never do, weighted
  heaviest, usually `gate: true`. A suite made only of "did it do the thing" rewards doing
  more, always.
- **Prefer a check to a rubric item.** Checks are free, deterministic, and re-runnable. Reserve
  rubric items for what a regex genuinely cannot settle, and write each criterion so two
  readers would grade it the same way.

### 6. Verify the instrument before trusting it

```bash
python3 harness/selftest.py
```

Free, no API calls. It lints every case, then scores two synthetic runs against them: one that
produced nothing, which must score near zero, and one built to satisfy every check, which must
score near one. **A case that cannot separate those two is not measuring anything** — fix it
before spending money. Run this again after every change to a case or a check.

### 7. Run and grade

```bash
python3 harness/run.py                 # costs money: one agent per case
python3 harness/grade.py runs/<id>     # free, re-runnable after editing checks
```

Grading is separate from running on purpose: rebuilding a check never means paying for the
agent runs again.

### 8. Read the failures before believing them

Open the failing cases and look at what the skill actually produced. Roughly a third of first
failures are the eval being wrong, not the skill — a check whose regex is too tight, a rubric
criterion that punishes a defensible choice, a fixture that made the task impossible. **Fix
the case and say that you did.** An eval that is never wrong is an eval nobody checked.

### 9. Report

```bash
python3 harness/report_html.py         # -> results.html
./harness/screenshot.sh                # -> docs/results-{light,dark}.png
```

Then write the summary in the chat: the score, the two or three weakest areas with the
evidence behind them, what you fixed in the eval itself, and what you would change in the
skill. Numbers without the "so what" are not a report.

### 10. Only if the user asked for the loop

```bash
python3 harness/loop.py --iterations 2
python3 harness/loop.py --iterations 2 --promote   # install an accepted winner
```

Read `references/improvement-loop.md` first. The loop digests failures into a candidate
revision, rejects it if it memorised fixture content, and accepts it only if it gains on train
without regressing on holdout. Expect rejections — a candidate that improves the training
cases and nothing else is the normal outcome, and rejecting it is the loop working.

Never promote without showing the user the diff and the scoreboard row that justifies it.

## Reference files

- `references/designing-cases.md` — what makes a case discriminate. Read before writing cases.
- `references/scoring.md` — check types, metrics, weights, gates, writing rubric criteria.
- `references/improvement-loop.md` — the loop, the overfit guard, accept/reject thresholds.

## Scripts

- `scripts/scaffold.py` — create a suite for a skill.
- `scripts/make_case.py` — turn a case spec into a real case directory, copying workspace
  files from a project or writing them inline.
- `scripts/harness/` — the harness that gets copied into it: `run`, `grade`, `selftest`,
  `improve`, `loop`, `report_html`, `screenshot.sh`. Stdlib only.
