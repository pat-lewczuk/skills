---
name: task-router
description: Turn a repo's agent instructions into a task router — a short root AGENTS.md with a "when doing X, read Y" table, plus per-unit AGENTS.md files and a check that every route exists. Use when asked to build a task router, slim or split AGENTS.md/CLAUDE.md, or set up just-in-time agent context in any project.
---

# Task router

Load context when a task needs it, not up front. Assume nothing about the repo — every path
you write must exist.

1. **Discover.** Run `git status` (never overwrite uncommitted work). Find the instruction
   files, the units (packages/apps/services, or top-level source dirs), the real commands
   (manifest + CI), and the docs, specs and skills an agent could be sent to.
2. **Split.** For every rule in the root file decide: applies to every task → stays at root;
   one unit only → that unit's `AGENTS.md`; duplicate or no-op → drop and list it. Move,
   never copy. Give a unit a file only if it has real unit-specific content. Next to each
   `AGENTS.md` add a `CLAUDE.md` containing only `@AGENTS.md`.
3. **Route.** Root = short project summary + hard rules + a `| Task | Read |` table. Include
   at least Bug fix, New feature, Refactor, Review, then one row per recurring concern and per
   unit. Every target is a concrete file. No doc for a need → report it as a gap, no row.
4. **Check.** Add a small script with no new dependencies that fails when a routed path does
   not exist or a file exceeds its budget (root ≤ 150 lines, unit ≤ 120). Run it.
5. **Report.** Files changed, where each moved rule went, what was dropped, gaps.

Out of scope: hooks, editing skills or specs, product code, commits.
