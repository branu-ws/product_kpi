"""過去に Fan / Proactive だった全顧客の週次スコア推移を個社別に可視化する。

対象 : cross_product_monthly_company で一度でも fan/proactive の会社
y 軸 : work_score (施工管理) / keiei_score (経営管理) の生スコア
UI   : 検索付きリストボックスで 1 社 or 全社を切り替え

出力 : output/html/xproduct_company_score_weekly.html
"""

import json
from pathlib import Path

import pandas as pd
import plotly.colors
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import kpi.db as db
from kpi.config import TIER

# ---------- データ取得 ----------
conn = db.load()

df = conn.sql("""
WITH ever_fan_proactive AS (
    SELECT DISTINCT company_uuid
    FROM cross_product_monthly_company
    WHERE integration_tier IN ('fan', 'proactive')
)
SELECT
    w.week_start::DATE AS week_start,
    c.company_name,
    w.work_score,
    w.keiei_score
FROM cross_product_company_weekly w
JOIN ever_fan_proactive epf USING (company_uuid)
JOIN companies c USING (company_uuid)
ORDER BY c.company_name, w.week_start
""").df()

conn.close()

# ---------- 表示設定 ----------
companies = sorted(df["company_name"].unique())
n = len(companies)
COLORS = plotly.colors.qualitative.Alphabet

# ---------- Figure ----------
fig = make_subplots(
    rows=2,
    cols=1,
    subplot_titles=["施工管理  (work_score)", "経営管理  (keiei_score)"],
    shared_xaxes=True,
    vertical_spacing=0.1,
)

for i, company in enumerate(companies):
    color = COLORS[i % len(COLORS)]
    cdf = df[df["company_name"] == company].sort_values("week_start")
    common = dict(
        name=company,
        legendgroup=company,
        mode="lines",
        line=dict(color=color, width=1.8),
        connectgaps=False,
    )
    fig.add_trace(
        go.Scatter(
            x=cdf["week_start"],
            y=cdf["work_score"],
            showlegend=False,
            hovertemplate=f"{company}<br>%{{x}}  work: %{{y}}<extra></extra>",
            **common,
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=cdf["week_start"],
            y=cdf["keiei_score"],
            showlegend=False,
            hovertemplate=f"{company}<br>%{{x}}  keiei: %{{y}}<extra></extra>",
            **common,
        ),
        row=2,
        col=1,
    )

# アクティブ閾値ライン
for row in [1, 2]:
    fig.add_hline(
        y=TIER.xproduct_score_min,
        line=dict(color="rgba(0,0,0,0.25)", width=1.2, dash="dot"),
        row=row,
        col=1,
    )

# x 軸ラベル（全行）
months = pd.date_range(df["week_start"].min(), df["week_start"].max(), freq="MS")
tick_vals = [int(m.timestamp() * 1000) for m in months]
tick_text = [f"{m.strftime('%y')}-{m.month}" for m in months]
fig.for_each_xaxis(
    lambda ax: ax.update(
        showticklabels=True,
        matches=None,
        type="date",
        tickvals=tick_vals,
        ticktext=tick_text,
        tickangle=0,
        showgrid=True,
        gridcolor="#eeeeee",
    )
)

fig.update_layout(
    title=dict(
        text="X-PRODUCT Fan / Proactive 顧客  週次スコア推移", font=dict(size=16), x=0.5
    ),
    hovermode="closest",
    plot_bgcolor="white",
    paper_bgcolor="white",
    font=dict(family="Noto Sans JP, sans-serif", size=12),
    height=800,
    margin=dict(t=80, b=60, r=60, l=60),
    showlegend=False,
)
fig.update_yaxes(showgrid=True, gridcolor="#eeeeee", title_text="スコア")

# ---------- HTML 出力 + 検索ウィジェット注入 ----------
out_dir = Path(__file__).parent.parent / "output" / "html"
out_dir.mkdir(parents=True, exist_ok=True)
out_path = out_dir / "xproduct_company_score_weekly.html"

html = fig.to_html(include_plotlyjs="cdn", full_html=True, config={"responsive": True})

options_html = "\n".join(
    f'<option value="{i}">{c}</option>' for i, c in enumerate(companies)
)
companies_json = json.dumps(companies, ensure_ascii=False)

widget = f"""
<div id="company-selector" style="
  position: fixed; bottom: 24px; right: 24px; z-index: 9999;
  background: #ffffff; border: 1px solid #cccccc;
  border-radius: 10px; padding: 12px 14px;
  box-shadow: 0 3px 12px rgba(0,0,0,0.15);
  width: 220px;
  font-family: 'Noto Sans JP', sans-serif; font-size: 13px;
">
  <div style="font-weight:bold; color:#444; margin-bottom:8px;">🔍 顧客を選択</div>
  <input type="text" id="cs-search" placeholder="会社名を検索…"
    style="width:100%; padding:6px 8px; box-sizing:border-box;
           border:1px solid #ddd; border-radius:6px; font-size:12px; margin-bottom:6px;">
  <select id="cs-list" size="7"
    style="width:100%; border:1px solid #ddd; border-radius:6px;
           font-size:12px; padding:4px;">
    <option value="-1" selected>── 全社表示 ──</option>
    {options_html}
  </select>
</div>

<script>
(function(){{
  const n = {n};
  const search = document.getElementById('cs-search');
  const list   = document.getElementById('cs-list');
  const plot   = document.querySelector('.plotly-graph-div');

  search.addEventListener('input', function(){{
    const q = this.value.toLowerCase();
    Array.from(list.options).forEach(opt => {{
      opt.hidden = opt.value !== '-1' && !opt.text.toLowerCase().includes(q);
    }});
  }});

  list.addEventListener('change', function(){{
    const idx = parseInt(this.value);
    let visible;
    if (idx === -1) {{
      visible = Array(n * 2).fill(true);
    }} else {{
      visible = Array(n * 2).fill(false);
      visible[idx * 2]     = true;
      visible[idx * 2 + 1] = true;
    }}
    Plotly.restyle(plot, {{visible: visible}});
  }});
}})();
</script>
"""

html = html.replace("</body>", widget + "\n</body>")
out_path.write_text(html, encoding="utf-8")
print(f"出力: {out_path}")
