-- クロスプロダクト 機能連携度 × 利用頻度 月次時系列 (縦持ち)
-- customer_status: fan / proactive / passive / onboarding
-- usage:           good / normal / bad
-- value:           企業数
WITH work_scores AS (
    SELECT
        company_name AS company_key,
        usage_month,
        CASE MAX(CASE lifecycle_stage
            WHEN 'onboarding-plus' THEN 5
            WHEN 'plus'            THEN 4
            WHEN 'onboarding-mini' THEN 3
            WHEN 'mini'            THEN 2
            WHEN 'retired'         THEN 1
            ELSE 0
        END)
            WHEN 5 THEN 'onboarding-plus'
            WHEN 4 THEN 'plus'
            WHEN 3 THEN 'onboarding-mini'
            WHEN 2 THEN 'mini'
            ELSE        'retired'
        END AS lifecycle_stage,
        SUM(CASE health WHEN 'good' THEN 2 WHEN 'normal' THEN 1 ELSE 0 END) AS work_score
    FROM feature_health
    GROUP BY company_name, usage_month
),
keiei_scores AS (
    SELECT
        company_name AS company_key,
        usage_month,
        SUM(CASE health WHEN 'good' THEN 2 WHEN 'normal' THEN 1 ELSE 0 END) AS keiei_score
    FROM keiei_feature_health
    GROUP BY company_name, usage_month
),
combined AS (
    SELECT
        w.company_key,
        w.usage_month,
        w.lifecycle_stage,
        w.work_score,
        COALESCE(k.keiei_score, 0)                    AS keiei_score,
        w.work_score + COALESCE(k.keiei_score, 0)     AS total_score
    FROM work_scores AS w
    LEFT JOIN keiei_scores AS k
        ON  w.company_key = k.company_key
        AND w.usage_month = k.usage_month
),
rolling AS (
    SELECT
        *,
        COUNT(*) OVER (
            PARTITION BY company_key ORDER BY usage_month
            ROWS BETWEEN 1 PRECEDING AND CURRENT ROW
        ) AS window_size,
        MIN(CASE WHEN work_score >= 1 AND keiei_score >= 1 THEN 1 ELSE 0 END) OVER (
            PARTITION BY company_key ORDER BY usage_month
            ROWS BETWEEN 1 PRECEDING AND CURRENT ROW
        ) AS fan_all2,
        MIN(CASE WHEN work_score >= 1 OR keiei_score >= 1 THEN 1 ELSE 0 END) OVER (
            PARTITION BY company_key ORDER BY usage_month
            ROWS BETWEEN 1 PRECEDING AND CURRENT ROW
        ) AS jisou_all2
    FROM combined
),
classified AS (
    SELECT
        usage_month,
        CASE
            WHEN lifecycle_stage LIKE 'onboarding%'        THEN 'onboarding'
            WHEN window_size >= 2 AND fan_all2  = 1        THEN 'fan'
            WHEN window_size >= 2 AND jisou_all2 = 1       THEN 'proactive'
            ELSE                                                 'passive'
        END AS customer_status,
        CASE
            WHEN total_score >= 5 THEN 'good'
            WHEN total_score >= 3 THEN 'normal'
            ELSE                       'bad'
        END AS usage
    FROM rolling
)
SELECT
    usage_month,
    customer_status,
    usage,
    CASE usage WHEN 'good' THEN 2 WHEN 'normal' THEN 1 ELSE 0 END AS usage_value,
    COUNT(*) AS value
FROM classified
GROUP BY usage_month, customer_status, usage
ORDER BY usage_month, customer_status, usage
