-- 経営管理 アウトプット1: 月別 顧客ロイヤリティ階層分布 (横ピボット)
-- loyalty_tier 値 → ASCII カラム名マッピング:
--   神=god, ファン=fan, 自走=jisou, 2か月連続活用=two_month, 断続的活用=occasional, まずい=at_risk, 離反状態=churned
SELECT
    usage_month,
    COUNT(DISTINCT CASE WHEN loyalty_tier = '神'           THEN company_name END) AS god,
    COUNT(DISTINCT CASE WHEN loyalty_tier = 'ファン'        THEN company_name END) AS fan,
    COUNT(DISTINCT CASE WHEN loyalty_tier = '自走'          THEN company_name END) AS jisou,
    COUNT(DISTINCT CASE WHEN loyalty_tier = '2か月連続活用' THEN company_name END) AS two_month,
    COUNT(DISTINCT CASE WHEN loyalty_tier = '断続的活用'    THEN company_name END) AS occasional,
    COUNT(DISTINCT CASE WHEN loyalty_tier = 'まずい'        THEN company_name END) AS at_risk,
    COUNT(DISTINCT CASE WHEN loyalty_tier = '離反状態'      THEN company_name END) AS churned
FROM keiei_company_loyalty
GROUP BY usage_month
ORDER BY usage_month
