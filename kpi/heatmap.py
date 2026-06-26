"""プロダクト共通の 機能別月次ヒートマップ生成ロジック。

build_heatmap(df, thresholds, feature_order, feature_label, title, out_path)
  df: usage_month / company_name / feature / event_count の DataFrame
"""

import json
from pathlib import Path

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

SCORE_LABEL = {0: "bad", 1: "normal", 2: "good"}

COLORSCALE = [
    [0.0, "#bfdbfe"],  # bad   : スカイブルー
    [0.5, "#3b82f6"],  # normal: ビビッドブルー
    [1.0, "#1e3a8a"],  # good  : ロイヤルブルー
]

FIXED_PER_H = 57   # px / company block
COL_W       = 90   # px / feature column (124→90 で幅を縮小)
GAP_H    = 6
MARGIN_L = 150     # Plotly 内部の左余白 (固定名前列が被さる)
NAME_COL_W = 148   # 左固定社名列の幅 (px)
MARGIN_R = 40
MARGIN_T = 60
MARGIN_B = 20
HEADER_H = 52


def _wrap_name(name: str) -> str:
    for sp in [" ", "　"]:
        if sp in name:
            return name.replace(sp, "<br>", 1)
    for kk in ["株式会社", "有限会社", "合同会社"]:
        if name.startswith(kk) and len(name) > len(kk):
            return kk + "<br>" + name[len(kk):]
        if name.endswith(kk) and len(name) > len(kk):
            return name[: -len(kk)] + "<br>" + kk
    mid = len(name) // 2
    return name[:mid] + "<br>" + name[mid:]


def _to_score(count, feature, thresholds):
    if count is None:
        return np.nan
    t = thresholds.get(feature)
    if t is None:
        return np.nan
    if count >= t.good_min:
        return 2.0
    if count >= t.normal_min:
        return 1.0
    return 0.0


def build_heatmap(
    df,
    thresholds: dict,
    feature_order: list[str],
    title: str,
    out_path: Path,
    feature_label: dict[str, str] | None = None,
    count_label: str = "利用数",
    count_suffix: str = "回",
) -> None:
    feature_label = feature_label or {}
    features   = [f for f in feature_order if f in df["feature"].unique()]
    companies  = sorted(df["company_name"].unique())
    all_months = sorted(df["usage_month"].unique())

    n_comp       = len(companies)
    n_months     = len(all_months)
    PLOT_W       = MARGIN_L + len(features) * COL_W + MARGIN_R
    per_h        = FIXED_PER_H
    total_data_h = n_comp * per_h + (n_comp - 1) * GAP_H
    total_h      = total_data_h + MARGIN_T + MARGIN_B

    fig = make_subplots(
        rows=n_comp, cols=1,
        vertical_spacing=GAP_H / total_data_h,
        row_heights=[n_months] * n_comp,
    )

    for ci, company in enumerate(companies):
        cdf = df[df["company_name"] == company]
        z, customdata = [], []
        for month in all_months:
            mdf = cdf[cdf["usage_month"] == month]
            z_row, cd_row = [], []
            for feat in features:
                row   = mdf[mdf["feature"] == feat]
                count = int(row["event_count"].iloc[0]) if len(row) > 0 else None
                score = _to_score(count, feat, thresholds)
                label = SCORE_LABEL[int(score)] if not np.isnan(score) else "—"
                z_row.append(score)
                cd_row.append([label, count if count is not None else 0, month[2:]])
            z.append(z_row)
            customdata.append(cd_row)

        fig.add_trace(go.Heatmap(
            z=z, x=features, y=all_months,
            customdata=customdata,
            colorscale=COLORSCALE, zmin=0, zmax=2,
            showscale=False,
            hovertemplate=(
                f"<b>{company}</b>  %{{customdata[2]}}<br>"
                "%{x}: <b>%{customdata[0]}</b><br>"
                f"{count_label}: %{{customdata[1]}}{count_suffix}<extra></extra>"
            ),
            xgap=6, ygap=0,
        ), row=ci + 1, col=1)

    # パネルごとのうっすらグレー背景
    for ci in range(n_comp):
        idx = ci + 1
        suf = "" if idx == 1 else str(idx)
        yax = fig.layout[f"yaxis{suf}"]
        xax = fig.layout[f"xaxis{suf}"]
        if yax.domain is None or xax.domain is None:
            continue
        fig.add_shape(
            type="rect", xref="paper", yref="paper",
            x0=xax.domain[0], x1=xax.domain[1],
            y0=yax.domain[0], y1=yax.domain[1],
            fillcolor="rgba(0,0,0,0.07)", line_width=0, layer="below",
        )

    fig.for_each_xaxis(lambda ax: ax.update(showticklabels=False, showgrid=False))

    tick_months = [m for i, m in enumerate(all_months) if i % 6 == 0]
    tick_labels = [m[2:] for m in tick_months]
    fig.for_each_yaxis(lambda ax: ax.update(
        showticklabels=True, side="right",
        tickvals=tick_months, ticktext=tick_labels,
        tickfont=dict(size=8), showgrid=False, autorange=True,
    ))

    fig.update_layout(
        title=dict(
            text=title,
            font=dict(size=14, family="Inter, Noto Sans JP, sans-serif",
                      color="#1a2035", weight=600),
            x=0.5,
        ),
        height=total_h, width=PLOT_W,
        paper_bgcolor="white", plot_bgcolor="white",
        font=dict(family="Inter, Noto Sans JP, sans-serif", size=10, color="#2c3e60"),
        margin=dict(t=MARGIN_T, b=MARGIN_B, l=MARGIN_L, r=MARGIN_R),
    )

    # スクロール位置 + 固定名前列の Y 座標を計算
    company_scroll  = {}
    company_page_y  = {}
    for ci, company in enumerate(companies):
        idx = ci + 1
        suf = "" if idx == 1 else str(idx)
        yax = fig.layout[f"yaxis{suf}"]
        if yax.domain:
            y_top    = MARGIN_T + (1 - yax.domain[1]) * total_data_h
            y_center = MARGIN_T + (1 - (yax.domain[0] + yax.domain[1]) / 2) * total_data_h
            company_scroll[company] = max(0, int(HEADER_H + y_top - 16))
            company_page_y[company] = y_center  # name-inner 自体が HEADER_H 分オフセット済み

    html = fig.to_html(include_plotlyjs="cdn", full_html=True)

    # ── Sticky ヘッダー (機能名) ──────────────────────────────────────────
    plot_area_w = PLOT_W - MARGIN_L - MARGIN_R
    col_w       = plot_area_w / len(features)
    label_items = ""
    for i, feat in enumerate(features):
        cx      = MARGIN_L + (i + 0.5) * col_w
        display = feature_label.get(feat, feat)
        label_items += (
            f'<div style="position:absolute;left:{cx:.1f}px;'
            f'transform:translateX(-50%);bottom:6px;width:{col_w:.0f}px;'
            f'text-align:center;line-height:1.3;font-size:10px;font-weight:500;'
            f'letter-spacing:0.01em;white-space:normal;word-break:break-all;'
            f'font-family:\'Inter\',\'Noto Sans JP\',sans-serif;color:#2c3e60;">'
            f"{display}</div>"
        )

    sticky_header = (
        '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
        '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600'
        '&family=Noto+Sans+JP:wght@300;400;500&display=swap" rel="stylesheet">\n'
        f'<div id="sticky-header" style="position:sticky;top:0;z-index:200;'
        f'background:white;border-bottom:1px solid rgba(0,0,0,0.08);'
        f'box-shadow:0 2px 12px rgba(0,0,0,0.06);'
        f'width:{PLOT_W}px;height:{HEADER_H}px;overflow:visible;flex-shrink:0;">'
        f'<div style="position:relative;width:100%;height:100%;">'
        f"{label_items}</div></div>"
    )

    # ── 左固定社名列 ──────────────────────────────────────────────────────
    name_items = ""
    for company in companies:
        py = company_page_y.get(company, 0)
        name_items += (
            f'<div style="position:absolute;top:{py:.1f}px;left:0;right:6px;'
            f'text-align:right;transform:translateY(-50%);'
            f'font-size:11px;font-weight:600;color:#1a2035;line-height:1.35;'
            f'font-family:\'Inter\',\'Noto Sans JP\',sans-serif;">'
            f'{_wrap_name(company)}</div>'
        )

    name_col = (
        f'<div id="name-col" style="position:fixed;left:0;top:0;width:{NAME_COL_W}px;'
        f'height:100vh;overflow:hidden;background:white;z-index:250;'
        f'box-shadow:2px 0 6px rgba(0,0,0,0.05);border-right:1px solid rgba(0,0,0,0.07);">'
        # ヘッダー高さと合わせた上部スペース
        f'<div style="height:{HEADER_H}px;background:white;'
        f'border-bottom:1px solid rgba(0,0,0,0.08);'
        f'box-shadow:0 2px 12px rgba(0,0,0,0.06);'
        f'display:flex;align-items:flex-end;justify-content:flex-end;'
        f'padding:0 8px 6px;box-sizing:border-box;">'
        f'<span style="font-size:9px;color:#8a9ab5;'
        f'font-family:\'Inter\',\'Noto Sans JP\',sans-serif;letter-spacing:0.04em;">'
        f'会社名</span></div>'
        # スクロール追従するコンテナ
        f'<div id="name-inner" style="position:absolute;left:0;right:0;top:{HEADER_H}px;">'
        f'{name_items}'
        f'</div>'
        f'</div>'
        f'<script>'
        f'(function(){{'
        f'  var inner=document.getElementById("name-inner");'
        f'  window.addEventListener("scroll",function(){{'
        f'    inner.style.top=({HEADER_H}-window.scrollY)+"px";'
        f'  }},{{passive:true}});'
        f'}})();'
        f'</script>'
    )

    # ── 顧客検索ウィジェット ──────────────────────────────────────────────
    options_html   = "\n".join(
        f'<option value="{i}">{c}</option>' for i, c in enumerate(companies)
    )
    companies_json = json.dumps(companies, ensure_ascii=False)
    scroll_json    = json.dumps(company_scroll, ensure_ascii=False)

    widget = f"""
<div id="company-selector" style="
  position:fixed;bottom:24px;right:24px;z-index:9999;
  background:rgba(255,255,255,0.96);
  border:1px solid rgba(0,0,0,0.08);border-radius:14px;
  padding:14px 16px;
  box-shadow:0 8px 32px rgba(0,0,0,0.12),0 2px 8px rgba(0,0,0,0.06);
  width:220px;font-family:'Inter','Noto Sans JP',sans-serif;font-size:13px;
  backdrop-filter:blur(8px);">
  <div style="font-weight:600;color:#1a2035;margin-bottom:8px;font-size:12px;letter-spacing:0.04em;">🔍 顧客を選択</div>
  <input type="text" id="cs-search" placeholder="会社名を検索…"
    style="width:100%;padding:7px 10px;box-sizing:border-box;
           border:1px solid rgba(0,0,0,0.12);border-radius:8px;
           font-size:12px;margin-bottom:6px;outline:none;
           font-family:'Inter','Noto Sans JP',sans-serif;
           background:#f8fafc;color:#1a2035;">
  <select id="cs-list" size="7"
    style="width:100%;border:1px solid rgba(0,0,0,0.12);border-radius:8px;
           font-size:11px;padding:4px;background:#f8fafc;color:#1a2035;
           font-family:'Inter','Noto Sans JP',sans-serif;">
    {options_html}
  </select>
</div>
<script>
(function(){{
  const companies={companies_json};
  const scrollPos={scroll_json};
  const search=document.getElementById('cs-search');
  const list=document.getElementById('cs-list');
  search.addEventListener('input',function(){{
    const q=this.value.toLowerCase();
    Array.from(list.options).forEach(opt=>{{opt.hidden=!opt.text.toLowerCase().includes(q);}});
  }});
  list.addEventListener('change',function(){{
    const ci=parseInt(this.value);
    if(ci<0)return;
    const pos=scrollPos[companies[ci]];
    if(pos!==undefined)window.scrollTo({{top:pos,behavior:'smooth'}});
  }});
}})();
</script>"""

    html = html.replace("<body>", "<body>\n" + sticky_header)
    html = html.replace("</body>", name_col + widget + "\n</body>")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"出力: {out_path}  ({n_comp}社 / {n_months}ヶ月 / {total_h}px)")
