"""Work Mini Fan / Proactive 顧客の機能別月次ヒートマップ。"""

from pathlib import Path
import kpi.db as db
from kpi.config import FEATURE_THRESHOLDS
from kpi.heatmap import build_heatmap

conn = db.load()
df = conn.sql("""
WITH mini_only AS (
    -- mini_customer_lifecycle に存在し、かつ sf_customers (Plus確認済み) に含まれない
    SELECT DISTINCT company_uuid FROM mini_customer_lifecycle
    EXCEPT
    SELECT company_uuid FROM sf_customers
),
fan_proactive AS (
    SELECT DISTINCT company_uuid
    FROM mini_work_monthly_company
    WHERE diversity_tier IN ('fan', 'proactive')
      AND company_uuid IN (SELECT company_uuid FROM mini_only)
),
monthly_raw AS (
    SELECT STRFTIME(content_date::DATE, '%Y-%m') AS usage_month,
           p.company_uuid,
           CASE WHEN h.content IN ('大工程', '小工程') THEN '工程作成'
                ELSE h.content END AS feature,
           COUNT(*) AS event_count
    FROM work_user_history h
    JOIN work_process_id_generator p USING (pid)
    JOIN fan_proactive USING (company_uuid)
    GROUP BY 1, 2, 3
)
SELECT m.usage_month, c.company_name, m.feature, m.event_count
FROM monthly_raw m JOIN companies c USING (company_uuid)
WHERE m.usage_month >= '2024-10'
ORDER BY 1, 2, 3
""").df()
conn.close()

build_heatmap(
    df=df,
    thresholds=FEATURE_THRESHOLDS,
    feature_order=["工程作成", "掲示板", "報告書", "出面", "日報", "出来高", "AIアシスタント", "写真アップロード", "フォルダ作成"],
    title="Work Mini Fan / Proactive 顧客  機能別月次ヒートマップ",
    out_path=Path(__file__).parent.parent / "output/html/work_minicompany_feature_heatmap.html",
)
