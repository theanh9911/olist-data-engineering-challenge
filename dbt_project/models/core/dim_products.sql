-- dim_products.sql
-- Dimension: Product catalog with English category names
-- Design Doc Section 5.3

SELECT
    product_id,
    category_english,
    category_portuguese,
    product_name_length,
    product_description_length,
    product_photos_qty,
    product_weight_g,
    product_length_cm,
    product_height_cm,
    product_width_cm
FROM {{ ref('stg_products') }}
