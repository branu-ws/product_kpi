-- 経営管理 アウトプット1: 月別 顧客ロイヤリティ階層分布 (横ピボット)
PIVOT (
    SELECT
        usage_month,
        loyalty_tier,
        COUNT(DISTINCT company_name) AS company_count
    FROM keiei_company_loyalty
    GROUP BY usage_month, loyalty_tier
)
ON loyalty_tier IN ('神', 'ファン', '自走', '2か月連続活用', '断続的活用', 'まずい', '離反状態')
USING SUM(company_count)
GROUP BY usage_month
ORDER BY usage_month
