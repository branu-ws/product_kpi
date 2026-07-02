"""写真アップロード・フォルダ作成の月次トレンド (Plus / Mini × 顧客数 / 作成数)"""

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
events AS (
    SELECT
        strftime(content_date, '%Y-%m') AS month,
        company_uuid,
        content AS feature
    FROM contents_user_history
    WHERE content IN ('写真アップロード', 'フォルダ作成')
      AND content_date >= '2024-01-01'
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
    FROM events
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
FEATURES = ["写真アップロード", "フォルダ作成"]
COLORS = {
    "写真アップロード": "#2ca02c",
    "フォルダ作成":     "#ff7f0e",
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
    title="写真・フォルダ作成トレンド — Plus / Mini × 顧客数 / 作成数",
    height=650,
    width=1000,
    legend=dict(title="", orientation="h", y=-0.12),
    hovermode="x unified",
    template="plotly_white",
)

fig.update_xaxes(dtick="M3", tickformat="%y-%m")

out = "output/html/work_photo_n_directory_trend.html"
fig.write_html(out, include_plotlyjs="cdn", config={"responsive": True})
print(f"Written: {out}")
