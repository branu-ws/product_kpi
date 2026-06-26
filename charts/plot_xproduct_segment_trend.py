"""X-PRODUCT 各 segment の時系列推移を Plotly で可視化する。

出力: output/html/xproduct_segment_trend.html
"""

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

import kpi.db as db

# ---------- データ取得 ----------
conn = db.load()

df = conn.sql("""
    SELECT
        usage_month,
        integration_tier,
        COUNT(*) AS company_count
    FROM cross_product_monthly_company
    WHERE usage_month >= '2025-01'
    GROUP BY usage_month, integration_tier
    ORDER BY usage_month, integration_tier
""").df()

conn.close()

# ---------- 表示設定 ----------
TIER_ORDER = ["onboarding", "passive", "proactive", "fan"]

TIER_COLOR = {
    "fan":        "#1a6bb5",
    "proactive":  "#2eaa6e",
    "passive":    "#f0a500",
    "onboarding": "#d94f3d",
}

TIER_LABEL = {
    "fan":        "ファン (両PD × 3ヶ月継続)",
    "proactive":  "プロアクティブ (いずれか × 3ヶ月継続)",
    "passive":    "パッシブ",
    "onboarding": "オンボーディング",
}

# ---------- pivot ----------
pivot = (
    df.pivot(index="usage_month", columns="integration_tier", values="company_count")
    .reindex(columns=TIER_ORDER)
    .fillna(0)
    .astype(int)
)
# YYYY-MM → YYYY-MM-01 に変換して date 軸として扱う (rangeslider に必要)
months = [m + "-01" for m in pivot.index.tolist()]

# ---------- Figure ----------
fig = go.Figure()

# 積み上げエリア（下から onboarding → fan の順）
for tier in TIER_ORDER:
    if tier not in pivot.columns:
        continue
    counts = pivot[tier].tolist()
    fig.add_trace(go.Scatter(
        x=months,
        y=counts,
        name=TIER_LABEL[tier],
        mode="lines",
        stackgroup="one",
        fillcolor=TIER_COLOR[tier],
        line=dict(color=TIER_COLOR[tier], width=1),
        hovertemplate="%{meta}<br>%{x}  %{y}社<extra></extra>",
        meta=TIER_LABEL[tier],
    ))

# 合計ラインをオーバーレイ
total = pivot.sum(axis=1)
fig.add_trace(go.Scatter(
    x=months,
    y=total.tolist(),
    name="合計",
    mode="lines+markers",
    line=dict(color="#333333", width=2, dash="dot"),
    marker=dict(size=5),
    hovertemplate="合計<br>%{x}  %{y}社<extra></extra>",
))

fig.update_layout(
    title=dict(
        text="X-PRODUCT 顧客セグメント推移（月次・社数）",
        font=dict(size=18),
    ),
    xaxis=dict(
        title="月",
        type="date",
        tickformat="%Y-%m",
        tickangle=-45,
        showgrid=True,
        gridcolor="#eeeeee",
        rangeslider=dict(visible=True, thickness=0.08),
        rangeselector=dict(
            buttons=[
                dict(count=6,  label="6ヶ月", step="month", stepmode="backward"),
                dict(count=12, label="1年",   step="month", stepmode="backward"),
                dict(count=24, label="2年",   step="month", stepmode="backward"),
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
    width=1000,
)

# ---------- 出力 ----------
out_dir = Path(__file__).parent.parent / "output" / "html"
out_dir.mkdir(parents=True, exist_ok=True)
out_path = out_dir / "xproduct_segment_trend.html"

fig.write_html(str(out_path), include_plotlyjs="cdn")
print(f"出力: {out_path}")
