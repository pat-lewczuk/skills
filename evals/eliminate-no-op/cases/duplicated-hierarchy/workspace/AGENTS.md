# AGENTS.md

Acme monorepo: `packages/web` (Next.js), `packages/api` (Fastify), `packages/db` (Drizzle),
`packages/ui` (component library). Turborepo, pnpm workspaces.

## Working here

- Install: `pnpm install` at the root. Never install inside a package directory.
- Build everything: `pnpm turbo run build`
- Test everything: `pnpm turbo run test`
- Run one package's tests: `pnpm --filter @acme/api test`
- Always write high-quality, production-ready code.
- Make sure your changes are well tested.

## Commits

Use conventional commits.

Never commit `.env` files or anything containing a live credential.

## API package

Route handlers live in `packages/api/src/routes/`. Every handler must call `assertSession(req)`
as its first statement — there is no global auth middleware.

Fastify plugins register in `packages/api/src/plugins/index.ts` in dependency order.

The API talks to Postgres only through `packages/db`. Never import `pg` in `packages/api`.

## Web package

All forms in `packages/web` use `react-hook-form` with a zod resolver. Do not hand-roll form
state.

Server state in `packages/web` uses the generated client in `packages/web/src/api-client/`.

## Database

Migrations: `pnpm --filter @acme/db migrate`. Generate one with
`pnpm --filter @acme/db drizzle-kit generate`.

Never edit a migration that has been merged to main — add a new one.

## Style

- Formatting is handled by Prettier on commit; do not reformat files by hand.
- Use TypeScript. Avoid `any`.
- Write clear, self-documenting code.
- Keep functions short.

## Testing

Run `pnpm turbo run test` before pushing.

Every handler must have a test in `packages/api/test/routes/`.

## Reminder

Remember to use conventional commit messages for all commits.
