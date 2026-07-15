-- stg_order_items.sql
-- Staging model for order items: cast price/freight to DECIMAL
-- Design Doc Section 5.2: freight_brl is PER ITEM, not per order

SELECT
    order_id,
    order_item_id::INTEGER as order_item_id,
    product_id,
    seller_id,
    shipping_limit_date::TIMESTAMP as shipping_limit_date,
    price::DECIMAL(18, 4) as price_brl,
    freight_value::DECIMAL(18, 4) as freight_brl,
    -- Composite primary key: order_id + order_item_id
    order_id || '-' || order_item_id as order_item_key
FROM {{ source('raw', 'order_items') }}
WHERE order_id IS NOT NULL
