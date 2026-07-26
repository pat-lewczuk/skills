# Taxonomy

Two lists. The **N-codes** classify no-ops. The **L-codes** classify directives that look
like no-ops but are load-bearing — check every candidate CUT against the L-codes before
committing to it.

Contents:
- [N-codes: no-op categories](#n-codes-no-op-categories)
- [L-codes: load-bearing lookalikes](#l-codes-load-bearing-lookalikes)
- [Worked examples](#worked-examples)
- [Borderline cases](#borderline-cases)

---

## N-codes: no-op categories

### N1 — Restates model default behavior
General engineering good practice the model already applies. Anything that would appear in
a generic "best practices" listicle and is not contradicted by anything in this project.

> "Write clean, readable, maintainable code." / "Use meaningful variable names." /
> "Handle errors appropriately." / "Follow SOLID principles."

Check against **L1** first: if the project's existing code violates the practice and the
rule exists to push back on that, it is not N1.

### N2 — Unfalsifiable exhortation
An adjective or adverb with no threshold, no artifact, and no way to tell compliance from
non-compliance.

> "Think carefully before making changes." / "Be thorough." / "Pay close attention to
> detail." / "Strive for excellence." / "Keep files reasonably small."

"Keep files small" becomes actionable the moment it says "under 300 lines" — the fix is
often TRIM-into-a-threshold rather than CUT. Ask the user for the number instead of
inventing one.

### N3 — Tautology / self-reference
The document instructing the reader to read the document.

> "Follow these instructions carefully." / "The rules in this file are important." /
> "Always adhere to the guidelines below." / "Read this file before starting work."

### N4 — Duplicate
Same directive stated more than once — within the file, or across the hierarchy
(root AGENTS.md vs nested AGENTS.md vs CLAUDE.md vs a skill). Cross-file duplication is the
expensive kind because both copies load.

Verdict is usually MERGE, not CUT: keep one canonical statement, at the narrowest scope that
still covers every place it applies.

### N5 — Dead reference
Points at a path, script, command, package, or doc that no longer exists. The agent either
fails when it obeys, or silently ignores it.

> "Run `./scripts/dev-setup.sh` first" — script deleted six months ago.
> "See docs/architecture.md" — file renamed.

Requires repo access to verify. Without it, mark unverified and list for the user to check.

### N6 — Already enforced by tooling
The linter, formatter, type checker, pre-commit hook, or CI already guarantees it
mechanically. Prose asking for it a second time costs context and cannot fail closed.

> "Use 2-space indentation" — Prettier config.
> "Don't use `any`" — `tsconfig.json` has `strict` + a lint rule.
> "Always run the formatter" — pre-commit hook does it.

Nuance: if the tool only runs in CI and the agent's inner loop is slow to discover failures,
a one-line pointer to the local command is genuinely useful. Keep the *command*, cut the
*exhortation*.

### N7 — No trigger condition
States a preference but gives the agent no way to know when it applies, so it cannot act
on it.

> "Prefer composition." — over what, in which layer, when?
> "Use the repository pattern where appropriate."

TRIM into a conditional if the intent is recoverable ("In `src/domain/**`, ..."), otherwise
CUT and note the ambiguity.

### N8 — General knowledge exposition
Explains a public framework, language feature, or library the model already knows.

> Three paragraphs on what React hooks are. A table of HTTP status codes. An explanation of
> what a foreign key is.

Project-specific usage of that framework is not N8 — "we use React Query for all server
state, never useEffect+fetch" is a real convention.

### N9 — Aspirational impossibility
Asks for a guarantee that cannot be given, so it changes nothing except the reader's
expectations.

> "Never make mistakes." / "Never hallucinate." / "Always produce bug-free code." /
> "Be 100% accurate."

Often TRIMmable into the actionable version: "Never invent API endpoints — grep the router
before referencing one."

### N10 — Ceremony and meta-commentary
Politeness padding, praise, roleplay framing with no behavioral consequence, notes about the
document's own history.

> "You are a world-class 10x senior engineer." / "Thank you for your help!" /
> "This file was last updated in March."

The persona line is worth a specific note: it is near-costless in tokens but also near-zero
in behavioral effect for engineering tasks, and it crowds the top of the file — the most
valuable position — with nothing. Recommend moving the first real constraint into that slot.

### N11 — Stale / completed
Describes a migration, deprecation, or transition that has finished, or a temporary
workaround for a bug that is fixed.

> "We are migrating from Redux to Zustand — new code should use Zustand." — migration
> completed, no Redux left in the repo.

Verify against the repo before cutting. If the old thing is genuinely gone, the rule is
archaeology.

### N12 — Illustrative filler
Long code examples or scenario walkthroughs demonstrating something already stated in one
line above them. The example adds tokens without adding a constraint.

Keep examples that disambiguate a rule that is genuinely ambiguous in prose. Cut examples
that merely restate an unambiguous rule at length.

---

## L-codes: load-bearing lookalikes

These read as generic. They are not. **Never CUT a directive that matches an L-code** — if
it also matches an N-code, the L-code wins and the verdict is KEEP or TRIM.

### L1 — Counter-default constraint
Pushes against a documented model tendency. The tell: the instruction is negative, and the
behavior it forbids is one the agent would otherwise reach for.

> "Do not add comments explaining what the code does." (models over-comment)
> "Do not add try/catch unless the error is handled meaningfully." (models add defensive
> wrappers)
> "Edit the existing file — do not create a new version alongside it." (models create
> `file_v2.ts`)
> "Do not add backwards-compatibility shims unless asked." (models preserve dead paths)
> "Stop and ask instead of guessing the schema." (models proceed on assumptions)

These look like N1 platitudes to a careless reader. They are the highest-value lines in most
instruction files.

### L2 — Project-specific fact in bland clothing
The sentence sounds generic but contains a noun only this project has.

> "Run tests with `pnpm vitest run --project unit`." — the sentence is "run the tests", the
> value is the exact invocation.

### L3 — Precedence / tie-breaker rule
Resolves a conflict between two conventions that both otherwise apply. Rare, cheap, and
impossible for the agent to derive.

> "When the style guide and the existing file disagree, match the existing file."

### L4 — Safety, legal, privacy, data handling
Never cut on efficiency grounds. Redundancy here is intentional.

> "Never write real customer data into fixtures." / "Do not commit anything from `secrets/`."

### L5 — Recovery path
What to do when something fails, is missing, or is ambiguous. Triggers rarely; matters
enormously when it does.

> "If the migration fails mid-run, do not retry — restore from the snapshot first."

### L6 — Scope boundary
Tells the agent what it is *not* allowed to touch, or when to stop and hand back.

> "Do not modify anything under `packages/legacy-billing/` — it is vendored."

---

## Worked examples

**Example 1 — N1, cut**

Input: `Always write clean, well-structured code that follows industry best practices.`
Verdict: `CUT (N1)` — inversion is absurd, no project noun, no observable artifact.

**Example 2 — looks like N1, actually L1, keep**

Input: `Keep code clean — do not leave commented-out code blocks behind when refactoring.`
Verdict: `KEEP (L1)` — the second clause targets a real tendency to preserve old code as
comments. Trim the first clause, keep the second.
Rewrite: `Delete replaced code; do not leave it commented out.`

**Example 3 — N2 → TRIM, not CUT**

Input: `Try to keep components reasonably small and focused.`
Verdict: `TRIM (N2)` — recover the threshold from the user or from the repo's actual
distribution.
Rewrite: `Split components over ~200 lines.` *(confirm the number with the user)*

**Example 4 — N6, keep the command**

Input: `It is very important that all code is properly formatted before committing. Please
make sure you always run the formatter. Consistent formatting helps the whole team.`
Verdict: `TRIM (N6)` — the pre-commit hook already enforces it; only the invocation is
useful.
Rewrite: `Format: pnpm format` *(or CUT entirely if the hook is non-bypassable)*

**Example 5 — N4 cross-file**

`CLAUDE.md`: "Use conventional commits."
`AGENTS.md`: "Commit messages must follow the conventional commits spec."
Verdict: `MERGE (N4)` — one canonical line in the file both agents read; delete the other.

**Example 6 — N8**

Input: a 40-line section explaining what a Next.js server component is.
Verdict: `CUT (N8)` — public framework knowledge. But scan it first for smuggled
project-specific rules ("...and in our app, all data fetching happens in the page-level
server component") — extract those to a one-liner before cutting the rest.

---

## Borderline cases

**The rule that was added after an incident.** Often looks generic ("always check the
response status"). It is not generic to the team. Flag as KEEP-with-question and ask the
user whether there is a story behind it. Git blame on the line is worth a look when
available — a line added in a commit referencing an incident ticket is load-bearing.

**The rule that duplicates something the model does 95% of the time.** Reliability
reinforcement is a legitimate use of context for a rule that matters (L4, L1). It is not
legitimate for a rule that does not (N1). The discriminator is consequence-of-failure, not
frequency-of-compliance.

**Aspirational culture text.** "We value simplicity over cleverness." Behaviorally near-inert
for an agent, but sometimes deliberate — the user may want it there for the humans who also
read the file. Flag it, explain the cost, let them decide. Do not cut unilaterally.

**Long files that are not bloated.** Some repos genuinely need a lot of instruction. If the
audit finds high signal density, say so plainly and recommend the routing structure instead
of a cut. "Your file is long because your project is complicated" is a valid finding.
