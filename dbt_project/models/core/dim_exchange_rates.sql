-- dim_exchange_rates.sql
-- Dimension: BRL→USD exchange rates with Forward-fill (LOCF) for weekends/holidays
-- Design Doc Section 3.2 & Assumption A4:
--   Frankfurter API doesn't publish rates on weekends/holidays.
--   Strategy: Use last known rate (Friday's rate for Saturday/Sunday).

WITH date_spine AS (
    SELECT date_day
    FROM {{ ref('dim_date') }}
),

raw_rates AS (
    SELECT
        date_day,
        brl_to_usd_rate
    FROM {{ ref('stg_exchange_rates') }}
),

-- LEFT JOIN date spine with raw rates → NULLs on weekends/holidays
joined AS (
    SELECT
        ds.date_day,
        rr.brl_to_usd_rate AS raw_rate
    FROM date_spine AS ds
    LEFT JOIN raw_rates AS rr ON ds.date_day = rr.date_day
),

-- Forward-fill: carry last non-NULL rate forward
-- Uses a "group" trick: assign each NULL row to the last non-NULL row's group
forward_filled AS (
    SELECT
        date_day,
        raw_rate,
        -- Create groups: each non-NULL rate starts a new group
        COUNT(raw_rate) OVER (ORDER BY date_day ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS rate_group
    FROM joined
)

SELECT
    date_day,
    -- Within each group, pick the first (and only) non-NULL value.
    -- If it's NULL (dates before the first rate of the year, e.g. Jan 1-3, 2016),
    -- fall back to the very first available rate of the year.
    COALESCE(
        FIRST_VALUE(raw_rate) OVER (
            PARTITION BY rate_group
            ORDER BY date_day
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ),
        (
            SELECT er.brl_to_usd_rate
            FROM {{ ref('stg_exchange_rates') }} AS er
            ORDER BY er.date_day ASC
            LIMIT 1
        )
    ) AS brl_to_usd_rate,
    raw_rate IS NULL AS is_forward_filled
FROM forward_filled
