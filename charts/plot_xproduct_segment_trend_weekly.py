"""X-PRODUCT 各 segment の週次推移を Plotly で可視化する。

出力: output/html/xproduct_segment_trend_weekly.html
"""

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

import kpi.db as db

# ---------- データ取得 ----------
conn = db.load()

df = conn.sql("""
    SELECT
        week_start,
        integration_tier,
        COUNT(*) AS company_count
    FROM cross_product_company_weekly
    GROUP BY week_start, integration_tier
    ORDER BY week_start, integration_tier
""").df()

conn.close()

# ---------- 表示設定 ----------
TIER_ORDER = ["onboarding", "passive", "proactive", "fan"]

TIER_COLOR = {
    "fan": "#1a6bb5",
    "proactive": "#2eaa6e",
    "passive": "#f0a500",
    "onboarding": "#d94f3d",
}

TIER_LABEL = {
    "fan": "ファン (両PD × 3ヶ月継続)",
    "proactive": "プロアクティブ (いずれか × 3ヶ月継続)",
    "passive": "パッシブ",
    "onboarding": "オンボーディング",
}

# ---------- pivot ----------
df["week_start"] = pd.to_datetime(df["week_start"])
pivot = (
    df.pivot(index="week_start", columns="integration_tier", values="company_count")
    .reindex(columns=TIER_ORDER)
    .fillna(0)
    .astype(int)
)
weeks = [d.strftime("%Y-%m-%d") for d in pivot.index]

# ---------- Figure ----------
fig = go.Figure()

for tier in TIER_ORDER:
    if tier not in pivot.columns:
        continue
    counts = pivot[tier].tolist()
    fig.add_trace(
        go.Scatter(
            x=weeks,
            y=counts,
            name=TIER_LABEL[tier],
            mode="lines",
            stackgroup="one",
            fillcolor=TIER_COLOR[tier],
            line=dict(color=TIER_COLOR[tier], width=1),
            hovertemplate="%{meta}<br>%{x}  %{y}社<extra></extra>",
            meta=TIER_LABEL[tier],
        )
    )

total = pivot.sum(axis=1)
fig.add_trace(
    go.Scatter(
        x=weeks,
        y=total.tolist(),
        name="合計",
        mode="lines+markers",
        line=dict(color="#333333", width=2, dash="dot"),
        marker=dict(size=5),
        hovertemplate="合計<br>%{x}  %{y}社<extra></extra>",
    )
)

fig.update_layout(
    title=dict(
        text="X-PRODUCT 顧客セグメント推移（週次・社数）",
        font=dict(size=18),
    ),
    xaxis=dict(
        title="週",
        type="date",
        tickformat="%Y-%m-%d",
        tickangle=-45,
        showgrid=True,
        gridcolor="#eeeeee",
        rangeslider=dict(visible=True, thickness=0.08),
        rangeselector=dict(
            buttons=[
                dict(count=28, label="4週", step="day", stepmode="backward"),
                dict(count=56, label="8週", step="day", stepmode="backward"),
                dict(count=3, label="3ヶ月", step="month", stepmode="backward"),
                dict(step="all", label="全期間"),
            ],
            bgcolor="#f5f5f5",
            activecolor="#d0d0d0",
        ),
    ),
    yaxis=dict(
        title="社数",
        showgrid=True,
        gridcolor="#eeeeee",
    ),
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="right",
        x=1,
    ),
    hovermode="x unified",
    plot_bgcolor="white",
    paper_bgcolor="white",
    font=dict(family="Noto Sans JP, sans-serif", size=12),
    margin=dict(t=100, b=40),
    height=680,
    width=1300,
)

# ---------- 出力 ----------
out_dir = Path(__file__).parent.parent / "output" / "html"
out_dir.mkdir(parents=True, exist_ok=True)
out_path = out_dir / "xproduct_segment_trend_weekly.html"

fig.write_html(str(out_path), include_plotlyjs="cdn")
print(f"出力: {out_path}")
