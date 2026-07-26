# Deploy runbook

1. `deploy/preflight.sh` — checks migrations are applied in staging.
2. Canary at 5% for 15 minutes. Watch `checkout.payment.error_rate`.
3. Rollback: `deploy/rollback.sh <release-sha>`. Never roll back across a schema migration.
