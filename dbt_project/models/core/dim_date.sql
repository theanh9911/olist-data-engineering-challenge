-- dim_date.sql
-- Dimension: Date spine from 2016-01-01 to 2018-12-31
-- Used for time-series analysis, MTD calculations, and FX rate joins

WITH date_spine AS (
    SELECT
        generate_series(
            '2016-01-01'::DATE,
            '2018-12-31'::DATE,
            '1 day'::INTERVAL
        )::DATE AS date_day
)

SELECT
    date_day,
    EXTRACT(YEAR FROM date_day)::INTEGER     AS year,
    EXTRACT(MONTH FROM date_day)::INTEGER    AS month,
    EXTRACT(QUARTER FROM date_day)::INTEGER  AS quarter,
    EXTRACT(DAY FROM date_day)::INTEGER      AS day_of_month,
    EXTRACT(DOW FROM date_day)::INTEGER      AS day_of_week,  -- 0=Sunday
    TO_CHAR(date_day, 'YYYY-MM')             AS year_month,
    CASE
        WHEN EXTRACT(DOW FROM date_day) IN (0, 6) THEN TRUE
        ELSE FALSE
    END AS is_weekend
FROM date_spine
