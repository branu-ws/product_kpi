-- クロスプロダクト 統合マトリクス (横持ち, Notion 用)
-- 列: 過去完了月 = YYYY-MM, 今月の週 = YYYY-MM-W1 ...
-- アルファベット順で自然に並ぶ (2026-05 < 2026-06-W1)
WITH monthly AS (
    SELECT
        usage_month AS month,
        COUNT(CASE WHEN integration_tier = 'fan'        AND usage_freq = 'good'   THEN 1 END) AS ファン_good,
        COUNT(CASE WHEN integration_tier = 'fan'        AND usage_freq = 'normal' THEN 1 END) AS ファン_normal,
        COUNT(CASE WHEN integration_tier = 'fan'        AND usage_freq = 'bad'    THEN 1 END) AS ファン_bad,
        COUNT(CASE WHEN integration_tier = 'proactive'  AND usage_freq = 'good'   THEN 1 END) AS 自走_good,
        COUNT(CASE WHEN integration_tier = 'proactive'  AND usage_freq = 'normal' THEN 1 END) AS 自走_normal,
        COUNT(CASE WHEN integration_tier = 'proactive'  AND usage_freq = 'bad'    THEN 1 END) AS 自走_bad,
        COUNT(CASE WHEN integration_tier = 'onboarding' AND usage_freq = 'good'   THEN 1 END) AS オンボ中_good,
        COUNT(CASE WHEN integration_tier = 'onboarding' AND usage_freq = 'normal' THEN 1 END) AS オンボ中_normal,
        COUNT(CASE WHEN integration_tier = 'onboarding' AND usage_freq = 'bad'    THEN 1 END) AS オンボ中_bad,
        COUNT(CASE WHEN integration_tier = 'passive'    AND usage_freq = 'good'   THEN 1 END) AS 放置_good,
        COUNT(CASE WHEN integration_tier = 'passive'    AND usage_freq = 'normal' THEN 1 END) AS 放置_normal,
        COUNT(CASE WHEN integration_tier = 'passive'    AND usage_freq = 'bad'    THEN 1 END) AS 放置_bad
    FROM cross_product_monthly_company
    WHERE usage_month < STRFTIME(CURRENT_DATE, '%Y-%m')
    GROUP BY usage_month
),
active_weeks AS (
    SELECT DISTINCT week_start
    FROM cross_product_company_weekly
    WHERE week_start + INTERVAL '6 days' >= DATE_TRUNC('month', CURRENT_DATE)
      AND week_start < DATE_TRUNC('month', CURRENT_DATE) + INTERVAL '1 month'
),
week_labels AS (
    SELECT
        week_start,
        STRFTIME(CURRENT_DATE, '%Y-%m') || '-W' ||
            CAST(ROW_NUMBER() OVER (ORDER BY week_start) AS VARCHAR) AS month
    FROM active_weeks
),
weekly AS (
    SELECT
        wl.month,
        COUNT(CASE WHEN cm.integration_tier = 'fan'        AND cm.usage_freq = 'good'   THEN 1 END) AS ファン_good,
        COUNT(CASE WHEN cm.integration_tier = 'fan'        AND cm.usage_freq = 'normal' THEN 1 END) AS ファン_normal,
        COUNT(CASE WHEN cm.integration_tier = 'fan'        AND cm.usage_freq = 'bad'    THEN 1 END) AS ファン_bad,
        COUNT(CASE WHEN cm.integration_tier = 'proactive'  AND cm.usage_freq = 'good'   THEN 1 END) AS 自走_good,
        COUNT(CASE WHEN cm.integration_tier = 'proactive'  AND cm.usage_freq = 'normal' THEN 1 END) AS 自走_normal,
        COUNT(CASE WHEN cm.integration_tier = 'proactive'  AND cm.usage_freq = 'bad'    THEN 1 END) AS 自走_bad,
        COUNT(CASE WHEN cm.integration_tier = 'onboarding' AND cm.usage_freq = 'good'   THEN 1 END) AS オンボ中_good,
        COUNT(CASE WHEN cm.integration_tier = 'onboarding' AND cm.usage_freq = 'normal' THEN 1 END) AS オンボ中_normal,
        COUNT(CASE WHEN cm.integration_tier = 'onboarding' AND cm.usage_freq = 'bad'    THEN 1 END) AS オンボ中_bad,
        COUNT(CASE WHEN cm.integration_tier = 'passive'    AND cm.usage_freq = 'good'   THEN 1 END) AS 放置_good,
        COUNT(CASE WHEN cm.integration_tier = 'passive'    AND cm.usage_freq = 'normal' THEN 1 END) AS 放置_normal,
        COUNT(CASE WHEN cm.integration_tier = 'passive'    AND cm.usage_freq = 'bad'    THEN 1 END) AS 放置_bad
    FROM cross_product_company_weekly cm
    JOIN week_labels wl ON cm.week_start = wl.week_start
    GROUP BY wl.month
)
SELECT * FROM monthly
UNION ALL
SELECT * FROM weekly
ORDER BY month
