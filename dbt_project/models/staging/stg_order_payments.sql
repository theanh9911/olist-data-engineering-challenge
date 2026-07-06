-- stg_order_payments.sql
-- Staging model for order payments: cast payment_value to DECIMAL
-- Design Doc Section 2.2: This table is kept SEPARATE from order_items to avoid Fan-out

SELECT
    order_id,
    payment_sequential::INTEGER               AS payment_sequential,
    payment_type,
    payment_installments::INTEGER             AS payment_installments,
    payment_value::DECIMAL(18, 4)             AS payment_value_brl,
    -- Composite primary key
    order_id || '-' || payment_sequential      AS order_payment_key
FROM {{ source('raw', 'order_payments') }}
WHERE order_id IS NOT NULL
