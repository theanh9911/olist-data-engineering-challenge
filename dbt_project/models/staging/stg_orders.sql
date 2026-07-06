-- stg_orders.sql
-- Staging model for orders: cast timestamps, extract purchase_date
-- No business logic — only cleaning and type casting

SELECT
    order_id,
    customer_id,
    order_status,
    order_purchase_timestamp::TIMESTAMP       AS order_purchase_timestamp,
    order_approved_at::TIMESTAMP              AS order_approved_at,
    order_delivered_carrier_date::TIMESTAMP    AS order_delivered_carrier_date,
    order_delivered_customer_date::TIMESTAMP   AS order_delivered_customer_date,
    order_estimated_delivery_date::TIMESTAMP   AS order_estimated_delivery_date,
    -- Extract DATE for joining with dim_date and dim_exchange_rates
    -- Convert source timezone (America/Sao_Paulo) to UTC before extracting date
    ((order_purchase_timestamp::TIMESTAMP AT TIME ZONE 'America/Sao_Paulo') AT TIME ZONE 'UTC')::DATE AS purchase_date
FROM {{ source('raw', 'orders') }}
WHERE order_id IS NOT NULL
