-- アウトプット5: 企業 x 月 全機能ヘルス一覧 (施工管理 + 経営管理)
-- health: good=3, normal=2, bad=1
WITH health_val AS (
    SELECT
        company_uuid, company_name, usage_month, plan_type, lifecycle_stage,
        MAX(CASE WHEN feature = '工程作成'    THEN CASE health WHEN 'good' THEN 3 WHEN 'normal' THEN 2 ELSE 1 END END) AS work_process,
        MAX(CASE WHEN feature = '出面'        THEN CASE health WHEN 'good' THEN 3 WHEN 'normal' THEN 2 ELSE 1 END END) AS work_attendance,
        MAX(CASE WHEN feature = '出来高'      THEN CASE health WHEN 'good' THEN 3 WHEN 'normal' THEN 2 ELSE 1 END END) AS work_progress,
        MAX(CASE WHEN feature = 'ホワイトボード' THEN CASE health WHEN 'good' THEN 3 WHEN 'normal' THEN 2 ELSE 1 END END) AS work_whiteboard,
        MAX(CASE WHEN feature = '日報'        THEN CASE health WHEN 'good' THEN 3 WHEN 'normal' THEN 2 ELSE 1 END END) AS work_diary,
        MAX(CASE WHEN feature = '報告書'      THEN CASE health WHEN 'good' THEN 3 WHEN 'normal' THEN 2 ELSE 1 END END) AS work_report
    FROM feature_health
    GROUP BY company_uuid, company_name, usage_month, plan_type, lifecycle_stage
),
keiei_val AS (
    SELECT
        company_uuid, usage_month,
        MAX(CASE WHEN feature = '案件ステータス更新' THEN CASE health WHEN 'good' THEN 3 WHEN 'normal' THEN 2 ELSE 1 END END) AS mgmt_project_status,
        MAX(CASE WHEN feature = '見積原価登録'       THEN CASE health WHEN 'good' THEN 3 WHEN 'normal' THEN 2 ELSE 1 END END) AS mgmt_est_cost,
        MAX(CASE WHEN feature = '見積売上登録'       THEN CASE health WHEN 'good' THEN 3 WHEN 'normal' THEN 2 ELSE 1 END END) AS mgmt_est_revenue,
        MAX(CASE WHEN feature = '実績原価登録'       THEN CASE health WHEN 'good' THEN 3 WHEN 'normal' THEN 2 ELSE 1 END END) AS mgmt_actual_cost,
        MAX(CASE WHEN feature = '実績売上登録'       THEN CASE health WHEN 'good' THEN 3 WHEN 'normal' THEN 2 ELSE 1 END END) AS mgmt_actual_revenue,
        MAX(CASE WHEN feature = '請求書発行'         THEN CASE health WHEN 'good' THEN 3 WHEN 'normal' THEN 2 ELSE 1 END END) AS mgmt_invoice,
        MAX(CASE WHEN feature = 'OCR処理'           THEN CASE health WHEN 'good' THEN 3 WHEN 'normal' THEN 2 ELSE 1 END END) AS mgmt_ocr,
        MAX(CASE WHEN feature = '原価ページPV'       THEN CASE health WHEN 'good' THEN 3 WHEN 'normal' THEN 2 ELSE 1 END END) AS mgmt_cost_pv
    FROM keiei_feature_health
    GROUP BY company_uuid, usage_month
)
SELECT
    w.company_name        AS company_name_jp,
    w.usage_month         AS month,
    w.plan_type           AS plan,
    w.lifecycle_stage     AS lifecycle,
    w.work_process,
    w.work_attendance,
    w.work_progress,
    w.work_whiteboard,
    w.work_diary,
    w.work_report,
    k.mgmt_project_status,
    k.mgmt_est_cost,
    k.mgmt_est_revenue,
    k.mgmt_actual_cost,
    k.mgmt_actual_revenue,
    k.mgmt_invoice,
    k.mgmt_ocr,
    k.mgmt_cost_pv
FROM health_val AS w
LEFT JOIN keiei_val AS k
    ON  w.company_uuid = k.company_uuid
    AND w.usage_month  = k.usage_month
ORDER BY w.company_name, w.usage_month
