-- クロスプロダクト 今月週次マトリクス (横持ち, Notion 用)
-- 週の所属は week_end (week_start + 6日) の月で決定するため、
-- 月をまたぐ第1週 (例: 5/26〜6/1) も「6月の週」として取り込む。
-- tier は前月末の3ヶ月計算値 (cross_product_monthly_company の usage_month = 前月) を使用。
WITH active_weeks AS (
    SELECT DISTINCT week_start
    FROM cross_product_company_weekly
    WHERE week_start + INTERVAL '6 days' >= DATE_TRUNC('month', CURRENT_DATE)
      AND week_start < DATE_TRUNC('month', CURRENT_DATE) + INTERVAL '1 month'
),
week_labels AS (
    SELECT
        week_start,
        STRFTIME(CURRENT_DATE, '%m') || '-W' ||
            CAST(ROW_NUMBER() OVER (ORDER BY week_start) AS VARCHAR) AS week_label
    FROM active_weeks
)
SELECT
    wl.week_label AS month,
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
GROUP BY wl.week_label
ORDER BY wl.week_label
