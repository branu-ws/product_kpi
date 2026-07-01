"""経営管理 機能別月次トレンド (Plus 顧客のみ × 顧客数 / 作成数)"""

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import kpi.db as db

conn = db.load()

df = conn.sql("""
SELECT
    strftime(content_date, '%Y-%m') AS month,
    content                          AS feature,
    COUNT(DISTINCT company_uuid)     AS companies,
    COUNT(*)                         AS events
FROM keiei_user_history
WHERE company_uuid IN (SELECT company_uuid FROM sf_all_plus_customers)
  AND content_date >= '2024-01-01'
GROUP BY month, feature
ORDER BY month, feature
""").df()

conn.close()

df["month_dt"] = pd.to_datetime(df["month"] + "-01")

FEATURES = [
    "案件ステータス更新",
    "見積原価登録",
    "見積売上登録",
    "実績原価登録",
    "実績売上登録",
    "請求書発行",
    "OCR処理",
    "原価ページPV",
]
COLORS = {
    "案件ステータス更新": "#1f77b4",
    "見積原価登録":       "#ff7f0e",
    "見積売上登録":       "#2ca02c",
    "実績原価登録":       "#d62728",
    "実績売上登録":       "#9467bd",
    "請求書発行":         "#8c564b",
    "OCR処理":            "#e377c2",
    "原価ページPV":       "#17becf",
}
METRICS = [("companies", "顧客数 (社)"), ("events", "作成数 (件)")]

fig = make_subplots(
    rows=1,
    cols=2,
    column_titles=[m[1] for m in METRICS],
    shared_xaxes=True,
    horizontal_spacing=0.08,
)

for c, (metric, _) in enumerate(METRICS, start=1):
    for feature in FEATURES:
        sub = df[df["feature"] == feature]
        fig.add_trace(
            go.Scatter(
                x=sub["month_dt"],
                y=sub[metric],
                mode="lines+markers",
                name=feature,
                legendgroup=feature,
                showlegend=(c == 1),
                line=dict(color=COLORS.get(feature, "#888888")),
                marker=dict(size=5),
                hovertemplate=f"{feature}<br>%{{x|%Y-%m}}<br>{metric}: %{{y}}<extra></extra>",
            ),
            row=1,
            col=c,
        )

fig.update_layout(
    title="経営管理 機能別月次トレンド — Plus 顧客 × 顧客数 / 作成数",
    height=450,
    width=1050,
    legend=dict(title="", orientation="h", y=-0.22),
    hovermode="x unified",
    template="plotly_white",
)

fig.update_xaxes(dtick="M3", tickformat="%y-%m")

out = "output/html/keiei_feature_trend.html"
fig.write_html(out, include_plotlyjs="cdn")
print(f"Written: {out}")
