-- snap_customers.sql
-- dbt Snapshot for SCD Type 2 tracking of customer geography
-- Design Doc Section 2.1: Track customer_state changes over time
-- Strategy: check — monitors customer_state for changes

{% snapshot snap_customers %}

{{
    config(
        target_schema='snapshots',
        unique_key='customer_unique_id',
        strategy='check',
        check_cols=['customer_state'],
    )
}}

-- Deduplicate: take the LATEST customer record per customer_unique_id
-- (a customer_unique_id can have multiple customer_ids from different orders)
-- Join with raw.orders to sort by purchase timestamp chronologically, as customer_id is a random hash.
WITH ranked AS (
    SELECT
        c.customer_unique_id,
        c.customer_state,
        c.customer_city,
        c.customer_zip_code_prefix,
        ROW_NUMBER() OVER (
            PARTITION BY c.customer_unique_id
            ORDER BY COALESCE(o.order_purchase_timestamp::timestamp, '1970-01-01'::timestamp) DESC, c.customer_id DESC
        ) AS rn
    FROM {{ source('raw', 'customers') }} c
    LEFT JOIN {{ source('raw', 'orders') }} o
        ON c.customer_id = o.customer_id
)

SELECT
    customer_unique_id,
    customer_state,
    customer_city,
    customer_zip_code_prefix
FROM ranked
WHERE rn = 1

{% endsnapshot %}
