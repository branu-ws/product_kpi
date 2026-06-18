-- 月別 × content ごとの KPI 集計
-- テーブル: work_user_history / work_process_id_generator / companies

SELECT
    strftime(h.content_date, '%Y-%m') AS usage_month,
    h.content,
    COUNT(*)                           AS content_count,
    COUNT(DISTINCT c.company_name)     AS company_count,
    COUNT(DISTINCT h.created_by)       AS user_count
FROM work_user_history AS h
INNER JOIN work_process_id_generator AS p ON h.pid = p.pid
INNER JOIN companies AS c ON p.company_uuid = c.company_uuid
GROUP BY usage_month, h.content
ORDER BY usage_month, h.content
