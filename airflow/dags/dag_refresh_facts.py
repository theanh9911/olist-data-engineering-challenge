"""
DAG: Refresh Fact Tables
Schedule: 3x daily at 00:30, 08:30, 16:30 UTC
Design Doc Section 4.3B

Flow:
    fetch_exchange_rates → dbt_run_facts → dbt_test_facts
"""

import os
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator

# Ingestion imports (resolved via PYTHONPATH in Docker)
from fetch_exchange_rates import fetch_rate_single, fetch_rates_range, upsert_rates_to_db
from config import get_connection_string

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
    dag_id="dag_refresh_facts",
    default_args=default_args,
    description="Refresh fact tables: API rates → Raw → Staging → Core Facts",
    schedule_interval="30 0,8,16 * * *",  # 3x daily
    start_date=datetime(2018, 1, 1),
    catchup=False,
    tags=["facts", "3x-daily"],
) as dag:

    # ============================================================
    # Task 1: Fetch exchange rates from Frankfurter API
    # ============================================================
    def _fetch_rates(**context):
        execution_date = context["ds"]  # YYYY-MM-DD string
        conn_string = get_connection_string()

        # For backfill (catchup=True), fetch the specific date
        rates = fetch_rate_single(execution_date)
        upsert_rates_to_db(rates, conn_string)

    fetch_exchange_rates = PythonOperator(
        task_id="fetch_exchange_rates",
        python_callable=_fetch_rates,
    )

    # ============================================================
    # Task 2: Install dbt dependencies
    # ============================================================
    dbt_deps = BashOperator(
        task_id="dbt_deps",
        bash_command=f"cd {DBT_PROJECT_DIR} && dbt deps --profiles-dir .",
    )

    # ============================================================
    # Task 3: Run dbt fact models
    # ============================================================
    dbt_run_facts = BashOperator(
        task_id="dbt_run_facts",
        bash_command=f"cd {DBT_PROJECT_DIR} && dbt run --select '+core.fact_*' --profiles-dir .",
    )

    # ============================================================
    # Task 4: Test fact models + reconciliation
    # ============================================================
    dbt_test_facts = BashOperator(
        task_id="dbt_test_facts",
        bash_command=f"cd {DBT_PROJECT_DIR} && dbt test --select 'core.fact_*' --profiles-dir . && dbt test --select 'test_type:singular' --profiles-dir .",
    )

    # ============================================================
    # Task 5: Generate reconciliation and idempotency proof file
    # ============================================================
    def _generate_proof(**context):
        import psycopg2
        conn = psycopg2.connect(get_connection_string())
        cur = conn.cursor()
        
        # Query 1: Prices and Freight sums
        cur.execute("""
            SELECT 
                (SELECT SUM(price::numeric) FROM raw.order_items) AS raw_price,
                (SELECT SUM(price_brl) FROM public_core.fact_order_items) AS gold_price,
                (SELECT SUM(freight_value::numeric) FROM raw.order_items) AS raw_freight,
                (SELECT SUM(freight_brl) FROM public_core.fact_order_items) AS gold_freight;
        """)
        raw_price, gold_price, raw_freight, gold_freight = cur.fetchone()
        
        # Query 2: Payments sums
        cur.execute("""
            SELECT 
                (SELECT SUM(payment_value::numeric) FROM raw.order_payments) AS raw_payment,
                (SELECT SUM(payment_value_brl) FROM public_core.fact_order_payments) AS gold_payment;
        """)
        raw_payment, gold_payment = cur.fetchone()
        
        # Query 3: Row counts
        cur.execute("SELECT COUNT(*) FROM raw.order_items;")
        raw_items_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM public_core.fact_order_items;")
        gold_items_count = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM raw.order_payments;")
        raw_payments_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM public_core.fact_order_payments;")
        gold_payments_count = cur.fetchone()[0]
        
        conn.close()
        
        # Write to shared volume file
        output_path = "/opt/airflow/ingestion/reconciliation_proof.txt"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(f"RAW PRICE: {raw_price}\n")
            f.write(f"GOLD PRICE: {gold_price}\n")
            f.write(f"RAW FREIGHT: {raw_freight}\n")
            f.write(f"GOLD FREIGHT: {gold_freight}\n")
            f.write(f"RAW PAYMENT: {raw_payment}\n")
            f.write(f"GOLD PAYMENT: {gold_payment}\n")
            f.write(f"RAW ITEMS COUNT: {raw_items_count}\n")
            f.write(f"GOLD ITEMS COUNT: {gold_items_count}\n")
            f.write(f"RAW PAYMENTS COUNT: {raw_payments_count}\n")
            f.write(f"GOLD PAYMENTS COUNT: {gold_payments_count}\n")

    generate_reconciliation_proof = PythonOperator(
        task_id="generate_reconciliation_proof",
        python_callable=_generate_proof,
    )

    # DAG dependency chain
    fetch_exchange_rates >> dbt_deps >> dbt_run_facts >> dbt_test_facts >> generate_reconciliation_proof
