"""
DAG: Refresh Dimension Tables
Schedule: Daily at 00:00 UTC
Design Doc Section 4.3A

Flow:
    load_raw_csv → dbt_snapshot → dbt_run_dimensions → dbt_test_dimensions
"""

import os
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator

# Ingestion imports (resolved via PYTHONPATH in Docker)
from load_csv import load_csv_to_raw
from fetch_exchange_rates import fetch_and_upsert_rates
from config import get_data_dir, get_connection_string

# Paths resolved from AIRFLOW_HOME (set by Airflow container)
AIRFLOW_HOME = os.environ.get("AIRFLOW_HOME", "/opt/airflow")
DBT_PROJECT_DIR = os.path.join(AIRFLOW_HOME, "dbt_project")


default_args = {
    "owner": "olist_data_team",
    "depends_on_past": False,
    "email_on_failure": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="dag_refresh_dimensions",
    default_args=default_args,
    description="Refresh dimension tables: CSV → Raw → Staging → Core Dims",
    schedule_interval="0 0 * * *",  # Daily at midnight UTC
    start_date=datetime(2018, 1, 1),
    catchup=False,
    tags=["dimensions", "daily"],
) as dag:

    # ============================================================
    # Task 1: Load raw CSV files into PostgreSQL
    # ============================================================
    def _load_csv():
        load_csv_to_raw(get_data_dir(), get_connection_string())

    load_raw_csv = PythonOperator(
        task_id="load_raw_csv",
        python_callable=_load_csv,
    )

    # ============================================================
    # Task 2: Fetch exchange rates from Frankfurter API
    # ============================================================
    def _fetch_rates(**context):
        execution_date = context["ds"]  # YYYY-MM-DD string
        fetch_and_upsert_rates(execution_date, get_connection_string())

    fetch_exchange_rates = PythonOperator(
        task_id="fetch_exchange_rates",
        python_callable=_fetch_rates,
    )

    # ============================================================
    # Task 3: Install dbt dependencies
    # ============================================================
    dbt_deps = BashOperator(
        task_id="dbt_deps",
        bash_command=f"cd {DBT_PROJECT_DIR} && dbt deps --profiles-dir .",
    )

    # ============================================================
    # Task 3: Run dbt snapshot (SCD Type 2 for customers)
    # ============================================================
    dbt_snapshot = BashOperator(
        task_id="dbt_snapshot",
        bash_command=f"cd {DBT_PROJECT_DIR} && dbt snapshot --profiles-dir .",
    )

    # ============================================================
    # Task 4: Run dbt models tagged as 'dimension'
    # ============================================================
    dbt_run_dimensions = BashOperator(
        task_id="dbt_run_dimensions",
        bash_command=f"cd {DBT_PROJECT_DIR} && dbt run --select '+core.dim_*' --profiles-dir .",
    )

    # ============================================================
    # Task 5: Test dimension models
    # ============================================================
    dbt_test_dimensions = BashOperator(
        task_id="dbt_test_dimensions",
        bash_command=f"cd {DBT_PROJECT_DIR} && dbt test --select 'core.dim_*' --profiles-dir .",
    )

    # DAG dependency chain
    load_raw_csv >> fetch_exchange_rates >> dbt_deps >> dbt_snapshot >> dbt_run_dimensions >> dbt_test_dimensions
