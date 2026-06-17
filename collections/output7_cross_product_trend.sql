-- アウトプット7: 企業別 クロスプロダクト 機能連携度推移 + 前月比フラグ
-- 機能連携度: 直近2ヶ月連続の継続状況で判定
-- ★ グルーピングキー: 現在は社名でグルーピング
--   UUID切り替え時: work_scores/keiei_scores の
--     company_name AS company_key → company_uuid AS company_key
--     GROUP BY company_name → GROUP BY company_uuid, company_name
--     PARTITION BY company_key → PARTITION BY company_key (変更不要)
WITH tier_order AS (
    SELECT 'ファン'   AS tier, 1 AS ord UNION ALL
    SELECT '自走',             2        UNION ALL
    SELECT 'オンボ中',         3        UNION ALL
    SELECT '離反気味',         4
),
work_scores AS (
    SELECT
        company_name                  AS company_key,  -- UUID切替: company_uuid AS company_key
        company_name,
        usage_month,
        -- 同名複数UUIDがある場合はより活性なライフサイクルを優先
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
        w.company_name,
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
        company_key,
        company_name,
        usage_month,
        work_score,
        keiei_score,
        total_score,
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
),
trend AS (
    SELECT
        *,
        LAG(integration_tier) OVER (PARTITION BY company_key ORDER BY usage_month) AS prev_tier,
        LAG(usage_freq)        OVER (PARTITION BY company_key ORDER BY usage_month) AS prev_freq
    FROM classified
)
SELECT
    t.company_name         AS 会社名,
    t.usage_month          AS 月,
    t.work_score           AS 施工スコア,
    t.keiei_score          AS 経営スコア,
    t.total_score          AS 合計スコア,
    t.integration_tier     AS 機能連携度,
    t.usage_freq           AS 利用頻度,
    t.prev_tier            AS 前月連携度,
    CASE
        WHEN t.prev_tier IS NULL   THEN '-'
        WHEN cur.ord < prv.ord     THEN '↑'
        WHEN cur.ord > prv.ord     THEN '↓'
        ELSE                            '→'
    END AS 連携度トレンド
FROM trend AS t
LEFT JOIN tier_order AS cur ON t.integration_tier = cur.tier
LEFT JOIN tier_order AS prv ON t.prev_tier        = prv.tier
ORDER BY t.company_name, t.usage_month
