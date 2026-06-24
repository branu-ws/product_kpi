"""config.yml の notion.outputs に定義された SQL → Notion DB への同期。

環境変数:
  NOTION_API_KEY : Notion インテグレーション トークン (秘密情報 → .env)

接続先 DB/DS ID は config.yml で管理 (secrets ではないのでリポジトリに含める)。

time_col:
  "month" (デフォルト) → YYYY-MM 形式。_MONTH_RE で列を識別。
  "week"              → MM-WN 形式 (例: 06-W1)。_WEEK_RE で列を識別。
"""

import logging
import os
import re
from pathlib import Path
from typing import Any, cast

import duckdb
import pandas as pd
from notion_client import Client

from kpi.config import ChartEntry, GcpSettings, load_notion_config

log = logging.getLogger(__name__)

_ROOT = Path(__file__).parent.parent
_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
_WEEK_RE = re.compile(r"^\d{2}-W\d+$")
_COMBINED_RE = re.compile(r"^\d{4}-\d{2}(-W\d+)?$")


def sync_charts(charts: list[ChartEntry], gcp: GcpSettings) -> None:
    """notion.charts の各グラフを Notion ページに embed ブロックとして注入する (冪等)。

    既に同じ URL の embed ブロックが存在する場合はスキップする。
    """
    if not charts or not gcp.charts_bucket:
        return

    notion: Client = Client(auth=os.environ["NOTION_API_KEY"])

    for chart in charts:
        url = f"https://storage.googleapis.com/{gcp.charts_bucket}/{Path(chart.html).name}"
        if _embed_exists(notion, chart.page_id, url):
            log.info("[chart:%s] embed ブロック既存のためスキップ", chart.name)
            continue

        notion.blocks.children.append(
            block_id=chart.page_id,
            children=[{"object": "block", "type": "embed", "embed": {"url": url}}],
        )
        log.info("[chart:%s] embed ブロック注入完了", chart.name)


def _embed_exists(notion: Client, page_id: str, url: str) -> bool:
    result = cast(
        dict[str, Any],
        notion.blocks.children.list(block_id=page_id),
    )
    return any(
        b.get("type") == "embed" and b.get("embed", {}).get("url") == url
        for b in result.get("results", [])
    )


def sync_all(conn: duckdb.DuckDBPyConnection) -> None:
    """config.yml の notion.outputs を全件同期する。"""
    cfg = load_notion_config()
    notion: Client = Client(auth=os.environ["NOTION_API_KEY"])
    months_to_show: int = cfg.months_to_show

    for output in cfg.outputs:
        name: str = output.name
        sql_path: Path = _ROOT / output.sql
        db_id: str = output.db_id
        ds_id: str = output.ds_id
        time_col: str = output.time_col

        log.info("[%s] 同期開始...", name)
        sql = sql_path.read_text()
        df: pd.DataFrame = conn.sql(sql).df()
        _sync_output(notion, df, db_id, ds_id, months_to_show, time_col)
        log.info("[%s] 完了", name)


def _sync_output(
    notion: Client,
    df: pd.DataFrame,
    db_id: str,
    ds_id: str,
    months_to_show: int,
    time_col: str = "month",
) -> None:
    if time_col == "week":
        period_re = _WEEK_RE
        time_col_name = "week"
    elif time_col == "combined":
        period_re = _COMBINED_RE
        time_col_name = "month"  # combined SQL outputs a "month" column
    else:
        period_re = _MONTH_RE
        time_col_name = "month"

    df = df.sort_values(time_col_name).tail(months_to_show)
    periods: list[str] = [str(p) for p in df[time_col_name].tolist()]
    metric_cols = [c for c in df.columns if c != time_col_name]
    pivot = df.set_index(time_col_name)[metric_cols].T

    log.info("  既存ページをアーカイブ中...")
    _archive_all(notion, ds_id)

    log.info("  期間カラムをスキーマに同期中...")
    title_prop = _sync_period_columns(notion, ds_id, periods, period_re)

    log.info("  %d 行を書き込み中...", len(metric_cols))
    for metric in reversed(metric_cols):
        row = pivot.loc[metric]
        properties: dict[str, object] = {
            title_prop: {"title": [{"text": {"content": metric}}]},
            **{period: {"number": int(row[period])} for period in periods},  # type: ignore[arg-type]
        }
        notion.pages.create(parent={"database_id": db_id}, properties=properties)
        log.debug("    作成: %s", metric)


def _archive_all(notion: Client, ds_id: str) -> None:
    has_more = True
    cursor: str | None = None
    while has_more:
        kwargs: dict[str, object] = {"page_size": 100}
        if cursor:
            kwargs["start_cursor"] = cursor
        result = cast(dict[str, Any], notion.data_sources.query(ds_id, **kwargs))
        for page in result["results"]:
            notion.pages.update(page_id=page["id"], in_trash=True)
        has_more = bool(result.get("has_more", False))
        cursor = result.get("next_cursor")


def _sync_period_columns(
    notion: Client,
    ds_id: str,
    periods: list[str],
    period_re: re.Pattern[str],
) -> str:
    ds_info = cast(dict[str, Any], notion.data_sources.retrieve(ds_id))
    props: dict[str, Any] = cast(dict[str, Any], ds_info.get("properties", {}))
    existing: set[str] = {k for k in props if period_re.match(k)}
    target = set(periods)

    def _is_title(v: object) -> bool:
        return isinstance(v, dict) and v.get("type") == "title"

    title_prop = next((k for k, v in props.items() if _is_title(v)), "指標")

    updates: dict[str, object] = {}
    for p in existing - target:
        updates[p] = None
    for p in target - existing:
        updates[p] = {"number": {}}
    if updates:
        notion.data_sources.update(ds_id, properties=updates)
    return title_prop
