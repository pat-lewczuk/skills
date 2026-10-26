# Customer portal

B2B self-service portal. Each customer company (an `Organization`) gets its own users;
users submit change requests and attach documents; company admins manage their own users.

- Next.js 15 app router, API under `app/api/`
- Postgres via Prisma (`prisma/schema.prisma`)
- Auth.js credentials login, JWT session carrying `userId`, `organizationId`, `role`
- Uploads go to S3 (`lib/storage.ts`)
- Support chatbot at `/support` (`app/api/chat/route.ts`), OpenAI via the Vercel AI SDK

Every API route scopes its queries by the session's `organizationId`.

Deployed on Vercel; Postgres on Neon; S3 bucket `portal-uploads-prod`.
