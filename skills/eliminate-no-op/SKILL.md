---
name: eliminate-no-op
description: Audit agent instruction files — AGENTS.md, CLAUDE.md, SKILL.md, .cursorrules, system prompts, subagent briefs — for no-op instructions that burn context without changing behavior, then produce a findings report and a proposed rewrite. Use this whenever the user mentions auditing, reviewing, slimming, compressing, cleaning up, or "why is my AGENTS.md so long", whenever an instruction file is suspected of being bloated or ignored by the agent, and whenever someone asks whether a rule in an agent config is actually doing anything. Also use it proactively before adding new rules to an already-large instruction file.
---

# Eliminate No-Op

Instruction files rot. Every incident adds a rule, no one ever removes one, and the file
drifts toward a wall of well-meant text that the agent already agreed with before it read
a single line. That text is not free: it occupies context on every single turn, it dilutes
attention away from the handful of rules that actually encode project-specific knowledge,
and it trains the reader (human and model) to skim.

This skill finds the dead weight and proposes a rewrite. It is deliberately conservative:
the failure mode of an over-eager cleanup — deleting a line that was quietly preventing a
recurring bug — is far more expensive than leaving three redundant lines in place.

## What counts as a no-op

A directive is a no-op when removing it would not change a single token the agent produces.
Three broad families:

1. **Already known.** It restates behavior the model does by default — general engineering
   good practice, politeness, common sense. "Write clean, maintainable code."
2. **Unactionable.** There is no observable artifact that could differ depending on whether
   the agent followed it. "Think deeply about the architecture."
3. **Inert.** It is duplicated elsewhere, enforced by tooling, references something that no
   longer exists, or has no trigger condition telling the agent when it applies.

The full taxonomy with codes and worked examples lives in `references/taxonomy.md`. Read it
before classifying — the codes make the report consistent and reviewable, and the
"load-bearing lookalikes" section is the part that prevents damage.

## Workflow

### 1. Collect the target and its context

Ask for the file if it wasn't given. Then gather everything needed to judge whether a line
is inert — you cannot tell a dead reference from a live one without looking:

- The **whole instruction hierarchy**, not just the one file: root `AGENTS.md`, nested
  `AGENTS.md` in subdirectories, `CLAUDE.md`, `.claude/` skills and commands, `.cursorrules`,
  imported files (`@path/to/file.md`). Duplication across levels is one of the largest
  sources of waste and is invisible when reading a single file.
- **Tooling config**: `eslint`/`biome`/`ruff` config, `tsconfig.json` (`strict`), formatter
  config, pre-commit hooks, CI workflows, `package.json` scripts. Anything these enforce
  mechanically does not need to be asked for in prose.
- **The repo itself**: do the referenced paths, scripts, and commands still exist?

If the repo isn't available (the user pasted a file with no project around it), say so and
run the analysis in **evidence-limited mode** — the codes that need repo evidence (N5 dead
reference, N6 tool-enforced) become "unverified" rather than being guessed at.

### 2. Run the mechanical pass

```bash
python3 scripts/analyze.py <target-file> [--repo <repo-root>] [--also <other-instruction-file> ...]
```

The script does the parts that should not be done by eye: it splits the file into
numbered directives, estimates token cost per section, flags near-duplicate directives
within and across files, extracts every path/command/script reference and checks whether it
exists in the repo, and reports vague-quantifier and hedge-word density. It produces
`analysis.json` plus a readable summary.

Its output is **evidence, not verdicts**. The script cannot tell a load-bearing rule from a
platitude. Every classification is yours.

### 3. Classify every directive

Work through the file directive by directive — do not sample, do not summarize whole
sections, and do not skip the parts that look obviously fine. The whole value of the audit
is that it is exhaustive; a partial pass gives the user no confidence that what remains was
actually examined.

For each directive assign: an **ID** (line number), a **verdict**, a **code**, and a
one-line **rationale** that names the evidence.

Verdicts:

| Verdict | Meaning |
|---|---|
| `KEEP` | Carries project-specific information or counters a real model tendency. Untouched. |
| `TRIM` | The information is real but the phrasing is 5x longer than needed. Rewrite shorter. |
| `MERGE` | Duplicate or partial overlap with another directive. Fold into the canonical one. |
| `MOVE` | Real information, wrong home — belongs in a nested AGENTS.md, a skill, a code comment, or tooling config rather than the always-loaded root file. |
| `CUT` | No-op. Removing it changes nothing. |

Apply these five tests before writing `CUT`. A directive survives if it passes **any** of them:

- **Inversion test.** Negate the directive. If the negation is something an agent might
  plausibly do by default, the directive carries information. If the negation is absurd
  ("write insecure code with no tests"), no one was going to do that anyway — no-op.
- **Ablation test.** Picture the last three tasks done in this repo. Would any output have
  differed if this line were absent? If you cannot name one, that is a strong CUT signal.
- **Specificity test.** Does it contain a project-specific noun — a path, command, package,
  version, threshold, table name, person, or environment? Project-specific nouns almost
  always carry information even when the sentence around them is bland.
- **Counter-default test.** Does it push against a known model tendency (over-commenting,
  adding defensive fallbacks, creating new files instead of editing, over-engineering,
  inventing abstractions, hedging)? These read as generic advice but are load-bearing. This
  is the single most common false-positive in a naive audit.
- **Recovery test.** Does it describe what to do when something fails or is ambiguous?
  Rarely-triggered escape hatches look like filler right up until they are needed.

When a directive is borderline, mark it `KEEP` with a note in the report rather than
guessing. The report is where uncertainty gets surfaced; the rewrite is where certainty
gets applied.

### 4. Write the report

Use the exact structure in `references/report-template.md`. Save it as
`no-op-report.md` next to the target file.

Two things the report must do that a plain list of findings does not:

- **Quantify.** Directive count and estimated token cost before/after, and a signal density
  figure (directives that survived / total). Users need a number to decide whether the
  rewrite is worth reviewing.
- **Show the cut lines verbatim.** Every `CUT` appears in the report with its original text.
  The report is the undo buffer. If a cut turns out to have been wrong, the user needs to be
  able to paste the line back without going to git history.

### 5. Propose the rewrite — never overwrite

Write the rewritten file **beside** the original: `AGENTS.rewrite.md`, never in place. Then
show a unified diff and ask whether to apply it. This is a proposal, and the user has
context you don't — they may know exactly which incident produced a line you flagged.

Rewrite rules:

- Preserve the original's information content exactly. This is a subtractive edit. Do not
  add new rules, do not "improve" surviving rules beyond compression, do not reorder for
  taste. If you notice a genuine gap, mention it in the report's *Observations* section —
  do not silently patch it into the rewrite.
- Keep the original's structure and heading names where possible so the user's muscle memory
  and any external links still work.
- Prefer imperative one-liners over prose paragraphs. `Run pnpm test:unit before pushing.`
  beats a paragraph explaining the importance of testing.
- Front-load the highest-signal sections. Project-specific commands, paths, and conventions
  first; general orientation later.
- If the file is large and multi-domain, propose a routing structure rather than one long
  file: a short root file that says *when* to read each detailed reference, with the details
  in separate files loaded on demand. Note this as a recommendation in the report — it is a
  bigger change than a subtractive edit and needs explicit buy-in.

## Calibration

State the standard you are holding the file to, because it varies by file type:

- **AGENTS.md / CLAUDE.md** — loaded on every turn. Strictest budget. A line has to earn its
  permanent residency in context.
- **SKILL.md** — loaded only when triggered. More room for explanation, but the description
  field is always in context and must be tight.
- **Nested / on-demand references** — loosest. Redundancy here is cheap.

A healthy root instruction file is mostly nouns the model could not have guessed: commands,
paths, names, versions, thresholds, and constraints that contradict the obvious approach.
If the rewrite ends up under roughly 40% of the original, say so explicitly and re-check the
CUT list before presenting — that is either a genuinely bloated file or an over-aggressive
pass, and the user deserves to know which one you think it is.

## Reference files

- `references/taxonomy.md` — the N-codes for no-op categories, the L-codes for load-bearing
  lookalikes, and worked before/after examples. Read before classifying.
- `references/report-template.md` — the exact report structure.
- `scripts/analyze.py` — mechanical pre-pass. Run before classifying.
