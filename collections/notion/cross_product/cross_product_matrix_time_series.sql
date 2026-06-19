-- クロスプロダクト 月別マトリクス (横持ち, Notion 用)
-- 行 = 指標 (ファン_good 等), 列 = 月 (YYYY-MM)
-- cross_product_monthly_company から集計
SELECT
    usage_month AS month,
    COUNT(CASE WHEN integration_tier = 'fan'       AND usage_freq = 'good'   THEN 1 END) AS ファン_good,
    COUNT(CASE WHEN integration_tier = 'fan'       AND usage_freq = 'normal' THEN 1 END) AS ファン_normal,
    COUNT(CASE WHEN integration_tier = 'fan'       AND usage_freq = 'bad'    THEN 1 END) AS ファン_bad,
    COUNT(CASE WHEN integration_tier = 'proactive' AND usage_freq = 'good'   THEN 1 END) AS 自走_good,
    COUNT(CASE WHEN integration_tier = 'proactive' AND usage_freq = 'normal' THEN 1 END) AS 自走_normal,
    COUNT(CASE WHEN integration_tier = 'proactive' AND usage_freq = 'bad'    THEN 1 END) AS 自走_bad,
    COUNT(CASE WHEN integration_tier = 'onboarding' AND usage_freq = 'good'  THEN 1 END) AS オンボ中_good,
    COUNT(CASE WHEN integration_tier = 'onboarding' AND usage_freq = 'normal' THEN 1 END) AS オンボ中_normal,
    COUNT(CASE WHEN integration_tier = 'onboarding' AND usage_freq = 'bad'   THEN 1 END) AS オンボ中_bad,
    COUNT(CASE WHEN integration_tier = 'passive'   AND usage_freq = 'good'   THEN 1 END) AS 放置_good,
    COUNT(CASE WHEN integration_tier = 'passive'   AND usage_freq = 'normal' THEN 1 END) AS 放置_normal,
    COUNT(CASE WHEN integration_tier = 'passive'   AND usage_freq = 'bad'    THEN 1 END) AS 放置_bad
FROM cross_product_monthly_company
WHERE usage_month < STRFTIME(CURRENT_DATE, '%Y-%m')
GROUP BY usage_month
ORDER BY usage_month
