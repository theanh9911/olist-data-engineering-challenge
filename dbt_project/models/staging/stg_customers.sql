-- stg_customers.sql
-- Staging model for customers
-- Design Doc Section 2.1: customer_unique_id is the TRUE customer identity
-- Design Doc Section 2.1: customer_state is used for Region (city has typos)

SELECT
    customer_id,
    customer_unique_id,
    customer_zip_code_prefix,
    customer_city,
    customer_state
FROM {{ source('raw', 'customers') }}
WHERE customer_id IS NOT NULL
