# Report template

Save as `no-op-report.md` beside the audited file. Use these sections in this order. Keep
prose short — the tables carry the report.

---

```markdown
# No-op audit: <path/to/file>

**Audited:** <date> · **Mode:** full / evidence-limited (no repo access)
**Also read for cross-file duplication:** <list, or "none">

## Summary

| | Before | After | Δ |
|---|---|---|---|
| Directives | | | |
| Lines | | | |
| Est. tokens | | | |
| Signal density | | | |

<One paragraph: what kind of file this is, what the dominant waste pattern is, and how
confident the recommendation is. If the cut is larger than ~60%, say so here and say why.>

## Verdict breakdown

| Verdict | Count | Est. tokens |
|---|---|---|
| KEEP | | |
| TRIM | | |
| MERGE | | |
| MOVE | | |
| CUT | | |

## Findings

One row per non-KEEP directive. Sort by line number, not by severity — the user reads
alongside the original file.

| Line | Verdict | Code | Directive (abbreviated) | Rationale |
|---|---|---|---|---|
| 12 | CUT | N1 | "Write clean, maintainable code" | Model default; inversion absurd; no project noun |
| 34-41 | TRIM | N12 | 8-line example of the commit format | Rule above is unambiguous; example restates it |
| 57 | MERGE | N4 | "Use conventional commits" | Duplicates CLAUDE.md:23; keep the AGENTS.md copy |
| 88 | CUT | N5 | "Run ./scripts/setup.sh" | Path does not exist in repo |

## Cut lines, verbatim

Every CUT reproduced in full so the user can restore any of them without git.

> **L12** — Always write clean, well-structured code that follows industry best practices.
> **L88** — Before starting, run `./scripts/setup.sh` to prepare your environment.

## Kept despite looking generic

The lines a careless audit would have removed, and why they stay. This section is what makes
the rest of the report trustworthy.

| Line | Code | Why it stays |
|---|---|---|
| 21 | L1 | Counters the tendency to add explanatory comments |
| 45 | L2 | Contains the exact test invocation for this monorepo |

## Open questions

Things that need the user's knowledge, not the auditor's judgment. Ask rather than guess.

- L19 "keep files reasonably small" — what is the actual threshold?
- L63 "always validate input" — is there an incident behind this, or is it generic?

## Observations

Gaps, inconsistencies, or structural recommendations noticed during the audit. Explicitly
*not* applied to the rewrite — the rewrite is subtractive only.

- No instruction covers what to do when a migration fails; the recovery path is undocumented.
- Sections 4 and 7 both describe error handling with slightly different rules.
- At <N> lines across <M> domains, this file is a candidate for a routing structure: a short
  root that points to per-domain references loaded on demand.

## Proposed rewrite

Written to `<path>.rewrite.md`. Diff below. Nothing has been applied to the original.

<unified diff>
```
