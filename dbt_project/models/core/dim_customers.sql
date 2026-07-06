-- dim_customers.sql
-- Dimension: Customer with SCD Type 2 for geographical tracking
-- Design Doc Section 2.1: Uses dbt snapshot for history tracking
-- Reads from the snapshot table created by snap_customers.sql

WITH snapshot_data AS (
    SELECT
        customer_unique_id,
        customer_state,
        customer_city,
        customer_zip_code_prefix,
        dbt_valid_from,
        dbt_valid_to,
        -- Đánh số thứ tự các phiên bản của cùng 1 khách hàng
        ROW_NUMBER() OVER (
            PARTITION BY customer_unique_id
            ORDER BY dbt_valid_from ASC
        ) AS version_rn
    FROM {{ ref('snap_customers') }}
)

SELECT
    -- Surrogate key for SCD Type 2 joins
    {{ dbt_utils.generate_surrogate_key(['customer_unique_id', 'dbt_valid_from']) }} AS customer_key,
    customer_unique_id,
    customer_state,
    customer_city,
    customer_zip_code_prefix,
    -- Nếu là phiên bản đầu tiên, set valid_from về quá khứ xa (1970-01-01) để khớp dữ liệu lịch sử
    CASE
        WHEN version_rn = 1 THEN '1970-01-01'::TIMESTAMP
        ELSE dbt_valid_from
    END AS valid_from,
    COALESCE(dbt_valid_to, '9999-12-31'::TIMESTAMP) AS valid_to,
    CASE
        WHEN dbt_valid_to IS NULL THEN TRUE
        ELSE FALSE
    END AS is_current
FROM snapshot_data
