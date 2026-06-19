-- クロスプロダクト 企業別週次スコア (縦持ち)
-- integration_tier : 前月末の3ヶ月判定値 (fan / proactive / passive / onboarding)
-- usage_freq       : 当週の稼働日割スコアによる判定 (good / normal / bad)
SELECT
    week_start,
    company_uuid,
    company_name,
    work_score,
    keiei_score,
    total_score,
    usage_freq,
    integration_tier
FROM cross_product_company_weekly
ORDER BY week_start, company_uuid
