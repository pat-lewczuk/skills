# CLAUDE.md

Notes for Claude Code specifically.

- Commit messages must follow the conventional commits specification.
- Do not commit `.env` files or any file with real credentials in it.
- Run `pnpm turbo run test` before you push.
- Prefer editing existing files over creating new ones.
- The dev server for the web app is `pnpm --filter @acme/web dev` on port 3210.
- When a task touches both `packages/api` and `packages/web`, change the API first so the
  generated client can be regenerated with `pnpm --filter @acme/web codegen`.
