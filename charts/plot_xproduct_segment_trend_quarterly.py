"""X-PRODUCT 各 segment の四半期推移を Plotly で可視化する。

四半期内の各社 integration_tier は月次ティアの最大値（最良値）を採用。
  例: Fan×1ヶ月 + Proactive×2ヶ月 → その四半期は Fan

出力: output/html/xproduct_segment_trend_quarterly.html
"""

from pathlib import Path

import plotly.graph_objects as go

import kpi.db as db

# ---------- データ取得 ----------
conn = db.load()

df = conn.sql("""
WITH best_tier AS (
    SELECT
        YEAR((usage_month || '-01')::DATE) || '-Q' ||
        QUARTER((usage_month || '-01')::DATE) AS quarter,
        company_uuid,
        CASE MAX(CASE integration_tier
            WHEN 'fan'        THEN 4
            WHEN 'proactive'  THEN 3
            WHEN 'passive'    THEN 2
            WHEN 'onboarding' THEN 1
            ELSE 0
        END)
            WHEN 4 THEN 'fan'
            WHEN 3 THEN 'proactive'
            WHEN 2 THEN 'passive'
            WHEN 1 THEN 'onboarding'
        END AS integration_tier
    FROM cross_product_monthly_company
    WHERE usage_month >= '2024-10'
    GROUP BY 1, 2
)
SELECT quarter, integration_tier, COUNT(*) AS company_count
FROM best_tier
GROUP BY 1, 2
ORDER BY 1, 2
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
    "fan": "ファン (四半期内に1ヶ月以上 両PD)",
    "proactive": "プロアクティブ (四半期内に1ヶ月以上 いずれか)",
    "passive": "パッシブ",
    "onboarding": "オンボーディング",
}

# ---------- pivot ----------
pivot = (
    df.pivot(index="quarter", columns="integration_tier", values="company_count")
    .reindex(columns=TIER_ORDER)
    .fillna(0)
    .astype(int)
)
quarters = pivot.index.tolist()

# ---------- Figure ----------
fig = go.Figure()

for tier in TIER_ORDER:
    if tier not in pivot.columns:
        continue
    counts = pivot[tier].tolist()
    fig.add_trace(
        go.Bar(
            x=quarters,
            y=counts,
            name=TIER_LABEL[tier],
            marker_color=TIER_COLOR[tier],
            hovertemplate="%{meta}<br>%{x}  %{y}社<extra></extra>",
            meta=TIER_LABEL[tier],
        )
    )

total = pivot.sum(axis=1)
fig.add_trace(
    go.Scatter(
        x=quarters,
        y=total.tolist(),
        name="合計",
        mode="lines+markers",
        line=dict(color="#333333", width=2, dash="dot"),
        marker=dict(size=6),
        hovertemplate="合計<br>%{x}  %{y}社<extra></extra>",
    )
)

fig.update_layout(
    title=dict(
        text="X-PRODUCT 顧客セグメント推移（四半期・社数・最良ティア集計）",
        font=dict(size=18),
    ),
    barmode="stack",
    xaxis=dict(
        title="四半期",
        showgrid=True,
        gridcolor="#eeeeee",
        tickangle=-30,
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
    margin=dict(t=100, b=60),
    height=680,
    width=1300,
)

# ---------- 出力 ----------
out_dir = Path(__file__).parent.parent / "output" / "html"
out_dir.mkdir(parents=True, exist_ok=True)
out_path = out_dir / "xproduct_segment_trend_quarterly.html"

fig.write_html(str(out_path), include_plotlyjs="cdn", config={"responsive": True})
print(f"出力: {out_path}")
