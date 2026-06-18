"""config.yml の notion.outputs に定義された SQL → Notion DB への同期。

環境変数:
  NOTION_API_KEY : Notion インテグレーション トークン (秘密情報 → .env)

接続先 DB/DS ID は config.yml で管理 (secrets ではないのでリポジトリに含める)。
"""

import logging
import os
import re
from pathlib import Path
from typing import Any, cast

import duckdb
import pandas as pd
import yaml  # type: ignore[import-untyped]
from notion_client import Client

log = logging.getLogger(__name__)

_ROOT = Path(__file__).parent.parent
_CONFIG_PATH = _ROOT / "config.yml"
_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")

_NUMERIC_COLS = [
    "ファン_good",
    "ファン_normal",
    "ファン_bad",
    "自走_good",
    "自走_normal",
    "自走_bad",
    "オンボ中_good",
    "オンボ中_normal",
    "オンボ中_bad",
    "離反気味_good",
    "離反気味_normal",
    "離反気味_bad",
]


def sync_all(conn: duckdb.DuckDBPyConnection) -> None:
    """config.yml の notion.outputs を全件同期する。"""
    with _CONFIG_PATH.open() as f:
        cfg = yaml.safe_load(f)

    notion: Client = Client(auth=os.environ["NOTION_API_KEY"])
    months_to_show: int = cfg["notion"].get("months_to_show", 18)

    for output in cfg["notion"]["outputs"]:
        name: str = output["name"]
        sql_path: Path = _ROOT / output["sql"]
        db_id: str = output["db_id"]
        ds_id: str = output["ds_id"]

        log.info("[%s] 同期開始...", name)
        sql = sql_path.read_text()
        df: pd.DataFrame = conn.sql(sql).df()
        _sync_output(notion, conn, df, db_id, ds_id, months_to_show)
        log.info("[%s] 完了", name)


def _sync_output(
    notion: Client,
    conn: duckdb.DuckDBPyConnection,
    df: pd.DataFrame,
    db_id: str,
    ds_id: str,
    months_to_show: int,
) -> None:
    df = df.sort_values("usage_month").tail(months_to_show)
    months: list[str] = [str(m) for m in df["usage_month"].tolist()]
    pivot = df.set_index("usage_month")[_NUMERIC_COLS].T

    log.info("  既存ページをアーカイブ中...")
    _archive_all(notion, ds_id)

    log.info("  月カラムをスキーマに同期中...")
    _sync_month_columns(notion, ds_id, months)

    log.info("  %d 行を書き込み中...", len(_NUMERIC_COLS))
    for metric in _NUMERIC_COLS:
        row = pivot.loc[metric]
        properties: dict[str, object] = {
            "指標": {"title": [{"text": {"content": metric}}]},
            **{month: {"number": int(row[month])} for month in months},  # type: ignore[arg-type]
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


def _sync_month_columns(notion: Client, ds_id: str, months: list[str]) -> None:
    ds_info = cast(dict[str, Any], notion.data_sources.retrieve(ds_id))
    props: dict[str, object] = ds_info.get("properties", {})
    existing: set[str] = {k for k in props if _MONTH_RE.match(k)}
    target = set(months)

    updates: dict[str, object] = {}
    for m in existing - target:
        updates[m] = None
    for m in target - existing:
        updates[m] = {"number": {}}
    if updates:
        notion.data_sources.update(ds_id, properties=updates)
