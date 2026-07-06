-- fact_order_payments.sql
-- Fact table: 1 row = 1 payment method per order
-- Design Doc Section 5.2: Grain is order_id + payment_sequential
-- INDEPENDENT from fact_order_items — never JOIN at detail grain!

{{
    config(
        materialized='incremental',
        unique_key='order_payment_key',
        incremental_strategy='merge'
    )
}}
SELECT
    -- Keys
    op.order_payment_key,
    o.order_id,
    op.payment_sequential,

    -- Customer identifiers (SCD Type 2 lookup with fallback for late-arriving dims)
    COALESCE(c_historical.customer_key, 'pending_refresh') AS customer_key,
    COALESCE(c_historical.customer_unique_id, 'pending_refresh') AS customer_unique_id,

    -- Date
    o.purchase_date,

    -- Order metadata
    o.order_status,

    -- Payment details
    op.payment_type,
    op.payment_installments,

    -- Payment value in BRL
    op.payment_value_brl,

    -- Exchange rate
    COALESCE(fx.brl_to_usd_rate, 0) AS brl_to_usd_rate,

    -- Payment value in USD
    ROUND(op.payment_value_brl * COALESCE(fx.brl_to_usd_rate, 0), 4) AS payment_value_usd

FROM {{ ref('stg_orders') }} o

INNER JOIN {{ ref('stg_order_payments') }} op
    ON o.order_id = op.order_id

-- JOIN customer dimension (SCD Type 2: match on time range when order occurred)
LEFT JOIN {{ ref('stg_customers') }} sc
    ON o.customer_id = sc.customer_id

LEFT JOIN {{ ref('dim_customers') }} c_historical
    ON sc.customer_unique_id = c_historical.customer_unique_id
    AND o.order_purchase_timestamp >= c_historical.valid_from
    AND o.order_purchase_timestamp < c_historical.valid_to

-- JOIN exchange rate (forward-filled)
LEFT JOIN {{ ref('dim_exchange_rates') }} fx
    ON o.purchase_date = fx.date_day

{% if is_incremental() %}
    -- Idempotency & Late Arriving Updates logic: 
    -- We use a 30-day "lookback window" based on purchase_date to catch late updates.
    -- The `merge` strategy on `unique_key` ensures safe upserts without duplication.
    WHERE o.purchase_date >= (SELECT MAX(purchase_date) - INTERVAL '30 days' FROM {{ this }})
{% endif %}

