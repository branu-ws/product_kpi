-- 施工管理 (Mini) 単一プロダクト マトリクス (横持ち, Notion 用)
-- 列: 過去完了月 = YYYY-MM, 今月の週 = YYYY-MM-W1 ...
-- mini_only: mini 契約あり かつ Plus 契約なし (Plus に寄せるため sf_customers から除外)
WITH mini_only AS (
    SELECT DISTINCT company_uuid FROM mini_customer_lifecycle
    EXCEPT
    SELECT company_uuid FROM sf_customers
),
monthly AS (
    SELECT
        usage_month AS month,
        COUNT(CASE WHEN diversity_tier = 'fan'        AND usage_freq = 'good'   THEN 1 END) AS ファン_good,
        COUNT(CASE WHEN diversity_tier = 'fan'        AND usage_freq = 'normal' THEN 1 END) AS ファン_normal,
        COUNT(CASE WHEN diversity_tier = 'fan'        AND usage_freq = 'bad'    THEN 1 END) AS ファン_bad,
        COUNT(CASE WHEN diversity_tier = 'proactive'  AND usage_freq = 'good'   THEN 1 END) AS 自走_good,
        COUNT(CASE WHEN diversity_tier = 'proactive'  AND usage_freq = 'normal' THEN 1 END) AS 自走_normal,
        COUNT(CASE WHEN diversity_tier = 'proactive'  AND usage_freq = 'bad'    THEN 1 END) AS 自走_bad,
        COUNT(CASE WHEN diversity_tier = 'onboarding' AND usage_freq = 'good'   THEN 1 END) AS オンボ中_good,
        COUNT(CASE WHEN diversity_tier = 'onboarding' AND usage_freq = 'normal' THEN 1 END) AS オンボ中_normal,
        COUNT(CASE WHEN diversity_tier = 'onboarding' AND usage_freq = 'bad'    THEN 1 END) AS オンボ中_bad,
        COUNT(CASE WHEN diversity_tier = 'passive'    AND usage_freq = 'good'   THEN 1 END) AS 放置_good,
        COUNT(CASE WHEN diversity_tier = 'passive'    AND usage_freq = 'normal' THEN 1 END) AS 放置_normal,
        COUNT(CASE WHEN diversity_tier = 'passive'    AND usage_freq = 'bad'    THEN 1 END) AS 放置_bad
    FROM mini_work_monthly_company
    WHERE company_uuid IN (SELECT company_uuid FROM mini_only)
      AND usage_month < STRFTIME(CURRENT_DATE, '%Y-%m')
    GROUP BY usage_month
),
active_weeks AS (
    SELECT DISTINCT week_start
    FROM mini_work_company_weekly
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
        COUNT(CASE WHEN cm.diversity_tier = 'fan'        AND cm.usage_freq = 'good'   THEN 1 END) AS ファン_good,
        COUNT(CASE WHEN cm.diversity_tier = 'fan'        AND cm.usage_freq = 'normal' THEN 1 END) AS ファン_normal,
        COUNT(CASE WHEN cm.diversity_tier = 'fan'        AND cm.usage_freq = 'bad'    THEN 1 END) AS ファン_bad,
        COUNT(CASE WHEN cm.diversity_tier = 'proactive'  AND cm.usage_freq = 'good'   THEN 1 END) AS 自走_good,
        COUNT(CASE WHEN cm.diversity_tier = 'proactive'  AND cm.usage_freq = 'normal' THEN 1 END) AS 自走_normal,
        COUNT(CASE WHEN cm.diversity_tier = 'proactive'  AND cm.usage_freq = 'bad'    THEN 1 END) AS 自走_bad,
        COUNT(CASE WHEN cm.diversity_tier = 'onboarding' AND cm.usage_freq = 'good'   THEN 1 END) AS オンボ中_good,
        COUNT(CASE WHEN cm.diversity_tier = 'onboarding' AND cm.usage_freq = 'normal' THEN 1 END) AS オンボ中_normal,
        COUNT(CASE WHEN cm.diversity_tier = 'onboarding' AND cm.usage_freq = 'bad'    THEN 1 END) AS オンボ中_bad,
        COUNT(CASE WHEN cm.diversity_tier = 'passive'    AND cm.usage_freq = 'good'   THEN 1 END) AS 放置_good,
        COUNT(CASE WHEN cm.diversity_tier = 'passive'    AND cm.usage_freq = 'normal' THEN 1 END) AS 放置_normal,
        COUNT(CASE WHEN cm.diversity_tier = 'passive'    AND cm.usage_freq = 'bad'    THEN 1 END) AS 放置_bad
    FROM mini_work_company_weekly cm
    JOIN week_labels wl ON cm.week_start = wl.week_start
    WHERE cm.company_uuid IN (SELECT company_uuid FROM mini_only)
    GROUP BY wl.month
)
SELECT * FROM monthly
UNION ALL
SELECT * FROM weekly
ORDER BY month
