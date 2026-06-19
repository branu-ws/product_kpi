-- 経営管理 (careecon keiei) 顧客ロイヤリティ月次時系列 (横持ち / Notion 表示用)
SELECT
    month,
    COUNT(CASE WHEN loyalty_tier = '神'           THEN 1 END) AS god,
    COUNT(CASE WHEN loyalty_tier = 'ファン'        THEN 1 END) AS fan,
    COUNT(CASE WHEN loyalty_tier = '自走'          THEN 1 END) AS 自主利用,
    COUNT(CASE WHEN loyalty_tier = '2か月連続活用' THEN 1 END) AS 二か月連続利用,
    COUNT(CASE WHEN loyalty_tier = '断続的活用'    THEN 1 END) AS 断続的利用,
    COUNT(CASE WHEN loyalty_tier = 'まずい'        THEN 1 END) AS 利用停止,
    COUNT(CASE WHEN loyalty_tier = '離反状態'      THEN 1 END) AS 放置状態
FROM keiei_company_loyalty
GROUP BY month
ORDER BY month
