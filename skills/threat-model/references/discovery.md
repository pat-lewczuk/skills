# Discovery: what to look for, and where

The goal of discovery is a filled-in System profile: which deployable applications
exist, what type each one is, how they are built, how auth and tenancy work, and where
the AI parts are. Spend the time here; the rest of the model is only as good as this
map. Prefer reading manifests and configuration over grepping the whole tree, and
confirm anything a README claims by finding it in the code.

## Step 1: inventory

| Signal | What it tells you |
| --- | --- |
| `package.json` `workspaces`, `pnpm-workspace.yaml`, `turbo.json`, `nx.json`, `lerna.json` | JS/TS monorepo; each workspace with a start or build script is a candidate application |
| `apps/`, `services/`, `packages/`, `cmd/` (Go), `src/*/` with own manifests | Multiple applications or a modular monolith |
| `docker-compose*.yml`, `Dockerfile*`, `k8s/`, `helm/`, `terraform/`, `serverless.yml`, `vercel.json`, `fly.toml`, `Procfile` | Deployable units and their runtime dependencies (databases, brokers, caches) |
| `package.json`, `composer.json`, `pyproject.toml` / `requirements.txt`, `go.mod`, `Cargo.toml`, `pom.xml` / `build.gradle`, `*.csproj`, `Gemfile`, `mix.exs` | Language and framework per application |
| `.env.example`, `config/`, `settings.py`, `appsettings.json` | External dependencies, secrets expected, feature flags |
| `openapi.*`, `swagger.*`, `schema.graphql`, `*.proto` | API surface, often more complete than the routes |
| `.github/workflows`, `.gitlab-ci.yml` | What gets deployed where, which scans already run |

## Step 2: classify each application

| Type | How to recognize it | Boundary it trusts |
| --- | --- | --- |
| Browser web app | HTML templates, React/Vue/Svelte, Next.js `app/` or `pages/`, server actions | Browser input, cookies, CSRF, XSS matter |
| HTTP API | Route files, controllers, resolvers, no templates | Every request; tokens, object IDs, rate limits |
| Background worker / consumer | Queue clients (BullMQ, Celery, Sidekiq, SQS, Kafka, RabbitMQ), `worker.*`, `consumer.*` | Message payloads; whoever can enqueue |
| Scheduled job | Cron definitions, `schedule`, CI schedules, k8s CronJob | Input files, upstream data, time-of-check |
| CLI | `bin/`, `cmd/`, argparse / commander / clap entry points | Arguments, config files, environment, working directory |
| Serverless function | `handler` exports, `serverless.yml`, `functions/` | Event payloads, IAM role breadth |
| Mobile backend | API consumed by native apps, push notification services | Client is attacker-controlled; never trust client-side checks |
| AI agent or AI feature | LLM SDK imports, system prompts, tool / function definitions, RAG retrieval, agent frameworks | Everything the model reads; everything its tools can do |
| MCP server | `@modelcontextprotocol/sdk`, `mcp` Python package, tool manifests | The connecting agent; tool arguments; the server's own credentials |
| Library | No runtime entry point of its own | Modelled through its consumers |

## Step 3: locate entry points, auth, data and AI parts per stack

| Stack | Entry points | Auth and authorization | Data access |
| --- | --- | --- | --- |
| Next.js / React Router / Remix | `app/**/route.ts`, `app/**/page.tsx`, `pages/api/**`, `"use server"` functions, `middleware.ts` | `middleware.ts`, auth libraries (NextAuth/Auth.js, Clerk, Lucia), session helpers called in handlers | ORM calls (Prisma, Drizzle, MikroORM, TypeORM); look for `where` clauses that include or omit tenant / owner IDs |
| Express / Fastify / Nest / Hono | `router.*`, `app.get`, `@Controller`, `@Get` decorators | `passport`, guards (`@UseGuards`), middleware order, JWT verification | repositories, raw SQL, query builders |
| Symfony / Laravel / other PHP | `config/routes*`, `#[Route]` attributes, `routes/web.php`, `routes/api.php` | security.yaml, voters, policies, gates, middleware groups | Doctrine / Eloquent queries, scopes, `findOneBy` by ID |
| Django / FastAPI / Flask | `urls.py`, `@router.*`, `@app.route` | middleware, `permission_classes`, `Depends(get_current_user)`, decorators | ORM querysets, raw cursors, `.filter()` without tenant |
| Rails | `config/routes.rb`, controllers | `before_action`, Devise, Pundit / CanCan | ActiveRecord scopes, `find` by params |
| Spring / .NET | `@RestController`, `@RequestMapping`, `[ApiController]`, minimal APIs | `@PreAuthorize`, security filter chain, `[Authorize]` policies | JPA / EF queries |
| Go | `http.HandleFunc`, chi / gin / echo routers, `cmd/*/main.go` | middleware chains, context values carrying user | `database/sql`, sqlc, GORM |
| Serverless | `serverless.yml` functions, `handler.*` | API Gateway authorizers, IAM roles per function | SDK calls with the function's role |

AI parts, any stack: imports of `openai`, `@anthropic-ai/sdk`, `anthropic`, `ai`
(Vercel AI SDK), `langchain`, `llamaindex`, `@google/generative-ai`, `ollama`; files
named `prompt*`, `agent*`, `tools*`; `tool` / `function` schemas passed to the model;
vector stores (pgvector, Pinecone, Qdrant, Chroma); `.mcp.json`, `claude_desktop_config`,
`.cursor/mcp.json`; `SKILL.md` folders; memory or conversation stores.

Multi-tenancy, any stack: a column or claim named `tenantId`, `organizationId`,
`accountId`, `workspaceId`, `companyId`; row-level security policies in migrations;
a middleware that resolves the tenant from host, header or token. The threat is wherever
a query uses the record ID but not the tenant ID.

## Step 4: write the profile

Fill the System profile table in the template, one row per application in scope.
Then list the data stores, external systems, and AI components once for the whole
repository. If something could not be determined from the code, say so in
"Assumptions and open questions" rather than guessing. Typical open questions: who
issues sessions in production, whether the API is reachable without the frontend,
whether a worker's queue is writable by anything other than the API.
