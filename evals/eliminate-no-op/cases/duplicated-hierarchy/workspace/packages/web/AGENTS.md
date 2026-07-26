# packages/web

Next.js 15 app. Dev server on port 3210.

- The API client in `src/api-client/` is generated. Do not edit it by hand; run
  `pnpm --filter @acme/web codegen` after an API change.
- Route groups mirror the marketing/app split; see `src/app/(marketing)` and `src/app/(app)`.
