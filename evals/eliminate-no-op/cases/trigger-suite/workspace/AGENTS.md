# AGENTS.md

`sumkit` is a tiny math utility package. TypeScript, published to npm.

## Principles

- Write clean, maintainable, well-tested code.
- Use meaningful names and keep functions small.
- Think carefully before making changes.
- Be thorough and pay attention to detail.
- Handle all errors appropriately.
- Follow industry best practices at all times.
- Strive for simplicity and elegance in your solutions.
- Always leave the codebase better than you found it.

## Commands

- Build: `pnpm build`
- Test: `pnpm vitest run`
- Publish: `pnpm changeset publish` (CI only)

## Conventions

- Public API is re-exported from `src/index.ts` only.
- Every exported function needs a doc comment with an `@example`.
- Breaking changes need a major changeset.

## Reminders

- Please read this document carefully before you start.
- Remember to write tests.
- Thank you for contributing to sumkit!
