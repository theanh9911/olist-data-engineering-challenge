"""
Fetch historical exchange rates from Frankfurter API → PostgreSQL raw schema.

API Documentation: https://api.frankfurter.dev/v1/
Key note from API docs: "Frankfurter stores dates in UTC."

Idempotency strategy: UPSERT (INSERT ON CONFLICT DO UPDATE)
- Mỗi ngày chỉ có 1 tỷ giá → dùng date_day làm natural key.
- Chạy lại bao nhiêu lần cũng không tạo duplicate.

Two modes:
1. Backfill: Lấy toàn bộ lịch sử bằng Range Query (1 API call duy nhất)
2. Daily:   Lấy tỷ giá ngày hôm nay (1 API call)

Usage:
    # Backfill toàn bộ lịch sử
    uv run python src/fetch_exchange_rates.py --backfill

    # Chỉ lấy ngày hôm nay (hoặc ngày cụ thể)
    uv run python src/fetch_exchange_rates.py --date 2018-08-15
"""

import argparse
import sys
import time
import requests
import psycopg2
from psycopg2 import sql
from datetime import date

from config import get_connection_string


# ============================================================
# Frankfurter API Configuration
# ============================================================
API_BASE_URL = "https://api.frankfurter.dev/v1"
FROM_CURRENCY = "BRL"
TO_CURRENCY = "USD"

# Olist dataset date range
BACKFILL_START = "2016-01-01"
BACKFILL_END = "2018-12-31"

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 5


def fetch_rates_range(start_date: str, end_date: str) -> dict:
    """
    Fetch exchange rates for a date range using Frankfurter Range Query.
    Returns: {date_string: rate_value}

    Example API call:
        GET /2016-01-01..2018-12-31?from=BRL&to=USD
    """
    url = f"{API_BASE_URL}/{start_date}..{end_date}"
    params = {"from": FROM_CURRENCY, "to": TO_CURRENCY}

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"  API call: {url} (attempt {attempt}/{MAX_RETRIES})")
            response = requests.get(url, params=params, timeout=60)
            response.raise_for_status()

            data = response.json()
            rates = {}

            # Response format: {"rates": {"2016-01-04": {"USD": 0.25}, ...}}
            for date_str, currencies in data.get("rates", {}).items():
                if TO_CURRENCY in currencies:
                    rates[date_str] = currencies[TO_CURRENCY]

            print(f"  [OK] Received {len(rates)} daily rates")
            return rates

        except requests.exceptions.RequestException as e:
            print(f"  [WARNING] Attempt {attempt} failed: {e}")
            if attempt < MAX_RETRIES:
                wait = RETRY_DELAY_SECONDS * attempt
                print(f"    Retrying in {wait}s...")
                time.sleep(wait)
            else:
                raise RuntimeError(f"Failed after {MAX_RETRIES} attempts: {e}")


def fetch_rate_single(target_date: str) -> dict:
    """
    Fetch exchange rate for a single date.
    Returns: {date_string: rate_value}
    """
    url = f"{API_BASE_URL}/{target_date}"
    params = {"from": FROM_CURRENCY, "to": TO_CURRENCY}

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()

            data = response.json()
            rate_date = data.get("date", target_date)
            rate_value = data.get("rates", {}).get(TO_CURRENCY)

            if rate_value is None:
                print(f"  [WARNING] No rate found for {target_date} (weekend/holiday?)")
                return {}

            return {rate_date: rate_value}

        except requests.exceptions.RequestException as e:
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_SECONDS * attempt)
            else:
                raise


def upsert_rates_to_db(rates: dict, conn_string: str) -> int:
    """
    UPSERT exchange rates into raw.exchange_rates.
    Idempotent: INSERT ON CONFLICT (date_day) DO UPDATE.

    Returns: number of rows upserted
    """
    if not rates:
        print("  No rates to upsert.")
        return 0

    conn = psycopg2.connect(conn_string)
    conn.autocommit = False

    try:
        cur = conn.cursor()

        # Ensure schema and table exist
        cur.execute("CREATE SCHEMA IF NOT EXISTS raw;")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS raw.exchange_rates (
                date_day       DATE PRIMARY KEY,
                from_currency  TEXT NOT NULL DEFAULT 'BRL',
                to_currency    TEXT NOT NULL DEFAULT 'USD',
                rate           NUMERIC(18, 8) NOT NULL,
                fetched_at     TIMESTAMP DEFAULT NOW()
            );
        """)

        # UPSERT each rate
        upsert_sql = """
            INSERT INTO raw.exchange_rates (date_day, from_currency, to_currency, rate, fetched_at)
            VALUES (%s, %s, %s, %s, NOW())
            ON CONFLICT (date_day) DO UPDATE SET
                rate = EXCLUDED.rate,
                fetched_at = NOW();
        """

        rows_upserted = 0
        for date_str, rate_value in sorted(rates.items()):
            cur.execute(upsert_sql, (date_str, FROM_CURRENCY, TO_CURRENCY, rate_value))
            rows_upserted += 1

        conn.commit()
        print(f"  [OK] Upserted {rows_upserted} rates into raw.exchange_rates")
        return rows_upserted

    except Exception as e:
        conn.rollback()
        print(f"  ERROR: {e}")
        raise
    finally:
        conn.close()


def get_order_date_range(conn_string: str) -> tuple:
    """
    Query raw.orders dynamically to find the actual min and max order purchase dates.
    Returns: (min_date_str, max_date_str) in YYYY-MM-DD format, or a fallback.
    """
    try:
        conn = psycopg2.connect(conn_string)
        cur = conn.cursor()
        cur.execute("SELECT MIN(order_purchase_timestamp)::date, MAX(order_purchase_timestamp)::date FROM raw.orders;")
        min_date, max_date = cur.fetchone()
        conn.close()
        if min_date and max_date:
            # Start backfill from Jan 1st of the minimum order year to fully cover the dim_date spine
            start_date = f"{min_date.year}-01-01"
            return start_date, max_date.isoformat()
    except Exception as e:
        print(f"  [WARNING] Could not query raw.orders dynamically: {e}. Using fallback range.")
    return BACKFILL_START, BACKFILL_END


def fetch_and_upsert_rates(target_date: str, conn_string: str) -> None:
    """
    Fetch exchange rate for target_date.
    Checks raw.orders for the actual data range and dynamically backfills
    if historical rates coverage is missing or insufficient.
    """
    import datetime

    # 1. Dynamically detect the date range of actual orders in database
    start_date, end_date = get_order_date_range(conn_string)

    # 2. Check current coverage of exchange rates for this range
    has_sufficient_history = False
    try:
        conn = psycopg2.connect(conn_string)
        cur = conn.cursor()
        cur.execute(
            "SELECT MIN(date_day), MAX(date_day), COUNT(*) FROM raw.exchange_rates WHERE date_day BETWEEN %s AND %s;",
            (start_date, end_date)
        )
        min_db_date, max_db_date, count = cur.fetchone()
        conn.close()

        if min_db_date and max_db_date:
            d_start = datetime.date.fromisoformat(start_date)
            d_end = datetime.date.fromisoformat(end_date)
            total_days = (d_end - d_start).days + 1

            # Check boundaries (allowing 5 days buffer for weekends/holidays at start/end)
            has_start_covered = (min_db_date - d_start).days <= 5
            has_end_covered = (d_end - max_db_date).days <= 5
            has_good_density = count >= int(total_days * 0.5)

            if has_start_covered and has_end_covered and has_good_density:
                has_sufficient_history = True
                print(f"  [INFO] Found adequate history coverage: {count}/{total_days} days (from {min_db_date} to {max_db_date}). Skipping backfill.")
    except Exception as e:
        print(f"  [WARNING] Error checking coverage: {e}")
        pass

    # 3. Trigger dynamic backfill if history is missing or boundaries are not covered
    if not has_sufficient_history:
        print(f"  [INFO] Insufficient history coverage for range {start_date} -> {end_date}. Triggering dynamic backfill...")
        rates = fetch_rates_range(start_date, end_date)
        upsert_rates_to_db(rates, conn_string)

    # 4. Fetch and upsert the specific target date
    print(f"  [INFO] Fetching exchange rate for target date: {target_date}")
    rates = fetch_rate_single(target_date)
    if rates:
        upsert_rates_to_db(rates, conn_string)


def main():
    parser = argparse.ArgumentParser(description="Fetch Frankfurter FX rates → PostgreSQL")
    parser.add_argument("--backfill", action="store_true", help="Fetch full historical range")
    parser.add_argument("--date", type=str, help="Fetch rate for a specific date (YYYY-MM-DD)")
    args = parser.parse_args()

    print("=" * 60)
    print("Frankfurter API → PostgreSQL raw.exchange_rates")
    print(f"Currency pair: {FROM_CURRENCY} → {TO_CURRENCY}")
    print("Strategy: UPSERT (INSERT ON CONFLICT DO UPDATE)")
    print("=" * 60)

    conn_string = get_connection_string()

    if args.backfill:
        print(f"\nMode: BACKFILL ({BACKFILL_START} → {BACKFILL_END})")
        print("Using Range Query (1 API call for entire history)\n")
        rates = fetch_rates_range(BACKFILL_START, BACKFILL_END)
        upsert_rates_to_db(rates, conn_string)

    elif args.date:
        print(f"\nMode: SINGLE DATE ({args.date})\n")
        rates = fetch_rate_single(args.date)
        upsert_rates_to_db(rates, conn_string)

    else:
        # Default: fetch today's rate
        today = date.today().isoformat()
        print(f"\nMode: TODAY ({today})\n")
        rates = fetch_rate_single(today)
        upsert_rates_to_db(rates, conn_string)

    print(f"\n{'=' * 60}")
    print("Done!")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
