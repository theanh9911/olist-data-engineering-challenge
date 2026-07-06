-- stg_exchange_rates.sql
-- Staging model for Frankfurter API exchange rates
-- Design Doc Section 2.5: API stores dates in UTC

SELECT
    date_day::DATE                     AS date_day,
    from_currency,
    to_currency,
    rate::DECIMAL(18, 8)               AS brl_to_usd_rate
FROM {{ source('raw', 'exchange_rates') }}
WHERE rate IS NOT NULL
