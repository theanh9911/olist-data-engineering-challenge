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
    extract(year from date_day)::integer as year,
    extract(month from date_day)::integer as month,
    extract(quarter from date_day)::integer as quarter,
    extract(day from date_day)::integer as day_of_month,
    extract(dow from date_day)::integer as day_of_week,  -- 0=Sunday
    to_char(date_day, 'YYYY-MM') as year_month,
    extract(dow from date_day) in (0, 6) as is_weekend
FROM date_spine
