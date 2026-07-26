# AGENTS.md

`ratchet` reconciles Stripe payouts against our ledger. One Python package, no service layer.

Read this file before making changes.

## Commands

- Install dev deps: `uv sync --group dev`
- Run locally: `uv run ratchet reconcile --since 2024-01-01`
- Unit tests: `uv run pytest -q`
- Integration tests: `uv run pytest -m integration` — needs `STRIPE_TEST_KEY` in the env
- Lint: `uv run ruff check .`
- Regenerate API models: `make codegen`

## Conventions

- All money is `int` cents. Never float. `Decimal` appears only inside `ratchet/rates.py`.
- Every Stripe call goes through `ratchet/stripe_client.py` — it owns the retry policy and the
  idempotency-key scheme. A direct `stripe.*` call bypasses both.
- New subcommands register in the `COMMANDS` dict in `ratchet/cli.py`. There is no plugin
  discovery mechanism.
- Fixtures in `tests/fixtures/` are anonymised real payout payloads. Do not regenerate them
  from live data.
- Follow the existing code style.

## Gotchas

- The sandbox Stripe account rate-limits at 25 req/s. `--concurrency` above 8 trips it.
- `reconcile` is not idempotent before v2.3. If it fails midway, run `ratchet rollback
  --run-id <id>` before retrying, or the second pass double-credits.
- Ledger timestamps are UTC; Stripe's are account-local. Convert with `ratchet/time.py`; do not
  call `datetime.astimezone` directly.
- `--dry-run` still writes to `.ratchet-cache/`. Delete it between test runs.

## Scope

- Do not edit `ratchet/generated/` — regenerated from the OpenAPI spec.
- Schema changes need a migration in `migrations/` and an entry in `CHANGELOG.md`.
- Payout logic changes need sign-off from finance before merge. Ask in #ledger.
