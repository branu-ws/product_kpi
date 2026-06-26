-- 施工管理 (careecon work) 顧客ティア月次時系列 (縦持ち / tidy format)
-- customer_status: fan / proactive / passive / onboarding
SELECT
    CAST(usage_month || '-01' AS DATE) AS month,
    diversity_tier                      AS customer_status,
    COUNT(DISTINCT company_uuid)        AS num_company
FROM work_monthly_company
GROUP BY usage_month, diversity_tier
ORDER BY month, customer_status
