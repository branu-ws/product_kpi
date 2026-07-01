"""経営管理 Fan / Proactive 顧客の機能別月次ヒートマップ。"""

from pathlib import Path

import kpi.db as db
from kpi.config import KEIEI_FEATURE_THRESHOLDS
from kpi.heatmap import build_heatmap

conn = db.load()
df = conn.sql("""
WITH fan_proactive AS (
    SELECT DISTINCT company_uuid
    FROM keiei_monthly_company
    WHERE diversity_tier IN ('fan', 'proactive')
      AND company_uuid IN (SELECT company_uuid FROM sf_customers)
),
monthly_raw AS (
    SELECT STRFTIME(content_date::DATE, '%Y-%m') AS usage_month,
           h.company_uuid, h.content AS feature, COUNT(*) AS event_count
    FROM keiei_user_history h
    JOIN fan_proactive USING (company_uuid)
    GROUP BY 1, 2, 3
)
SELECT m.usage_month, c.company_name, m.feature, m.event_count
FROM monthly_raw m JOIN companies c USING (company_uuid)
ORDER BY 1, 2, 3
""").df()
conn.close()

build_heatmap(
    df=df,
    thresholds=KEIEI_FEATURE_THRESHOLDS,
    feature_order=[
        "案件ステータス更新",
        "OCR処理",
        "実績原価登録",
        "実績売上登録",
        "見積売上登録",
        "原価ページPV",
        "見積原価登録",
        "請求書発行",
    ],
    feature_label={"案件ステータス更新": "案件ステータス<br>更新"},
    title="経営管理 Fan / Proactive 顧客  機能別月次ヒートマップ",
    out_path=Path(__file__).parent.parent
    / "output/html/keiei_company_feature_heatmap.html",
)
