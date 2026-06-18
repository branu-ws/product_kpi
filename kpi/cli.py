"""CLI エントリーポイント。pyproject.toml の [project.scripts] から呼ばれる。"""

import logging
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import duckdb
import httpx
import pandas as pd
from dotenv import load_dotenv
from tqdm import tqdm

from kpi import (
    companies,
    company_loyalty,
    contracts,
    customer_lifecycle,
    db,
    feature_health,
    keiei_user_history,
    notion_sync,
    users,
    work_process_id_generator,
    work_user_history,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

_OUTPUT_DIR = Path(__file__).parent.parent / "output" / "csv"
_COLLECTIONS_DIR = Path(__file__).parent.parent / "collections"
_BQ_DIR = _COLLECTIONS_DIR / "bigquery"    # bigquery/{dataset}/*.sql → BigQuery
_NOTION_DIR = _COLLECTIONS_DIR / "notion"  # notion/*.sql → kpi-sync


def update_duckdb() -> None:
    """Redash からデータを取得して DuckDB キャッシュを更新し、
    collections/*.sql の集計結果を BigQuery に保存する。
    """
    _bar_fmt = "{l_bar}{bar}| {elapsed}"

    with httpx.Client() as client:
        fetch_tasks: list[tuple[str, Any]] = [
            ("work_user_history        ", lambda: work_user_history.fetch(client)),
            (
                "work_process_id_generator",
                lambda: work_process_id_generator.fetch(client),
            ),
            ("companies                ", lambda: companies.fetch(client)),
            ("contracts                ", lambda: contracts.fetch(client)),
            ("users                    ", lambda: users.fetch(client)),
            ("keiei_user_history       ", lambda: keiei_user_history.fetch(client)),
        ]
        fetched: dict[str, Any] = {}
        with tqdm(fetch_tasks, bar_format=_bar_fmt) as pbar:
            for name, fn in pbar:
                pbar.set_description(f"Redash  {name}")
                fetched[name.strip()] = fn()

    history_df = fetched["work_user_history"]
    projects_df = fetched["work_process_id_generator"]
    companies_df = fetched["companies"]
    contracts_df = fetched["contracts"]
    users_df = fetched["users"]
    keiei_history_df = fetched["keiei_user_history"]

    conn = duckdb.connect()
    conn.register("work_user_history", history_df)
    conn.register("work_process_id_generator", projects_df)
    conn.register("companies", companies_df)
    conn.register("contracts", contracts_df)
    conn.register("users", users_df)
    conn.register("keiei_user_history", keiei_history_df)

    with tqdm(total=5, bar_format=_bar_fmt) as pbar:
        pbar.set_description("KPI計算  customer_lifecycle  ")
        lifecycle_df = customer_lifecycle.build(conn)
        conn.register("customer_lifecycle", lifecycle_df)
        pbar.update(1)

        pbar.set_description("KPI計算  feature_health      ")
        health_df = feature_health.build(conn)
        conn.register("feature_health", health_df)
        pbar.update(1)

        pbar.set_description("KPI計算  company_loyalty     ")
        loyalty_df = company_loyalty.build(conn)
        conn.register("company_loyalty", loyalty_df)
        pbar.update(1)

        pbar.set_description("KPI計算  keiei_feature_health")
        keiei_health_df = feature_health.build_keiei(conn)
        conn.register("keiei_feature_health", keiei_health_df)
        pbar.update(1)

        pbar.set_description("KPI計算  keiei_company_loyalty")
        keiei_loyalty_df = company_loyalty.build_keiei(conn)
        conn.register("keiei_company_loyalty", keiei_loyalty_df)
        pbar.update(1)

    views: dict[str, dict[str, Any]] = defaultdict(dict)
    sql_files = sorted(_BQ_DIR.rglob("*.sql"))
    with tqdm(sql_files, bar_format=_bar_fmt) as pbar:
        for sql_file in pbar:
            rel = sql_file.relative_to(_BQ_DIR)
            parts = rel.with_suffix("").parts
            if len(parts) < 2:
                log.warning("skip %s: place under bigquery/{dataset}/", rel)
                continue
            dataset = parts[0]
            table_name = "_".join(parts[1:])
            pbar.set_description(f"SQL実行  {dataset}.{table_name:<40}")
            try:
                df = conn.sql(sql_file.read_text()).df()
                if "usage_month" in df.columns:
                    df["usage_month"] = pd.to_datetime(
                        df["usage_month"] + "-01"
                    ).dt.date
                views[dataset][table_name] = df
            except Exception as e:
                log.warning("警告: %s スキップ (%s)", rel, e)

    conn.close()

    db.save(
        work_user_history=history_df,
        work_process_id_generator=projects_df,
        companies=companies_df,
        contracts=contracts_df,
        users=users_df,
        keiei_user_history=keiei_history_df,
        customer_lifecycle=lifecycle_df,
        feature_health=health_df,
        company_loyalty=loyalty_df,
        keiei_feature_health=keiei_health_df,
        keiei_company_loyalty=keiei_loyalty_df,
    )

    if views:
        db.save_views(dict(views))

    log.info("完了")


def sync_notion() -> None:
    """config.yml の notion.outputs を Notion DB に同期する。"""
    load_dotenv()
    conn = db.load()
    notion_sync.sync_all(conn)
    conn.close()


def export_csv() -> None:
    """SQL ファイルを実行して CSV に出力する。

    使い方:
        uv run kpi-export collections/output1_loyalty_distribution.sql
        uv run kpi-export collections/*.sql
    """
    args = sys.argv[1:]
    if not args:
        log.error("使い方: kpi-export <sql_file> [<sql_file2> ...]")
        sys.exit(1)

    sql_files = [Path(a) for a in args]
    conn = db.load()

    for sql_file in sql_files:
        rel = (
            sql_file.relative_to(_COLLECTIONS_DIR)
            if sql_file.is_relative_to(_COLLECTIONS_DIR)
            else Path(sql_file.name)
        )
        output_path = _OUTPUT_DIR / rel.with_suffix(".csv")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        sql = sql_file.read_text(encoding="utf-8")
        result = conn.sql(sql).df()
        print(f"\n=== {rel} ===")  # noqa: T201
        print(result.to_string())  # noqa: T201
        result.to_csv(output_path, index=False, encoding="utf-8-sig")
        log.info("-> %s に保存しました", output_path)

    conn.close()
