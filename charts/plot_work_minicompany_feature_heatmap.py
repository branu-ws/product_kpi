"""Work Mini Fan / Proactive 顧客の機能別月次ヒートマップ。"""

from pathlib import Path

import kpi.db as db
from kpi.config import FEATURE_THRESHOLDS
from kpi.heatmap import build_heatmap

conn = db.load()
df = conn.sql("""
WITH mini_only AS (
    SELECT DISTINCT company_uuid FROM mini_customer_lifecycle
    EXCEPT
    SELECT company_uuid FROM sf_customers
),
fan_proactive AS (
    SELECT DISTINCT company_uuid
    FROM mini_work_monthly_company
    WHERE diversity_tier IN ('fan', 'proactive')
      AND company_uuid IN (SELECT company_uuid FROM mini_only)
)
SELECT fh.month        AS usage_month,
       fh.company_name,
       fh.feature,
       fh.usage_count  AS event_count
FROM mini_feature_health fh
JOIN fan_proactive USING (company_uuid)
WHERE fh.month >= '2024-10'
ORDER BY 1, 2, 3
""").df()
conn.close()

build_heatmap(
    df=df,
    thresholds=FEATURE_THRESHOLDS,
    feature_order=[
        "工程作成",
        "掲示板",
        "報告書",
        "出面",
        "日報",
        "出来高",
        "AIアシスタント",
        "写真アップロード",
        "フォルダ作成",
    ],
    title="Work Mini Fan / Proactive 顧客  機能別月次ヒートマップ",
    out_path=Path(__file__).parent.parent
    / "output/html/work_minicompany_feature_heatmap.html",
)
