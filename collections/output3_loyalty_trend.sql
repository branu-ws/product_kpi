-- アウトプット3: 企業別ロイヤリティ推移 + 前月比フラグ
WITH tier_order AS (
    SELECT '神'         AS tier, 1 AS ord UNION ALL
    SELECT 'ファン',              2       UNION ALL
    SELECT '自走',                3       UNION ALL
    SELECT '2か月連続活用',       4       UNION ALL
    SELECT '断続的活用',          5       UNION ALL
    SELECT 'まずい',              6       UNION ALL
    SELECT '離反状態',            7
),
trend AS (
    SELECT
        company_name,
        company_uuid,
        usage_month,
        loyalty_tier,
        LAG(loyalty_tier) OVER (
            PARTITION BY company_uuid ORDER BY usage_month
        ) AS prev_tier
    FROM company_loyalty
)
SELECT
    t.company_name,
    t.usage_month,
    t.loyalty_tier,
    t.prev_tier,
    CASE
        WHEN t.prev_tier IS NULL THEN '-'
        WHEN cur.ord > prv.ord   THEN '↓'
        WHEN cur.ord < prv.ord   THEN '↑'
        ELSE                          '→'
    END AS trend
FROM trend AS t
LEFT JOIN tier_order AS cur ON t.loyalty_tier = cur.tier
LEFT JOIN tier_order AS prv ON t.prev_tier    = prv.tier
ORDER BY t.company_name, t.usage_month
