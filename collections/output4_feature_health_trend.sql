-- アウトプット4: 企業 x 機能のヘルス推移 + 前月比フラグ
WITH health_order AS (
    SELECT 'good'   AS health, 1 AS ord UNION ALL
    SELECT 'normal',           2        UNION ALL
    SELECT 'bad',              3
),
trend AS (
    SELECT
        company_name,
        company_uuid,
        feature,
        usage_month,
        health,
        usage_count,
        LAG(health) OVER (
            PARTITION BY company_uuid, feature ORDER BY usage_month
        ) AS prev_health
    FROM feature_health
)
SELECT
    t.company_name,
    t.feature,
    t.usage_month,
    t.health,
    t.usage_count,
    t.prev_health,
    CASE
        WHEN t.prev_health IS NULL THEN '-'
        WHEN cur.ord > prv.ord     THEN '↓'
        WHEN cur.ord < prv.ord     THEN '↑'
        ELSE                            '→'
    END AS trend
FROM trend AS t
LEFT JOIN health_order AS cur ON t.health      = cur.health
LEFT JOIN health_order AS prv ON t.prev_health = prv.health
ORDER BY t.company_name, t.feature, t.usage_month
