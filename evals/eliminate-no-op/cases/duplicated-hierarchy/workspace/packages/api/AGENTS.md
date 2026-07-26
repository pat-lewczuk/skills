# packages/api

Fastify service. Node 22.

- Every route handler calls `assertSession(req)` first. There is no global auth middleware.
- Plugins register in `src/plugins/index.ts`, in dependency order.
- Handlers get a test in `test/routes/`.
- Run tests: `pnpm --filter @acme/api test`
- Postgres access goes through `@acme/db`. Never import `pg` here.
- Rate limiting is per-route, configured in `src/plugins/rate-limit.ts`. The default is 60/min.
