-- stg_order_items.sql
-- Staging model for order items: cast price/freight to DECIMAL
-- Design Doc Section 5.2: freight_brl is PER ITEM, not per order

SELECT
    order_id,
    order_item_id::INTEGER                    AS order_item_id,
    product_id,
    seller_id,
    shipping_limit_date::TIMESTAMP            AS shipping_limit_date,
    price::DECIMAL(18, 4)                     AS price_brl,
    freight_value::DECIMAL(18, 4)             AS freight_brl,
    -- Composite primary key: order_id + order_item_id
    order_id || '-' || order_item_id          AS order_item_key
FROM {{ source('raw', 'order_items') }}
WHERE order_id IS NOT NULL
