"""出面・日報・報告書・AIアシスタントの月次トレンド (Plus / Mini × 顧客数 / 作成数)"""

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import kpi.db as db

conn = db.load()

df = conn.sql("""
WITH mini_only AS (
    SELECT DISTINCT company_uuid FROM mini_customer_lifecycle
    EXCEPT
    SELECT company_uuid FROM sf_customers
),
-- 出面・日報・報告書: work_user_history → pid 経由で company_uuid
work_events AS (
    SELECT
        strftime(content_date, '%Y-%m') AS month,
        pig.company_uuid,
        content AS feature
    FROM work_user_history wh
    JOIN work_process_id_generator pig ON wh.pid = pig.pid
    WHERE content IN ('出面', '日報', '報告書')
      AND content_date >= '2024-01-01'
),
-- AIアシスタント: ai_user_history は company_uuid 直接
ai AS (
    SELECT
        strftime(content_date, '%Y-%m') AS month,
        company_uuid,
        'AIアシスタント' AS feature
    FROM ai_user_history
    WHERE content_date >= '2024-01-01'
),
all_events AS (
    SELECT month, company_uuid, feature FROM work_events
    UNION ALL
    SELECT month, company_uuid, feature FROM ai
),
segmented AS (
    SELECT
        month,
        feature,
        CASE
            WHEN company_uuid IN (SELECT company_uuid FROM sf_all_plus_customers) THEN 'Plus'
            WHEN company_uuid IN (SELECT company_uuid FROM mini_only)             THEN 'Mini'
        END AS segment,
        company_uuid
    FROM all_events
)
SELECT
    month,
    feature,
    segment,
    COUNT(DISTINCT company_uuid) AS companies,
    COUNT(*)                     AS events
FROM segmented
WHERE segment IS NOT NULL
GROUP BY month, feature, segment
ORDER BY month, segment, feature
""").df()

conn.close()

df["month_dt"] = pd.to_datetime(df["month"] + "-01")

SEGMENTS = ["Plus", "Mini"]
FEATURES = ["出面", "日報", "報告書", "AIアシスタント"]
COLORS = {
    "出面":           "#1f77b4",
    "日報":           "#9467bd",
    "報告書":         "#8c564b",
    "AIアシスタント": "#d62728",
}
METRICS = [("companies", "顧客数 (社)"), ("events", "作成数 (件)")]

fig = make_subplots(
    rows=2,
    cols=2,
    row_titles=SEGMENTS,
    column_titles=[m[1] for m in METRICS],
    shared_xaxes=True,
    vertical_spacing=0.12,
    horizontal_spacing=0.08,
)

for r, segment in enumerate(SEGMENTS, start=1):
    for c, (metric, _) in enumerate(METRICS, start=1):
        for feature in FEATURES:
            sub = df[(df["segment"] == segment) & (df["feature"] == feature)]
            fig.add_trace(
                go.Scatter(
                    x=sub["month_dt"],
                    y=sub[metric],
                    mode="lines+markers",
                    name=feature,
                    legendgroup=feature,
                    showlegend=(r == 1 and c == 1),
                    line=dict(color=COLORS[feature]),
                    marker=dict(size=5),
                    hovertemplate=f"{segment} / {feature}<br>%{{x|%Y-%m}}<br>{metric}: %{{y}}<extra></extra>",
                ),
                row=r,
                col=c,
            )

fig.update_layout(
    title="出面・日報・報告書・AI トレンド — Plus / Mini × 顧客数 / 作成数",
    height=650,
    width=1000,
    legend=dict(title="", orientation="h", y=-0.12),
    hovermode="x unified",
    template="plotly_white",
)

fig.update_xaxes(dtick="M3", tickformat="%y-%m")

out = "output/html/work_attendance_n_reports.html"
fig.write_html(out, include_plotlyjs="cdn")
print(f"Written: {out}")
