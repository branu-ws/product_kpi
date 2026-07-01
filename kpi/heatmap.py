"""プロダクト共通の 機能別月次ヒートマップ生成ロジック。

build_heatmap(df, thresholds, feature_order, feature_label, title, out_path)
  df: usage_month / company_name / feature / event_count の DataFrame
"""

import json
import logging
from pathlib import Path
from string import Template

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from kpi.config import FeatureThreshold

_TEMPLATES = Path(__file__).parent / "templates"


def _tmpl(name: str) -> Template:
    return Template((_TEMPLATES / name).read_text(encoding="utf-8"))


log = logging.getLogger(__name__)

SCORE_LABEL = {0: "bad", 1: "normal", 2: "good"}

COLORSCALE = [
    [0.0, "#bfdbfe"],  # bad   : スカイブルー
    [0.5, "#3b82f6"],  # normal: ビビッドブルー
    [1.0, "#1e3a8a"],  # good  : ロイヤルブルー
]

FIXED_PER_H = 57  # px / company block
COL_W = 90  # px / feature column (124→90 で幅を縮小)
GAP_H = 6
MARGIN_L = 150  # Plotly 内部の左余白 (固定名前列が被さる)
NAME_COL_W = 148  # 左固定社名列の幅 (px)
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
            return kk + "<br>" + name[len(kk) :]
        if name.endswith(kk) and len(name) > len(kk):
            return name[: -len(kk)] + "<br>" + kk
    mid = len(name) // 2
    return name[:mid] + "<br>" + name[mid:]


def _to_score(
    count: float | None,
    feature: str,
    thresholds: dict[str, FeatureThreshold],
) -> float:
    # None (その月のデータなし) と 0 (利用ゼロ) は両方 bad=0.0 で統一
    if count is None:
        return 0.0
    t = thresholds.get(feature)
    if t is None:
        return 0.0
    if count >= t.good_min:
        return 2.0
    if count >= t.normal_min:
        return 1.0
    return 0.0


def build_heatmap(
    df: pd.DataFrame,
    thresholds: dict[str, FeatureThreshold],
    feature_order: list[str],
    title: str,
    out_path: Path,
    feature_label: dict[str, str] | None = None,
    count_label: str = "利用数",
    count_suffix: str = "回",
) -> None:
    feature_label = feature_label or {}
    features = [f for f in feature_order if f in df["feature"].unique()]
    companies = sorted(df["company_name"].unique())
    all_months = sorted(df["usage_month"].unique())

    n_comp = len(companies)
    n_months = len(all_months)
    plot_w = MARGIN_L + len(features) * COL_W + MARGIN_R
    per_h = FIXED_PER_H
    total_data_h = n_comp * per_h + (n_comp - 1) * GAP_H
    total_h = total_data_h + MARGIN_T + MARGIN_B

    fig = make_subplots(
        rows=n_comp,
        cols=1,
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
                row = mdf[mdf["feature"] == feat]
                count = int(row["event_count"].iloc[0]) if len(row) > 0 else None
                score = _to_score(count, feat, thresholds)
                label = SCORE_LABEL[int(score)] if not np.isnan(score) else "—"
                z_row.append(score)
                cd_row.append([label, count if count is not None else 0, month[2:]])
            z.append(z_row)
            customdata.append(cd_row)

        fig.add_trace(
            go.Heatmap(
                z=z,
                x=features,
                y=all_months,
                customdata=customdata,
                colorscale=COLORSCALE,
                zmin=0,
                zmax=2,
                showscale=False,
                hovertemplate=(
                    f"<b>{company}</b>  %{{customdata[2]}}<br>"
                    "%{x}: <b>%{customdata[0]}</b><br>"
                    f"{count_label}: %{{customdata[1]}}{count_suffix}<extra></extra>"
                ),
                xgap=6,
                ygap=0,
            ),
            row=ci + 1,
            col=1,
        )

    # パネルごとのうっすらグレー背景
    for ci in range(n_comp):
        idx = ci + 1
        suf = "" if idx == 1 else str(idx)
        yax = fig.layout[f"yaxis{suf}"]
        xax = fig.layout[f"xaxis{suf}"]
        if yax.domain is None or xax.domain is None:
            continue
        fig.add_shape(
            type="rect",
            xref="paper",
            yref="paper",
            x0=xax.domain[0],
            x1=xax.domain[1],
            y0=yax.domain[0],
            y1=yax.domain[1],
            fillcolor="rgba(0,0,0,0.07)",
            line_width=0,
            layer="below",
        )

    fig.for_each_xaxis(lambda ax: ax.update(showticklabels=False, showgrid=False))

    tick_months = [m for i, m in enumerate(all_months) if i % 6 == 0]
    tick_labels = [m[2:] for m in tick_months]
    fig.for_each_yaxis(
        lambda ax: ax.update(
            showticklabels=True,
            side="right",
            tickvals=tick_months,
            ticktext=tick_labels,
            tickfont={"size": 8},
            showgrid=False,
            autorange=True,
        )
    )

    fig.update_layout(
        title={
            "text": title,
            "font": {
                "size": 14,
                "family": "Inter, Noto Sans JP, sans-serif",
                "color": "#1a2035",
                "weight": 600,
            },
            "x": 0.5,
        },
        height=total_h,
        width=plot_w,
        paper_bgcolor="white",
        plot_bgcolor="white",
        font={
            "family": "Inter, Noto Sans JP, sans-serif",
            "size": 10,
            "color": "#2c3e60",
        },
        margin={"t": MARGIN_T, "b": MARGIN_B, "l": MARGIN_L, "r": MARGIN_R},
    )

    # スクロール位置 + 固定名前列の Y 座標を計算
    company_scroll = {}
    company_page_y = {}
    for ci, company in enumerate(companies):
        idx = ci + 1
        suf = "" if idx == 1 else str(idx)
        yax = fig.layout[f"yaxis{suf}"]
        if yax.domain:
            y_top = MARGIN_T + (1 - yax.domain[1]) * total_data_h
            domain_mid = (yax.domain[0] + yax.domain[1]) / 2
            y_center = MARGIN_T + (1 - domain_mid) * total_data_h
            company_scroll[company] = max(0, int(HEADER_H + y_top - 16))
            company_page_y[company] = y_center  # HEADER_H 分オフセット済み

    html = fig.to_html(include_plotlyjs="cdn", full_html=True)

    # ── Sticky ヘッダー (機能名) ──────────────────────────────────────────
    plot_area_w = plot_w - MARGIN_L - MARGIN_R
    col_w = plot_area_w / len(features)
    label_items = ""
    for i, feat in enumerate(features):
        cx = MARGIN_L + (i + 0.5) * col_w
        display = feature_label.get(feat, feat)
        label_items += (
            f'<div style="position:absolute;left:{cx:.1f}px;'
            f"transform:translateX(-50%);bottom:6px;width:{col_w:.0f}px;"
            f"text-align:center;line-height:1.3;font-size:10px;font-weight:500;"
            f"letter-spacing:0.01em;white-space:normal;word-break:break-all;"
            f"font-family:'Inter','Noto Sans JP',sans-serif;color:#2c3e60;>"
            f"{display}</div>"
        )

    sticky_header = _tmpl("heatmap_sticky_header.html").substitute(
        plot_w=plot_w,
        header_h=HEADER_H,
        label_items=label_items,
    )

    # ── 左固定社名列 ──────────────────────────────────────────────────────
    name_items = ""
    for company in companies:
        py = company_page_y.get(company, 0)
        name_items += (
            f'<div style="position:absolute;top:{py:.1f}px;left:0;right:6px;'
            f"text-align:right;transform:translateY(-50%);"
            f"font-size:11px;font-weight:600;color:#1a2035;line-height:1.35;"
            f"font-family:'Inter','Noto Sans JP',sans-serif;>"
            f"{_wrap_name(company)}</div>"
        )

    name_col = _tmpl("heatmap_name_col.html").substitute(
        name_col_w=NAME_COL_W,
        header_h=HEADER_H,
        name_items=name_items,
    )

    # ── 顧客検索ウィジェット ──────────────────────────────────────────────
    options_html = "\n".join(
        f'<option value="{i}">{c}</option>' for i, c in enumerate(companies)
    )
    companies_json = json.dumps(companies, ensure_ascii=False)
    scroll_json = json.dumps(company_scroll, ensure_ascii=False)

    widget = _tmpl("heatmap_widget.html").substitute(
        options_html=options_html,
        companies_json=companies_json,
        scroll_json=scroll_json,
    )

    html = html.replace("<body>", "<body>\n" + sticky_header)
    html = html.replace("</body>", name_col + widget + "\n</body>")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    log.info("出力: %s  (%d社 / %dヶ月 / %dpx)", out_path, n_comp, n_months, total_h)
