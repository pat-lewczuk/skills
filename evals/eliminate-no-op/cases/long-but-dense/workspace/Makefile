airflow-up:
	docker compose -f dags/docker-compose.yml up -d
dag-test:
	PYTHONPATH=. airflow dags test $(DAG) 2024-01-01
feature-backfill:
	PYTHONPATH=. python -m features.backfill --view $(VIEW) --from $(FROM)
tf-plan:
	./infra/tfwrap plan $(ENV)
test:
	PYTHONPATH=. pytest -q tests/unit
test-integration:
	PYTHONPATH=. pytest -q tests/integration
.PHONY: airflow-up dag-test feature-backfill tf-plan test test-integration
