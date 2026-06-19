-- 経営管理 (careecon keiei) 顧客ロイヤリティ月次時系列 (縦持ち / tidy format)
-- customer_status: god / fan / proactive / two_month / occasional / inactive / abandoned
SELECT
    CAST(month || '-01' AS DATE) AS month,
    CASE loyalty_tier
        WHEN '神'           THEN 'god'
        WHEN 'ファン'        THEN 'fan'
        WHEN '自走'          THEN 'proactive'
        WHEN '2か月連続活用' THEN 'two_month'
        WHEN '断続的活用'    THEN 'occasional'
        WHEN 'まずい'        THEN 'inactive'
        WHEN '離反状態'      THEN 'abandoned'
    END AS customer_status,
    COUNT(DISTINCT company_uuid) AS num_company
FROM keiei_company_loyalty
WHERE loyalty_tier IS NOT NULL
GROUP BY month, loyalty_tier
ORDER BY month, customer_status
