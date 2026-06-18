-- アウトプット6: クロスプロダクト 機能連携度 × 利用頻度 (月別ピボット)
-- 機能連携度: 直近2ヶ月連続の継続状況で判定
-- 利用頻度スコア: good=2, normal=1, bad=0 の合計 / good≥5, normal≥3, bad<3
-- ★ グルーピングキー: 現在は社名でグルーピング（output7 と同じ切り替えルール）
WITH work_scores AS (
    SELECT
        company_name                  AS company_key,  -- UUID切替: company_uuid AS company_key
        company_name,
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
    GROUP BY company_name, usage_month          -- UUID切替: GROUP BY company_uuid, company_name, usage_month
),
keiei_scores AS (
    SELECT
        company_name                  AS company_key,  -- UUID切替: company_uuid AS company_key
        usage_month,
        SUM(CASE health WHEN 'good' THEN 2 WHEN 'normal' THEN 1 ELSE 0 END) AS keiei_score
    FROM keiei_feature_health
    GROUP BY company_name, usage_month          -- UUID切替: GROUP BY company_uuid, usage_month
),
combined AS (
    SELECT
        w.company_key,
        w.usage_month,
        w.lifecycle_stage,
        w.work_score,
        COALESCE(k.keiei_score, 0)                     AS keiei_score,
        w.work_score + COALESCE(k.keiei_score, 0)      AS total_score
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
        -- 直近2ヶ月すべてで 施工≥1 AND 経営≥1 → ファン
        MIN(CASE WHEN work_score >= 1 AND keiei_score >= 1 THEN 1 ELSE 0 END) OVER (
            PARTITION BY company_key ORDER BY usage_month
            ROWS BETWEEN 1 PRECEDING AND CURRENT ROW
        ) AS fan_all2,
        -- 直近2ヶ月すべてで 施工≥1 OR 経営≥1 → 自走
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
            WHEN lifecycle_stage LIKE 'onboarding%'          THEN 'オンボ中'
            WHEN window_size >= 2 AND fan_all2  = 1          THEN 'ファン'
            WHEN window_size >= 2 AND jisou_all2 = 1         THEN '自走'
            ELSE                                                   '離反気味'
        END AS integration_tier,
        CASE
            WHEN total_score >= 5 THEN 'good'
            WHEN total_score >= 3 THEN 'normal'
            ELSE                       'bad'
        END AS usage_freq
    FROM rolling
)
SELECT
    usage_month,
    COUNT(CASE WHEN integration_tier = 'ファン'   AND usage_freq = 'good'   THEN 1 END) AS fan_good,
    COUNT(CASE WHEN integration_tier = 'ファン'   AND usage_freq = 'normal' THEN 1 END) AS fan_normal,
    COUNT(CASE WHEN integration_tier = 'ファン'   AND usage_freq = 'bad'    THEN 1 END) AS fan_bad,
    COUNT(CASE WHEN integration_tier = '自走'     AND usage_freq = 'good'   THEN 1 END) AS jisou_good,
    COUNT(CASE WHEN integration_tier = '自走'     AND usage_freq = 'normal' THEN 1 END) AS jisou_normal,
    COUNT(CASE WHEN integration_tier = '自走'     AND usage_freq = 'bad'    THEN 1 END) AS jisou_bad,
    COUNT(CASE WHEN integration_tier = 'オンボ中' AND usage_freq = 'good'   THEN 1 END) AS onboarding_good,
    COUNT(CASE WHEN integration_tier = 'オンボ中' AND usage_freq = 'normal' THEN 1 END) AS onboarding_normal,
    COUNT(CASE WHEN integration_tier = 'オンボ中' AND usage_freq = 'bad'    THEN 1 END) AS onboarding_bad,
    COUNT(CASE WHEN integration_tier = '離反気味' AND usage_freq = 'good'   THEN 1 END) AS churn_risk_good,
    COUNT(CASE WHEN integration_tier = '離反気味' AND usage_freq = 'normal' THEN 1 END) AS churn_risk_normal,
    COUNT(CASE WHEN integration_tier = '離反気味' AND usage_freq = 'bad'    THEN 1 END) AS churn_risk_bad
FROM classified
GROUP BY usage_month
ORDER BY usage_month
