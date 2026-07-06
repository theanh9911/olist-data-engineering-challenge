-- stg_products.sql
-- Staging model for products with category translation
-- Design Doc Section 2.4: LEFT JOIN + COALESCE to handle missing translations

SELECT
    p.product_id,
    COALESCE(t.product_category_name_english, p.product_category_name, 'unknown') AS category_english,
    p.product_category_name AS category_portuguese,
    p.product_name_lenght::DECIMAL::INTEGER      AS product_name_length,
    p.product_description_lenght::DECIMAL::INTEGER AS product_description_length,
    p.product_photos_qty::DECIMAL::INTEGER       AS product_photos_qty,
    p.product_weight_g::DECIMAL(10, 2)  AS product_weight_g,
    p.product_length_cm::DECIMAL(10, 2) AS product_length_cm,
    p.product_height_cm::DECIMAL(10, 2) AS product_height_cm,
    p.product_width_cm::DECIMAL(10, 2)  AS product_width_cm
FROM {{ source('raw', 'products') }} p
LEFT JOIN {{ source('raw', 'category_translation') }} t
    ON p.product_category_name = t.product_category_name
WHERE p.product_id IS NOT NULL
