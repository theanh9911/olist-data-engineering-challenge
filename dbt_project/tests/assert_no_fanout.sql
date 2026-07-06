-- assert_no_fanout.sql
-- Data Quality Test: Verify fact_order_items has NOT been inflated by bad JOINs
-- The row count of fact_order_items should exactly equal the row count of raw.order_items
-- (after filtering out NULLs)
--
-- Test PASSES when query returns 0 rows (counts match)

WITH fact_count AS (
    SELECT COUNT(*) AS cnt
    FROM {{ ref('fact_order_items') }}
),

raw_count AS (
    SELECT COUNT(*) AS cnt
    FROM {{ source('raw', 'order_items') }}
    WHERE order_id IS NOT NULL
)

SELECT
    f.cnt AS fact_rows,
    r.cnt AS raw_rows,
    f.cnt - r.cnt AS diff
FROM fact_count f
CROSS JOIN raw_count r
WHERE f.cnt != r.cnt
