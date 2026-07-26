# AGENTS.md — Atlas data platform

Monorepo for the data platform: Airflow DAGs, dbt models, a feature store, the training
pipeline, and the Terraform that runs it. Five domains, one repo, one on-call rotation.

## Orientation

- `dags/` — Airflow 2.9 DAGs. One file per DAG, filename equals `dag_id`.
- `dbt/` — dbt-core 1.8 project, warehouse is Snowflake.
- `features/` — feature store definitions (Feast 0.40) plus their backfill jobs.
- `training/` — PyTorch training code and the Metaflow flows that run it.
- `infra/` — Terraform 1.9, one workspace per environment.
- `platform/` — shared Python library. Everything else depends on it; it depends on nothing.

Run everything through `make`. Bare `python` invocations miss the `PYTHONPATH` shim.

## Airflow

- DAGs must be importable in under 2 seconds. The scheduler kills slow imports and the DAG
  silently disappears. Keep imports at module scope minimal; import inside the task callable.
- Never use `datetime.now()` in a DAG — use the `logical_date` from the task context, or
  backfills produce different data than the original run did.
- `catchup=False` on every new DAG unless the DAG is explicitly a backfill.
- Task retries: 2 for anything that hits Snowflake, 0 for anything that writes to Kafka.
  Kafka producers are not idempotent yet.
- Cross-DAG dependencies go through `ExternalTaskSensor` with `poke_interval=300`. Do not use
  `TriggerDagRunOperator` — it hides the dependency from the lineage graph.
- Local run: `make airflow-up`, then `make dag-test DAG=<dag_id>`.
- Secrets come from the `atlas/airflow` path in Vault via `platform.secrets.get`. Never read
  `os.environ` directly in a DAG.

## dbt

- Model naming: `stg_<source>__<entity>`, `int_<domain>__<verb>`, `mart_<domain>__<entity>`.
- Every model needs a `unique` and `not_null` test on its primary key. CI fails without them.
- Incremental models must declare `unique_key` and use `merge`. `insert_overwrite` on Snowflake
  silently drops late-arriving rows.
- `dbt build --select state:modified+ --defer --state ./target-base` is the CI command; run it
  locally before pushing or you will wait 20 minutes for CI to tell you.
- Never `dbt run --full-refresh` against `prod` without an approved change ticket. It rebuilds
  4 TB and costs about $900.
- Snowflake warehouse for dev is `WH_DEV_XS`. Anything larger needs finance approval.

## Feature store

- A feature view's `ttl` must exceed the training window or the point-in-time join drops rows.
- Entity keys are strings, always. Integer keys break the Redis online store's key encoding.
- Backfills run through `make feature-backfill VIEW=<name> FROM=<date>`. They are not
  idempotent — check `features/_state/` for a prior run before starting.
- Online and offline definitions live in the same file on purpose. Do not split them.

## Training

- `training/` code must run unchanged on a laptop and on the GPU cluster. Anything
  device-specific goes behind `platform.device.current()`.
- Datasets are read through `platform.data.load`, never `pandas.read_parquet` directly — the
  loader handles the S3 credential refresh that long jobs need.
- Set the seed with `platform.seed.set_all(seed)`. Torch, numpy, and CUDA all need it, and
  three of the four places that matter are easy to forget.
- Checkpoint every 500 steps to `s3://atlas-checkpoints/<flow>/<run_id>/`. Spot instances are
  reclaimed with two minutes' notice.
- A training run that touches customer data needs `--consent-cohort` set. The loader refuses
  to start without it.
- Metrics go to Weights & Biases under the `atlas` entity. Project name equals the flow name.

## Infrastructure

- Terraform: `make tf-plan ENV=staging`. Never run `terraform` directly — the wrapper injects
  the state backend and the assume-role config.
- `prod` applies only from CI on `main`. A local apply to prod will be reverted and will page
  the on-call engineer.
- IAM changes need a second reviewer from the platform team.
- State is in S3 with DynamoDB locking. If a run dies mid-apply, do not force-unlock — ask in
  `#atlas-platform`; a stale lock usually means the apply is still running somewhere.

## On-call

- Runbooks: `docs/runbooks/<alert-name>.md`. Every alert must have one before it can page.
- First response to a DAG failure: check `logical_date` and whether upstream landed. Most
  failures are late data, not code.
- Escalation path is in PagerDuty, not here.
- To silence an alert, use the PagerDuty maintenance window. Do not comment out the alert
  definition — CI has a check that catches it.

## Conventions

- Python 3.12, `ruff` and `mypy --strict` in CI. Type annotations on every public function.
- Write clean, readable code and follow best practices.
- Tests: `make test` runs unit tests; `make test-integration` needs Docker and takes 8 minutes.
- Be thorough and take care when making changes to shared code.
- Commit messages: `<domain>: <imperative>`, where domain is one of the six top-level
  directories.
- Please read this file before starting work, and follow all the guidelines it contains.
