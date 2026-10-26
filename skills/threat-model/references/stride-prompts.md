# STRIDE prompts

Ask these for every entry point and every flow that crosses a trust boundary. The
questions are prompts for finding threats, not a checklist to fill with "yes". When a
letter does not apply, say so in one line and move on; silently skipping one is how
whole classes of bugs get missed.

## Classic web and API

**S: Spoofing.** Who can pretend to be someone else here? Can a request arrive without
a session? Can a session, JWT or API key be guessed, replayed or reused after logout?
Can a webhook be called by anyone who knows the URL? Can a user set their own
`userId` or `organizationId` in the payload?

**T: Tampering.** What can be modified in transit or at rest? Hidden form fields,
client-side state, query parameters, file contents, prices and quantities (negative
values, zero, overflow), order of steps in a workflow (skipping approval), uploaded
files that are later executed or parsed.

**R: Repudiation.** If a user or an agent does something harmful, can we prove who and
when? Are sensitive actions logged with actor, time and target? Are logs writable by
the application user? Does the log leak secrets or personal data?

**I: Information disclosure.** Who can read what they should not? Objects by ID
(IDOR), list endpoints without tenant scoping, error messages with stack traces,
verbose API responses with extra fields, secrets in the repository or environment,
backups and exports, caches shared between users.

**D: Denial of service.** What is expensive here? Unbounded list queries, file uploads
without size limits, regex on user input, external calls without timeouts, anything
that costs money per request (LLM tokens, SMS, email).

**E: Elevation of privilege.** How does a standard user become admin, or a user of
tenant A act in tenant B? Missing role checks on POST / PUT / DELETE, authorization
only in the UI, role stored in a cookie or token the client can change, admin
endpoints discoverable by guessing paths, mass assignment of `role` or `isAdmin`.

## Other application types

The letters are the same; the boundary moves. Ask the classic questions against the
input the application trusts.

**Background worker or queue consumer.** Who can put a message on the queue (S)? Can a
message carry another tenant's ID or an arbitrary file path (T, E)? Is a failed job
retried forever or does it poison the queue (D)? Does the worker run with broader
credentials than the API that enqueued the job (E)? Is there a record of which job did
what (R)?

**Scheduled job or batch pipeline.** Where do input files come from and who can write
there (T)? Does the job read a path or a config it does not own (E)? Is the output
visible to people who could not see the input (I)? What happens when it runs twice or
on stale data (T, D)?

**CLI.** Arguments, config files, environment variables and the working directory are
all inputs. Can a repository or a project directory the CLI runs in change its
behaviour (T, E; this is how AI coding tools got CVEs)? Does it print or log secrets
(I)? Does it execute anything from its input (E)?

**Serverless function.** The function's IAM role is its blast radius (E). Event
payloads are untrusted even when they come from "internal" services (S, T). Timeouts
and concurrency limits are the DoS and cost controls (D).

**MCP server.** The connecting agent is an untrusted caller: validate tool arguments
as you would API parameters (T, E). The server's own credentials should be the
narrowest that still work (E). Every tool invocation should be logged with its
arguments (R). Tool descriptions and results flow into a model's context, so they are
an injection channel in both directions (see AI components below).

**Mobile backend.** The app is attacker-controlled: any check that happens only in the
client does not exist (E). Certificate pinning, device tokens and push notification
endpoints are entry points (S, I).

## AI components

Apply these to any place where model output influences what the system does
(a chatbot answer, an agent's tool call, generated code, a summary a person acts on).

**Lethal trifecta.** Does the component (1) process untrusted content, (2) have access
to private data or sensitive systems, (3) have a way to change state or communicate
externally? The third property includes subtle channels: rendering a Markdown link or
image whose URL carries data, writing to a memory or RAG store that other sessions
read, creating records another system acts on. With all three present, assume prompt
injection succeeds and design for containment: remove a property for that session or
put a human approval in front of the state change.

**Goal hijack and injection (ASI01, LLM01).** Where does untrusted text enter the
model's context? User messages, uploaded documents, emails, web pages, tool results,
database rows written by other users, previous conversation memory. Is content from
those sources separated from instructions, and does the application constrain what the
model may do regardless of what its context says?

**Excessive agency (LLM03, ASI02, ASI03).** Which tools does the model have and with
whose credentials? Can a tool that should only read also write or delete? Does the
agent use a human's token or a service account broader than the task? Is every
privileged action validated by deterministic code at execution time, not by the prompt?

**Data exposure through the model (LLM02, LLM08).** Can the model be asked for another
user's data? Do the retrieval or data tools enforce the same tenant and role scoping as
the API? Does the system prompt contain secrets or policy logic that leaks on request?
Treat tool arguments, retrieved chunks and logs as outputs subject to the same rules as
the answer.

**Memory and retrieval poisoning (ASI06, LLM05, LLM09).** Can a user write something
today that changes the model's behaviour in another user's session tomorrow? Shared
vector stores, long-term memory, cached summaries.

**Unbounded consumption (LLM06).** Is there a per-user rate limit and a spend ceiling?
A rate limit that allows expensive requests does not stop a denial-of-wallet attack.

**Supply chain of the agent (ASI04, MCP Top 10, Agentic Skills Top 10).** Which MCP
servers, skills, plugins and model providers does the system load, and from where? Are
they pinned and reviewed, or discovered at runtime?

**Human-agent trust (ASI09).** Where does a person approve something based on the
model's summary? Does the approval screen show the raw action, or only what the model
chose to say about it?

## Scoring

Likelihood: High if an anonymous or low-privilege user can trigger it with ordinary
tools; Medium if it needs a valid account plus some effort; Low if it needs insider
access or a rare precondition. Impact: High for cross-tenant data exposure, account
takeover, money, destructive actions; Medium for single-user data or availability of a
feature; Low for cosmetic or self-inflicted effects. Work the High / High rows first.
