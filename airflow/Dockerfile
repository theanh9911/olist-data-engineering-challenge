FROM apache/airflow:2.8.1-python3.11

USER root

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

USER airflow

# Install Python packages
RUN pip install --no-cache-dir \
    dbt-postgres==1.7.* \
    psycopg2-binary \
    pandas \
    requests \
    python-dotenv

# Working directory
WORKDIR /opt/airflow
