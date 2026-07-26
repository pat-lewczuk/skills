# Engineering Agent Guidelines — Helios Platform

You are a highly skilled software engineer working on Helios. Your goal is to produce
excellent work. Please follow every guideline in this document.

## Philosophy

We believe in simplicity over cleverness, and in leaving the codebase better than we found it.
Quality is everyone's responsibility.

## Before you start

1. Read this document in full.
2. Run `make setup` to install the toolchain.
3. Read `docs/adr/README.md` to understand why the architecture is the way it is.

## Coding standards

- Write readable, well-structured, idiomatic Go.
- Use `gofmt`. Run `make lint` before committing.
- Error messages start lowercase and do not end with punctuation.
- Wrap errors with `fmt.Errorf("...: %w", err)` — never with `errors.New` on a wrapped value.
- Do not introduce new interfaces with a single implementation.
- Handle all errors. Never ignore a returned error.
- Table-driven tests only. See `internal/billing/rate_test.go` for the shape we use.

## Architecture

- HTTP handlers in `internal/api/handlers/` stay thin: parse, call a service, render.
- Services in `internal/service/` hold business logic and never touch `net/http` types.
- Storage is behind `internal/store.Store`. No SQL outside that package.
- Background jobs are registered in `cmd/worker/main.go`. A job must be idempotent — the
  scheduler retries on any non-nil error.

## Operations

- Feature flags are read once at startup. A flag change needs a rolling restart.
- Never log a full request body — it may contain card data. Use `redact.Body`.
- Panics in a handler are recovered by middleware, but a panic in a job kills the worker.

## Reviews

- Be respectful and constructive in code review.
- Keep pull requests focused and reasonably sized.

## Finally

Thank you for your contributions to Helios! Remember: always strive for excellence.
