"""
Load Olist CSV files into PostgreSQL raw schema.

Idempotency strategy: TRUNCATE + INSERT
- Mỗi lần chạy sẽ xóa sạch bảng raw rồi nạp lại từ đầu.
- Đảm bảo chạy lại bao nhiêu lần cũng cho cùng kết quả.
- An toàn cho cả Historical Backfill lẫn Daily Refresh.

Usage:
    uv run python src/load_csv.py
"""

import sys
import pandas as pd
import psycopg2
from psycopg2 import sql
from io import StringIO
from pathlib import Path

from config import get_connection_string, get_data_dir


# ============================================================
# Mapping: CSV filename → raw table name
# ============================================================
CSV_TABLE_MAPPING = {
    "olist_orders_dataset.csv": "orders",
    "olist_order_items_dataset.csv": "order_items",
    "olist_order_payments_dataset.csv": "order_payments",
    "olist_customers_dataset.csv": "customers",
    "olist_products_dataset.csv": "products",
    "olist_sellers_dataset.csv": "sellers",
    "product_category_name_translation.csv": "category_translation",
    # order_reviews is intentionally excluded from MVP — see Design Document Section 9.3
    # Geolocation is intentionally excluded — see Design Document Section 2.3
}

# Tables to skip loading (documented exclusions)
EXCLUDED_FILES = {
    "olist_geolocation_dataset.csv",  # Fan-out risk, not used in MVP
    "olist_order_reviews_dataset.csv",  # Excluded due to duplicate review_id & comments issues
}


def load_csv_to_raw(data_dir: str, conn_string: str) -> dict:
    """
    Load all CSV files into PostgreSQL raw schema.

    Returns:
        dict: {table_name: row_count} for verification
    """
    data_path = Path(data_dir)
    results = {}

    if not data_path.exists():
        print(f"ERROR: Data directory not found: {data_path}")
        print("Run: uv run python scripts/download_data.py")
        sys.exit(1)

    conn = psycopg2.connect(conn_string)
    conn.autocommit = False

    try:
        cur = conn.cursor()

        # Ensure raw schema exists
        cur.execute("CREATE SCHEMA IF NOT EXISTS raw;")

        for csv_filename, table_name in CSV_TABLE_MAPPING.items():
            csv_path = data_path / csv_filename

            if not csv_path.exists():
                print(f"  [SKIP] {csv_filename} not found")
                continue

            print(f"  Loading {csv_filename} → raw.{table_name}...", end=" ")

            # Read CSV with pandas (handles encoding, dtypes)
            df = pd.read_csv(csv_path, low_memory=False)

            # Clean carriage returns and newlines in text fields to prevent PostgreSQL COPY format errors
            df = df.replace(to_replace=[r'\r', r'\n'], value=' ', regex=True)

            # === IDEMPOTENCY: Drop + Recreate ===
            # Using DROP + CREATE instead of TRUNCATE to handle schema changes
            cur.execute(
                sql.SQL("DROP TABLE IF EXISTS raw.{} CASCADE").format(
                    sql.Identifier(table_name)
                )
            )

            # Build CREATE TABLE from DataFrame dtypes
            col_defs = []
            for col_name, dtype in df.dtypes.items():
                # Use TEXT for all columns in raw layer — casting happens in dbt staging
                col_defs.append(
                    sql.SQL("{} TEXT").format(sql.Identifier(col_name))
                )

            create_stmt = sql.SQL("CREATE TABLE raw.{} ({})").format(
                sql.Identifier(table_name),
                sql.SQL(", ").join(col_defs),
            )
            cur.execute(create_stmt)

            # === Bulk COPY for performance ===
            # Convert DataFrame to CSV string buffer
            buffer = StringIO()
            df.to_csv(buffer, index=False, header=False, sep="\t", na_rep="\\N")
            buffer.seek(0)

            copy_stmt = sql.SQL("COPY raw.{} FROM STDIN WITH (FORMAT text, NULL '\\N')").format(
                sql.Identifier(table_name)
            )
            cur.copy_expert(copy_stmt, buffer)

            row_count = len(df)
            results[table_name] = row_count
            print(f"  [OK] {row_count:,} rows")

        conn.commit()
        print(f"\n{'=' * 50}")
        print("All tables loaded successfully into raw schema.")
        print(f"Total: {sum(results.values()):,} rows across {len(results)} tables")
        print(f"{'=' * 50}")

    except Exception as e:
        conn.rollback()
        print(f"\nERROR: {e}")
        raise
    finally:
        conn.close()

    return results


if __name__ == "__main__":
    print("=" * 50)
    print("Olist CSV Ingestion → PostgreSQL raw schema")
    print("Strategy: DROP + CREATE + COPY (Idempotent)")
    print("=" * 50)

    data_dir = get_data_dir()
    conn_string = get_connection_string()

    print(f"Data directory: {data_dir}")
    print("Loading...\n")

    results = load_csv_to_raw(data_dir, conn_string)
