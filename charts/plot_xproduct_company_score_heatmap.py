"""X-Product Fan / Proactive 顧客の月次スコアヒートマップ。

x = プロダクト (施工管理 / 経営管理), y = YYYY-MM, facet_row = 企業
color: good/normal/bad = TIER.usage_freq_good/normal 閾値で判定
"""

from pathlib import Path

import kpi.db as db
from kpi.config import TIER
from kpi.heatmap import build_heatmap


# TIER スコア閾値を FeatureThreshold 互換オブジェクトで定義
class _T:
    def __init__(self, good, normal):
        self.good_min = good
        self.normal_min = normal


XPRODUCT_THRESHOLDS = {
    "施工管理": _T(TIER.usage_freq_good, TIER.usage_freq_normal),
    "経営管理": _T(TIER.usage_freq_good, TIER.usage_freq_normal),
}

conn = db.load()
df = conn.sql("""
WITH fan_proactive AS (
    SELECT DISTINCT company_uuid
    FROM cross_product_monthly_company
    WHERE integration_tier IN ('fan', 'proactive')
),
monthly AS (
    SELECT
        STRFTIME(week_start::DATE, '%Y-%m') AS usage_month,
        company_uuid,
        ROUND(AVG(work_score))  AS work_score,
        ROUND(AVG(keiei_score)) AS keiei_score
    FROM cross_product_company_weekly
    WHERE company_uuid IN (SELECT company_uuid FROM fan_proactive)
    GROUP BY 1, 2
)
SELECT usage_month, c.company_name, '施工管理' AS feature, work_score  AS event_count
FROM monthly m JOIN companies c USING (company_uuid)
UNION ALL
SELECT usage_month, c.company_name, '経営管理' AS feature, keiei_score AS event_count
FROM monthly m JOIN companies c USING (company_uuid)
ORDER BY 1, 2, 3
""").df()
conn.close()

build_heatmap(
    df=df,
    thresholds=XPRODUCT_THRESHOLDS,
    feature_order=["施工管理", "経営管理"],
    title="X-Product Fan / Proactive 顧客  月次スコアヒートマップ",
    out_path=Path(__file__).parent.parent
    / "output/html/xproduct_company_score_heatmap.html",
    count_label="スコア",
    count_suffix="",
)
