"""X-PRODUCT 顧客 Tier × Health Score の週次推移を Plotly Express facet で可視化する。

facet_row=integration_tier, color=usage_freq
サブプロット背景: Tier Trend カラーの暗めバージョンで着色
Health Score: 黒系グラデーション (good=濃 / bad=薄)

出力: output/html/xproduct_tier_health_trend_weekly.html
"""

from pathlib import Path

import pandas as pd
import plotly.express as px

import kpi.db as db

# ---------- データ取得 ----------
conn = db.load()

df = conn.sql("""
WITH actual AS (
    SELECT week_start::DATE AS week_start, integration_tier, usage_freq,
           COUNT(*) AS company_count
    FROM cross_product_company_weekly
    GROUP BY 1, 2, 3
),
scaffold AS (
    SELECT w.week_start, t.integration_tier, f.usage_freq
    FROM (SELECT DISTINCT week_start::DATE AS week_start FROM cross_product_company_weekly) w
    CROSS JOIN (SELECT DISTINCT integration_tier FROM cross_product_company_weekly) t
    CROSS JOIN (SELECT DISTINCT usage_freq       FROM cross_product_company_weekly) f
)
SELECT s.week_start, s.integration_tier, s.usage_freq,
       a.company_count
FROM scaffold s
LEFT JOIN actual a USING (week_start, integration_tier, usage_freq)
ORDER BY 1, 2, 3
""").df()

conn.close()

# ---------- 表示設定 ----------
TIER_ORDER = ["fan", "proactive", "passive", "onboarding"]
HEALTH_ORDER = ["bad", "normal", "good"]

TIER_LABEL = {
    "fan": "ファン",
    "proactive": "プロアクティブ",
    "passive": "パッシブ",
    "onboarding": "オンボーディング",
}

# Tier Trend (#1a6bb5, #2eaa6e, #f0a500, #d94f3d) を少し暗くしたもの → サブプロット背景
TIER_BG_COLOR = {
    "fan": "rgba( 13,  74, 138, 0.18)",
    "proactive": "rgba( 26, 107,  62, 0.18)",
    "passive": "rgba(168, 112,   0, 0.18)",
    "onboarding": "rgba(155,  32,  32, 0.18)",
}

# 黒系グラデーション: good=最も濃い, bad=最も薄い
HEALTH_COLOR = {
    "good": "#1a1a1a",
    "normal": "#686868",
    "bad": "#c0c0c0",
}

# ---------- Figure ----------
fig = px.area(
    df,
    x="week_start",
    y="company_count",
    color="usage_freq",
    facet_row="integration_tier",
    color_discrete_map=HEALTH_COLOR,
    category_orders={
        "integration_tier": TIER_ORDER,
        "usage_freq": HEALTH_ORDER,
    },
    labels={"company_count": "社数", "week_start": "週", "usage_freq": "Health Score"},
    title="X-PRODUCT 顧客 Tier × Health Score 週次推移",
    height=900,
    facet_row_spacing=0.02,
)

# facet ラベルを日本語に変換しつつ tier→domain マッピングを検出
# アノテーションの y 座標 ≈ 各サブプロットの上端 → 最近傍 yaxis を探す
tier_to_domain = {}
for ann in fig.layout.annotations:
    for key, label in TIER_LABEL.items():
        if ann.text == f"integration_tier={key}":
            ann.text = f"<b>{label}</b>"
            ann.font = dict(size=15, color="#222222")
            best_domain, best_dist = None, float("inf")
            for idx in range(1, len(TIER_ORDER) + 1):
                suf = "" if idx == 1 else str(idx)
                yax = fig.layout[f"yaxis{suf}"]
                if yax.domain is not None:
                    dist = abs(ann.y - yax.domain[1])
                    if dist < best_dist:
                        best_dist, best_domain = dist, yax.domain
            if best_domain:
                tier_to_domain[key] = best_domain
            break

# サブプロット背景を tier カラーで着色 (shapes を below に敷く)
for tier, domain in tier_to_domain.items():
    fig.add_shape(
        type="rect",
        xref="paper",
        yref="paper",
        x0=0,
        x1=1,
        y0=domain[0],
        y1=domain[1],
        fillcolor=TIER_BG_COLOR[tier],
        line_width=0,
        layer="below",
    )

fig.update_traces(hovertemplate="%{y}社<extra></extra>")

fig.update_layout(
    hovermode="x unified",
    plot_bgcolor="rgba(0,0,0,0)",  # 透明 → shape の背景色を表示
    paper_bgcolor="#ffffff",
    font=dict(family="Noto Sans JP, sans-serif", size=12, color="#333333"),
    margin=dict(t=100, b=60, r=180),
    legend=dict(
        title="Health Score",
        x=1.01,
        y=1,
        bgcolor="rgba(255,255,255,0.9)",
        bordercolor="#dddddd",
        borderwidth=1,
    ),
)
# 月初ごとに "26-4" 形式のラベルを生成 (Plotly date 軸は ms 単位の UNIX 時刻を受け付ける)
months = pd.date_range(df["week_start"].min(), df["week_start"].max(), freq="MS")
tick_vals = [int(m.timestamp() * 1000) for m in months]
tick_text = [f"{m.strftime('%y')}-{m.month}" for m in months]

# 全 facet 行に x 軸ラベルを表示 (matches=None で各行独立 → showticklabels が効く)
fig.for_each_xaxis(
    lambda ax: ax.update(
        showticklabels=True,
        matches=None,
        tickvals=tick_vals,
        ticktext=tick_text,
        tickangle=0,
        showgrid=True,
        gridcolor="rgba(0,0,0,0.07)",
        type="date",
    )
)
fig.update_yaxes(showgrid=True, gridcolor="rgba(0,0,0,0.07)", matches=None)

# ---------- 出力 ----------
out_dir = Path(__file__).parent.parent / "output" / "html"
out_dir.mkdir(parents=True, exist_ok=True)
out_path = out_dir / "xproduct_tier_health_trend_weekly.html"

fig.write_html(str(out_path), include_plotlyjs="cdn", config={"responsive": True})
print(f"出力: {out_path}")
