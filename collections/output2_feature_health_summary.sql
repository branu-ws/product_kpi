-- アウトプット2: 月別 機能別ヘルス分布 (横ピボット: feature x health)
PIVOT (
    SELECT
        usage_month,
        feature,
        health,
        COUNT(*) AS company_count
    FROM feature_health
    GROUP BY usage_month, feature, health
)
ON health IN ('good', 'normal', 'bad')
USING SUM(company_count)
GROUP BY usage_month, feature
ORDER BY usage_month, feature
