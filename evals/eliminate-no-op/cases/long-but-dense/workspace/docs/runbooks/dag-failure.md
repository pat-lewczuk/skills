# dag-failure

1. Check `logical_date` and whether the upstream partition landed.
2. Late data is the usual cause. Re-run the task, not the DAG.
