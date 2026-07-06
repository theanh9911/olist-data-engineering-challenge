"""
Database connection configuration for Olist ingestion scripts.
Reads connection parameters from environment variables or uses defaults.
"""

import os
from dotenv import load_dotenv

# Load .env file if exists (for local development)
load_dotenv()


def get_connection_params() -> dict:
    """Return PostgreSQL connection parameters as a dictionary."""
    return {
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": int(os.getenv("POSTGRES_PORT", "5432")),
        "dbname": os.getenv("POSTGRES_DB", "olist_warehouse"),
        "user": os.getenv("POSTGRES_USER", "olist_admin"),
        "password": os.getenv("POSTGRES_PASSWORD", "olist_secret_2024"),
    }


def get_connection_string() -> str:
    """Return PostgreSQL connection string for psycopg2."""
    params = get_connection_params()
    return (
        f"host={params['host']} "
        f"port={params['port']} "
        f"dbname={params['dbname']} "
        f"user={params['user']} "
        f"password={params['password']}"
    )


def get_data_dir() -> str:
    """Return path to the data/ directory containing CSV files."""
    # When running inside Airflow container: /opt/airflow/data
    # When running locally: ../data (relative to ingestion/)
    airflow_data = "/opt/airflow/data"
    if os.path.exists(airflow_data):
        return airflow_data

    # Local development: resolve relative to this file
    from pathlib import Path
    return str(Path(__file__).resolve().parent.parent.parent / "data")
