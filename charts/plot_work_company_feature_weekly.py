"""Work (施工管理) Fan / Proactive 顧客の機能別週次利用数を個社別に可視化する。

対象  : work_monthly_company で一度でも fan/proactive の会社
facet : 機能 (工程作成 / 掲示板 / 報告書 / 出面 / 日報 / 出来高)
color : 会社名
UI    : 検索付きリストボックスで 1 社 or 全社を切り替え

出力  : output/html/work_company_feature_weekly.html
"""

import json
from pathlib import Path

import pandas as pd
import plotly.colors
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import kpi.db as db
from kpi.config import FEATURE_THRESHOLDS, TIER

# ---------- データ取得 ----------
conn = db.load()

# 90 週の起点
cutoff = (
    pd.Timestamp.today().normalize()
    - pd.tseries.offsets.Week(weekday=0)
    - pd.Timedelta(weeks=TIER.weekly_window - 1)
)

df = conn.sql(f"""
WITH ever_fan_proactive AS (
    SELECT DISTINCT company_uuid
    FROM work_monthly_company
    WHERE diversity_tier IN ('fan', 'proactive')
),
weekly_raw AS (
    SELECT
        DATE_TRUNC('week', h.content_date::DATE) AS week_start,
        p.company_uuid,
        CASE WHEN h.content IN ('大工程', '小工程') THEN '工程作成'
             ELSE h.content
        END AS feature,
        COUNT(*) AS event_count
    FROM work_user_history h
    JOIN work_process_id_generator p USING (pid)
    JOIN ever_fan_proactive epf USING (company_uuid)
    WHERE h.content_date >= '{cutoff.date()}'
    GROUP BY 1, 2, 3
),
-- 全週 × 全社 × 全機能 のスキャフォールド (NULL = 活動なし → 線を切る)
all_weeks AS (
    SELECT DISTINCT week_start FROM weekly_raw
),
all_companies AS (
    SELECT DISTINCT p.company_uuid, c.company_name
    FROM work_process_id_generator p
    JOIN ever_fan_proactive epf USING (company_uuid)
    JOIN companies c USING (company_uuid)
),
all_features AS (
    SELECT DISTINCT feature FROM weekly_raw
),
scaffold AS (
    SELECT w.week_start, ac.company_uuid, ac.company_name, f.feature
    FROM all_weeks w
    CROSS JOIN all_companies ac
    CROSS JOIN all_features f
)
SELECT s.week_start, s.company_name, s.feature,
       r.event_count
FROM scaffold s
LEFT JOIN weekly_raw r
    ON s.week_start = r.week_start
   AND s.company_uuid = r.company_uuid
   AND s.feature = r.feature
ORDER BY s.feature, s.company_name, s.week_start
""").df()

conn.close()

# ---------- 週次スコアに変換 (good=2 / normal=1 / bad=0) ----------
# 月次閾値 ÷ 4.3 で週次近似
WEEKS_PER_MONTH = 4.3


def to_score(count, feature):
    if pd.isna(count):
        return None  # 線を切る
    t = FEATURE_THRESHOLDS.get(feature)
    if t is None:
        return 0
    if count >= t.good_min / WEEKS_PER_MONTH:
        return 2
    if count >= t.normal_min / WEEKS_PER_MONTH:
        return 1
    return 0


df["score"] = df.apply(lambda r: to_score(r["event_count"], r["feature"]), axis=1)

# ---------- 表示設定 ----------
FEATURE_ORDER = [
    "工程作成",
    "掲示板",
    "報告書",
    "出面",
    "日報",
    "出来高",
    "AIアシスタント",
    "写真アップロード",
    "フォルダ作成",
]
# データに存在する機能のみに絞り、順序を維持
features = [f for f in FEATURE_ORDER if f in df["feature"].unique()]
companies = sorted(df["company_name"].unique())
n_feat = len(features)
n_comp = len(companies)

COLORS = plotly.colors.qualitative.Alphabet

# ---------- Figure ----------
fig = make_subplots(
    rows=n_feat,
    cols=1,
    subplot_titles=features,
    shared_xaxes=True,
    vertical_spacing=0.04,
)

for ci, company in enumerate(companies):
    color = COLORS[ci % len(COLORS)]
    cdf = df[df["company_name"] == company]

    for fi, feature in enumerate(features):
        fdf = cdf[cdf["feature"] == feature].sort_values("week_start")
        fig.add_trace(
            go.Scatter(
                x=fdf["week_start"],
                y=fdf["score"],
                name=company,
                legendgroup=company,
                showlegend=(fi == 0),
                mode="lines",
                line=dict(color=color, width=1.8),
                connectgaps=False,
                hovertemplate=f"{company}<br>%{{x}}  {feature}: %{{y}} (0=bad/1=normal/2=good)<extra></extra>",
            ),
            row=fi + 1,
            col=1,
        )

# ---------- x 軸ラベル（全行）----------
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
fig.update_yaxes(showgrid=True, gridcolor="#eeeeee", title_text="件数")

# サブタイトルを太字に
for ann in fig.layout.annotations:
    ann.font = dict(size=13, color="#222222")
    ann.text = f"<b>{ann.text}</b>"

fig.update_layout(
    title=dict(
        text="Work (施工管理) Fan / Proactive 顧客  機能別週次利用数",
        font=dict(size=16),
        x=0.5,
    ),
    hovermode="closest",
    plot_bgcolor="white",
    paper_bgcolor="white",
    font=dict(family="Noto Sans JP, sans-serif", size=12),
    height=1400,
    width=1200,
    margin=dict(t=80, b=60, r=60, l=60),
    showlegend=False,
)
fig.update_yaxes(
    tickvals=[0, 1, 2],
    ticktext=["bad (0)", "normal (1)", "good (2)"],
    range=[-0.1, 2.2],
)

# ---------- HTML 出力 + 検索ウィジェット注入 ----------
out_dir = Path(__file__).parent.parent / "output" / "html"
out_dir.mkdir(parents=True, exist_ok=True)
out_path = out_dir / "work_company_feature_weekly.html"

html = fig.to_html(include_plotlyjs="cdn", full_html=True)

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
  const nComp = {n_comp};
  const nFeat = {n_feat};
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
    const ci = parseInt(this.value);
    let visible;
    if (ci === -1) {{
      visible = Array(nComp * nFeat).fill(true);
    }} else {{
      visible = Array(nComp * nFeat).fill(false);
      for (let fi = 0; fi < nFeat; fi++) {{
        visible[ci * nFeat + fi] = true;
      }}
    }}
    Plotly.restyle(plot, {{visible: visible}});
  }});
}})();
</script>
"""

html = html.replace("</body>", widget + "\n</body>")
out_path.write_text(html, encoding="utf-8")
print(f"出力: {out_path}")
