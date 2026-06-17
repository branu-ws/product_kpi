-- アウトプット5: 企業 x 月 全機能ヘルス一覧 (施工管理 + 経営管理)
-- health: good=3, normal=2, bad=1
WITH health_val AS (
    SELECT
        company_uuid, company_name, usage_month, plan_type, lifecycle_stage,
        MAX(CASE WHEN feature = '工程作成'    THEN CASE health WHEN 'good' THEN 3 WHEN 'normal' THEN 2 ELSE 1 END END) AS 施工_工程作成,
        MAX(CASE WHEN feature = '出面'        THEN CASE health WHEN 'good' THEN 3 WHEN 'normal' THEN 2 ELSE 1 END END) AS 施工_出面,
        MAX(CASE WHEN feature = '出来高'      THEN CASE health WHEN 'good' THEN 3 WHEN 'normal' THEN 2 ELSE 1 END END) AS 施工_出来高,
        MAX(CASE WHEN feature = 'ホワイトボード' THEN CASE health WHEN 'good' THEN 3 WHEN 'normal' THEN 2 ELSE 1 END END) AS 施工_ホワイトボード,
        MAX(CASE WHEN feature = '日報'        THEN CASE health WHEN 'good' THEN 3 WHEN 'normal' THEN 2 ELSE 1 END END) AS 施工_日報,
        MAX(CASE WHEN feature = '報告書'      THEN CASE health WHEN 'good' THEN 3 WHEN 'normal' THEN 2 ELSE 1 END END) AS 施工_報告書
    FROM feature_health
    GROUP BY company_uuid, company_name, usage_month, plan_type, lifecycle_stage
),
keiei_val AS (
    SELECT
        company_uuid, usage_month,
        MAX(CASE WHEN feature = '案件ステータス更新' THEN CASE health WHEN 'good' THEN 3 WHEN 'normal' THEN 2 ELSE 1 END END) AS 経営_案件ステータス更新,
        MAX(CASE WHEN feature = '見積原価登録'       THEN CASE health WHEN 'good' THEN 3 WHEN 'normal' THEN 2 ELSE 1 END END) AS 経営_見積原価登録,
        MAX(CASE WHEN feature = '見積売上登録'       THEN CASE health WHEN 'good' THEN 3 WHEN 'normal' THEN 2 ELSE 1 END END) AS 経営_見積売上登録,
        MAX(CASE WHEN feature = '実績原価登録'       THEN CASE health WHEN 'good' THEN 3 WHEN 'normal' THEN 2 ELSE 1 END END) AS 経営_実績原価登録,
        MAX(CASE WHEN feature = '実績売上登録'       THEN CASE health WHEN 'good' THEN 3 WHEN 'normal' THEN 2 ELSE 1 END END) AS 経営_実績売上登録,
        MAX(CASE WHEN feature = '請求書発行'         THEN CASE health WHEN 'good' THEN 3 WHEN 'normal' THEN 2 ELSE 1 END END) AS 経営_請求書発行,
        MAX(CASE WHEN feature = 'OCR処理'           THEN CASE health WHEN 'good' THEN 3 WHEN 'normal' THEN 2 ELSE 1 END END) AS 経営_OCR処理,
        MAX(CASE WHEN feature = '原価ページPV'       THEN CASE health WHEN 'good' THEN 3 WHEN 'normal' THEN 2 ELSE 1 END END) AS 経営_原価ページPV
    FROM keiei_feature_health
    GROUP BY company_uuid, usage_month
)
SELECT
    w.company_name        AS 会社名,
    w.usage_month         AS 月,
    w.plan_type           AS プラン,
    w.lifecycle_stage     AS ライフサイクル,
    w.施工_工程作成,
    w.施工_出面,
    w.施工_出来高,
    w.施工_ホワイトボード,
    w.施工_日報,
    w.施工_報告書,
    k.経営_案件ステータス更新,
    k.経営_見積原価登録,
    k.経営_見積売上登録,
    k.経営_実績原価登録,
    k.経営_実績売上登録,
    k.経営_請求書発行,
    k.経営_OCR処理,
    k.経営_原価ページPV
FROM health_val AS w
LEFT JOIN keiei_val AS k
    ON  w.company_uuid = k.company_uuid
    AND w.usage_month  = k.usage_month
ORDER BY w.company_name, w.usage_month
