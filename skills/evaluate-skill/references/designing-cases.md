# Designing cases

A case is a small realistic workspace, a prompt in the user's words, and a set of assertions
about what should come back. The suite is only as good as the cases; everything downstream is
arithmetic.

Contents:
- [The one rule](#the-one-rule)
- [The five kinds of case](#the-five-kinds-of-case)
- [Building the workspace](#building-the-workspace)
- [Splits](#splits)
- [Traps](#traps)
- [Trigger cases](#trigger-cases)
- [How many cases](#how-many-cases)
- [Smells](#smells)

---

## The one rule

**A case must be able to fail.** Before writing any assertion, answer: what would a bad run of
this skill produce here, and which check catches it? If you cannot name the bad run, the case
is decoration.

The corollary is that a suite of "did it produce the artifact" cases measures almost nothing.
Producing an artifact is the easy part. What separates a good skill from a bad one is what it
declines to do, what it notices without being told, and what it preserves while changing
everything around it.

## The five kinds of case

Most suites need at least three of these. A suite with only the first kind is the common
failure mode.

**1. The canonical case.** The task the skill exists for, at realistic size, with every
feature of the job present at once. Scores the main path.

**2. The restraint case.** A workspace where the correct answer is *do almost nothing*. A
cleanup skill pointed at clean code; a refactoring skill pointed at code that is already fine;
an audit skill pointed at a file that is genuinely dense. Without this case, every metric
rewards doing more, and the improvement loop will happily make the skill more aggressive
forever. **This is the single highest-value case in most suites** and the one people skip.

**3. The evidence case.** Two situations that look identical from the text alone and are
distinguished only by something in the workspace — a config that does or does not enforce a
rule, a path that does or does not exist, a package version. Catches a skill that pattern-matches
instead of checking.

**4. The trap case.** Content engineered so the obvious move is wrong. See [Traps](#traps).

**5. The trigger case.** Does the description fire on the right prompts. See
[Trigger cases](#trigger-cases).

## Building the workspace

`cases/<id>/workspace/` is copied into a fresh sandbox for every run. What is in it decides
what the skill can know.

- **Make the evidence real.** If a check says "the linter already enforces this", the linter
  config has to be in the workspace and actually contain that rule. A fixture that lies makes
  the label wrong, and you will spend an afternoon blaming the skill.
- **Include the files that make it a project**, not just the file under test: manifests, config,
  a few real source files, whatever the skill would consult. Skills behave differently in a
  bare directory.
- **Never let a fixture sabotage the workflow under test.** A root `AGENTS.md` or `CLAUDE.md`
  in the sandbox is auto-loaded as the agent's own instructions. If it says "never create new
  files" and the skill's job is to write a report, the case measures the fixture, not the
  skill. Read every instruction file you plant, from the agent's point of view.
- **Keep it small.** Enough to be realistic, not a real repo. Every extra file is context the
  agent spends on nothing.
- **Watch the parent repo's `.gitignore`.** A fixture that plants `secrets/` or `*.env` may not
  be committed at all, and the case will fail for everyone else.

## Splits

Every suite needs both:

- **`train`** — the improvement loop sees these failures and revises against them.
- **`holdout`** — never enters the digest. Its only job is to answer "did the revision learn
  the job, or the training cases?"

One or two holdout cases is enough, but zero makes the loop unfalsifiable. `selftest.py` fails
the suite if there is no holdout, on purpose.

Put your *most representative* case in holdout, not your weirdest. The holdout is a
generalisation test; a bizarre edge case tells you nothing about generalisation.

## Traps

A trap is content that a careless run destroys and a careful run keeps. They are what turn a
suite from "did it work" into "can it be trusted".

Finding them: take the thing the skill removes, changes, or overrides, and construct an
instance where doing so is wrong for a reason only the workspace reveals.

- A cleanup skill: a line that looks like boilerplate but encodes a real constraint.
- A refactor skill: a function that looks dead but is called through a string dispatch.
- A dependency-upgrade skill: a pin that looks stale but is held back by a real incompatibility.
- A test-writing skill: an existing test that looks redundant but covers a regression.

Weight trap checks heavily (3+ against `safety`) and gate the worst of them. The asymmetry is
the point: the expensive failure for nearly every skill is confident destruction, not a missed
improvement.

## Trigger cases

The `description` field is the only part of a skill that is in context on every turn, and it
alone decides whether the skill fires. Test it directly with a `kind: "trigger"` case:

```json
{"probes": [
  {"prompt": "phrasing a user would actually type", "should_fire": true},
  {"prompt": "a different phrasing, different vocabulary", "should_fire": true},
  {"prompt": "adjacent work the skill must not hijack", "should_fire": false}
]}
```

Probes run with Write/Edit/Bash withheld, so each stops soon after the routing decision — they
are cheap. Include at least as many negative probes as positive ones: over-triggering is
invisible to every other case in the suite and is the more common defect in a description that
was written to be found.

## How many cases

Four to eight. Below four there is not enough signal to tell a real gain from noise; past
eight, each run costs enough that people stop running it, and a suite nobody runs measures
nothing.

Prefer one more *kind* of case over one more instance of a kind you already have.

## Smells

- **Every case passes on the first run.** The cases are too easy, or the checks are too loose.
  Add a harder case; do not celebrate.
- **A case fails for a reason unrelated to the skill.** Fix the case. Note that you did.
- **The prompt names the skill's own vocabulary.** "Run the no-op audit and produce the
  findings table" tests nothing about judgement. Write the prompt as a user who has the
  problem, not as someone who has read the skill.
- **All checks in one metric.** If everything is `correctness`, the weights do nothing and the
  score cannot express "it worked but it was reckless".
- **The workspace was generated by the same model that will be graded on it.** It will contain
  exactly the patterns that model finds easy. Take fixtures from real code where you can.
