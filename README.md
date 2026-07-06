# Olist Sales Analytics Platform — Data Engineering Challenge

This project is a complete solution for the **Data Engineering Challenge — Olist Sales Analytics**, building a 3-tier Data Warehouse (Bronze, Silver, Gold) integrated with USD exchange rates from the Frankfurter API and orchestrated via Apache Airflow.

---

## 1. System Architecture & Modeling

The system is designed as a **Star Schema** to optimize BI query performance, divided into 3 tiers:
1. **Raw (Bronze):** Raw ingestion of data from the 8 Olist CSV files and the Frankfurter API exchange rates.
2. **Staging (Silver):** Data cleaning, type casting, and translation of product categories (Portuguese → English).
3. **Core (Gold):** Composed of 2 independent Fact tables to prevent fan-out row inflation (`fact_order_items`, `fact_order_payments`) and 4 Dimension tables (`dim_products`, `dim_customers` with SCD Type 2, `dim_date`, and `dim_exchange_rates` supporting weekend rate forward-fill).

*Detailed architecture and business analysis can be found at: [design_document.md](design_document.md)*

---

## 2. Directory Structure

```
TC-Data-Test/
├── README.md                           # This guide
├── design_document.md                  # System architecture design document
├── challenge_requirements.md           # Challenge requirements summary
├── docker-compose.yml                  # Postgres 15 + Airflow (LocalExecutor) setup
│
├── ingestion/                          # Extract & Load (Python + uv)
│   ├── pyproject.toml                  # uv project configuration
│   ├── uv.lock                         # Dependencies lockfile
│   └── src/
│       ├── load_csv.py                 # Ingest Olist CSVs (TRUNCATE + INSERT)
│       └── fetch_exchange_rates.py     # Ingest Frankfurter rates (UPSERT)
│
├── dbt_project/                        # Transformation & DQ (dbt)
│   ├── dbt_project.yml                 # dbt configuration
│   ├── profiles.yml                    # Postgres database connection profile
│   ├── snapshots/                      # snap_customers.sql (SCD Type 2 snapshot)
│   ├── models/                         # Staging & Core models
│   └── tests/                          # Custom tests (Reconciliation & Fan-out)
│
├── airflow/                            # Orchestration (Airflow)
│   ├── Dockerfile                      # Airflow image with dbt + uv packages
│   └── dags/                           # 2 DAGs for automated workflow management
│
├── reports/                            # Power BI Dashboard file (.pbix)
├── data/                               # Raw CSV files directory (downloaded via script)
├── evidence/                           # Screenshots proving DQ + DAG execution results
└── scripts/
    ├── download_data.py                # Automate dataset download from Kaggle
    ├── init_db.sql                     # Initialize schemas for Postgres
    └── setup.ps1                       # One-click initialization script for Windows
```

---

## 3. Quick Start Guide

### Prerequisites:
1. **Docker Desktop** (Running).
2. **uv** (Python package manager). *Install quickly via PowerShell: `pip install uv`*
3. **Power BI Desktop** (To view the interactive dashboard).

### Automated Setup via PowerShell (Recommended)
Open PowerShell at the project root directory and run:
```powershell
.\scripts\setup.ps1
```
*This script will automatically: copy `.env.example` -> `.env`, create a Python venv, download the Olist dataset to the `data/` directory, and spin up Docker containers for Postgres and Airflow.*

---

## 4. Manual Operation & Testing

### Step 1: Ingestion
Ingest the 8 Olist CSV files and backfill 2 years of exchange rates from the Frankfurter API (2016-2018):
```bash
cd ingestion
# Activate venv
.venv\Scripts\activate

# Ingest CSVs
uv run python src/load_csv.py

# Backfill exchange rates (Single API call for 2 years range)
uv run python src/fetch_exchange_rates.py --backfill
```

### Step 2: Run dbt (Transformation & Data Quality Testing)
```bash
cd ../dbt_project
# Download dbt-utils packages
dbt deps

# Run snapshot for SCD Type 2 Customers dimension
dbt snapshot

# Build the complete Star Schema models
dbt run

# Run all automated data quality tests
dbt test
```

---

## 5. Connecting & Designing Dashboard on Power BI

Since the Power BI report file (`.pbix`) is a binary format, you need to open Power BI Desktop on your local machine to connect directly to the PostgreSQL Data Warehouse running inside the Docker container:

### 1. Configure PostgreSQL Connection:
* Open **Power BI Desktop**.
* Select **Get Data** $\rightarrow$ **PostgreSQL database**.
* Fill in the connection settings:
  * **Server:** `localhost:5432`
  * **Database:** `olist_warehouse`
  * **Data Connectivity mode:** Select **Import** (for Power BI to load and compress data, optimizing performance).
* At the credentials screen, select the **Database** tab and enter:
  * **User:** `olist_admin`
  * **Password:** `olist_secret_2024`

### 2. Import Tables (Schema `public_core`):
Select and import the Gold-tier tables (cleaned and modeled via dbt):
* `fact_order_items`
* `fact_order_payments`
* `dim_customers`
* `dim_products`
* `dim_date`
* `dim_exchange_rates`

### 3. Airflow UI (Orchestrator):
* URL: `http://localhost:8080` (User: `admin` / Password: `admin`).
* 2 DAGs run automatically:
  - **`dag_refresh_dimensions`** (Runs daily at 00:00 UTC): Refreshes product catalog, customers, and executes the SCD Type 2 snapshot.
  - **`dag_refresh_facts`** (Runs 3 times daily): Fetches the latest exchange rates, incrementally loads order records, and runs the revenue reconciliation test.

---

## 6. Idempotency & Reconciliation Verification

* **Idempotency:** You can execute `dbt run` or ingestion scripts as many times as you like. The row count and revenue metrics in `fact_order_items` will never be duplicated or inflated.
* **Cross-Reconciliation:** The `reconcile_revenue` test automatically compares the revenue calculated from goods value (`fact_order_items.price + freight`) against the total payments (`fact_order_payments.payment_value`) for each order. Any order with a discrepancy > 1 BRL will immediately trigger a test warning.
* *Detailed screenshots of evidence are documented in: [writeup.md](writeup.md)*
