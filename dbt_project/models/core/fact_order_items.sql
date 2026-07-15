-- fact_order_items.sql
-- Fact table: 1 row = 1 product item in an order
-- Design Doc Section 5.2: Grain is order_id + order_item_id
-- Converts BRL to USD using dim_exchange_rates (with forward-filled weekend rates)
-- NEVER JOIN this table with fact_order_payments at item grain → Fan-out risk!

{{
    config(
        materialized='incremental',
        unique_key='order_item_key',
        incremental_strategy='merge'
    )
}}

SELECT
    -- Simple Keys & Identifiers
    oi.order_item_key,
    o.order_id,
    oi.order_item_id,
    oi.product_id,
    o.purchase_date,
    o.order_status,
    oi.price_brl,
    oi.freight_brl,

    -- Calculated Customer identifiers (SCD Type 2 lookup with fallback)
    COALESCE(c_historical.customer_key, 'pending_refresh') AS customer_key,
    COALESCE(c_historical.customer_unique_id, 'pending_refresh') AS customer_unique_id,
    COALESCE(c_historical.customer_state, 'pending_refresh') AS customer_state,

    -- Calculated Product & FX
    COALESCE(p.category_english, 'unknown') AS product_category,
    COALESCE(fx.brl_to_usd_rate, 0) AS brl_to_usd_rate,

    -- Calculated Revenue in USD
    ROUND(oi.price_brl * COALESCE(fx.brl_to_usd_rate, 0), 4) as price_usd,
    ROUND(oi.freight_brl * COALESCE(fx.brl_to_usd_rate, 0), 4) as freight_usd

FROM {{ ref('stg_orders') }} AS o

-- JOIN order items
INNER JOIN {{ ref('stg_order_items') }} AS oi
    ON o.order_id = oi.order_id

-- JOIN customer dimension (SCD Type 2: match on time range when order occurred)
LEFT JOIN {{ ref('stg_customers') }} AS sc
    ON o.customer_id = sc.customer_id

LEFT JOIN {{ ref('dim_customers') }} AS c_historical
    ON
        sc.customer_unique_id = c_historical.customer_unique_id
        AND o.order_purchase_timestamp >= c_historical.valid_from
        AND o.order_purchase_timestamp < c_historical.valid_to

-- JOIN product dimension
LEFT JOIN {{ ref('dim_products') }} AS p
    ON oi.product_id = p.product_id

-- JOIN exchange rate (forward-filled, no NULLs expected)
LEFT JOIN {{ ref('dim_exchange_rates') }} AS fx
    ON o.purchase_date = fx.date_day

{% if is_incremental() %}
    -- Idempotency & Late Arriving Updates logic: 
    -- We use a 30-day "lookback window" based on purchase_date.
    -- Why? Orders can have their status updated (e.g. 'shipped' -> 'delivered') weeks after the initial purchase.
    -- Since Olist dataset lacks an `updated_at` column, we rescan the last 30 days of orders. 
    -- The `merge` strategy on `unique_key` ensures we only update changed statuses without duplicating rows.
    WHERE o.purchase_date >= (SELECT MAX(t.purchase_date) - INTERVAL '30 days' FROM {{ this }} AS t)
{% endif %}
