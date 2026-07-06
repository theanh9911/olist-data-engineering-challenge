-- reconcile_revenue.sql
-- Data Quality Test: Đối soát chéo Revenue giữa 2 bảng Fact
-- Design Doc Section 8.1: SUM(price + freight) ≈ SUM(payment_value) per order
-- Cho phép chênh lệch tối đa 1.00 BRL (do lỗi làm tròn)
--
-- Test PASSES khi query trả về 0 rows (không có đơn nào chênh lệch quá 1 BRL)
-- Đặt severity = 'warn' vì dữ liệu gốc Kaggle chứa sẵn ~249 đơn hàng (0.25%) lệch kế toán/voucher.

{{ config(severity = 'warn') }}

WITH items_total AS (
    SELECT
        order_id,
        SUM(price_brl + freight_brl) AS total_items_brl
    FROM {{ ref('fact_order_items') }}
    GROUP BY order_id
),

payments_total AS (
    SELECT
        order_id,
        SUM(payment_value_brl) AS total_payments_brl
    FROM {{ ref('fact_order_payments') }}
    GROUP BY order_id
)

SELECT
    i.order_id,
    i.total_items_brl,
    p.total_payments_brl,
    ABS(i.total_items_brl - p.total_payments_brl) AS diff_brl
FROM items_total i
INNER JOIN payments_total p ON i.order_id = p.order_id
WHERE ABS(i.total_items_brl - p.total_payments_brl) > 1.00
