from airflow import DAG

with DAG("daily_orders", catchup=False, schedule="0 3 * * *") as dag:
    pass
