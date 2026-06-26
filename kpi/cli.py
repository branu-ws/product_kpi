"""CLI エントリーポイント。pyproject.toml の [project.scripts] から呼ばれる。"""

import logging
import os
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
    charts,
    companies,
    company_loyalty,
    contracts,
    cross_product,
    customer_lifecycle,
    db,
    feature_health,
    keiei_user_history,
    notion_sync,
    sf_customers,
    single_product,
    users,
    work_process_id_generator,
    work_user_history,
)
from kpi import (
    config as kpi_config,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

_OUTPUT_DIR = Path(__file__).parent.parent / "output" / "csv"
_COLLECTIONS_DIR = Path(__file__).parent.parent / "collections"
_BQ_DIR = _COLLECTIONS_DIR / "bigquery"  # bigquery/{dataset}/*.sql → BigQuery
_NOTION_DIR = _COLLECTIONS_DIR / "notion"  # notion/*.sql → kpi-sync


def _fetch_raw(
    client: httpx.Client, bar_fmt: str
) -> dict[str, pd.DataFrame]:
    """Redash + SF から全 raw データを取得する。companies の SF 社名補完を含む。"""
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
        ("sf_customers             ", lambda: sf_customers.fetch(client)),
        (
            "sf_all_plus_customers    ",
            lambda: sf_customers.fetch_plus_historical(client),
        ),
        ("mini_sf_customers        ", lambda: sf_customers.fetch_mini(client)),
        ("ai_user_history          ", lambda: work_user_history.fetch_ai(client)),
        ("contents_user_history    ", lambda: work_user_history.fetch_contents(client)),
        ("daily_report_photo       ", lambda: work_user_history.fetch_daily_report_attrs(client)),
        ("report_attrs             ", lambda: work_user_history.fetch_report_attrs(client)),
    ]
    fetched: dict[str, pd.DataFrame] = {}
    with tqdm(fetch_tasks, bar_format=bar_fmt) as pbar:
        for name, fn in pbar:
            pbar.set_description(f"Redash  {name}")
            fetched[name.strip()] = fn()

    # DS1 にない会社 (keiei-only・解約済み含む) の社名を SF 名で補完
    # sf_all_plus_customers で解約済み顧客の社名もカバーする
    sf_names = (
        fetched["sf_all_plus_customers"][["company_uuid", "sf_company_name"]]
        .rename(columns={"sf_company_name": "company_name"})
    )
    fetched["companies"] = (
        pd.concat([fetched["companies"], sf_names], ignore_index=True)
        .drop_duplicates(subset="company_uuid", keep="first")
        .reset_index(drop=True)
    )

    return fetched


def _build_kpi(
    raw: dict[str, pd.DataFrame], bar_fmt: str
) -> tuple[dict[str, pd.DataFrame], dict[str, dict[str, Any]]]:
    """raw DataFrames から全 KPI テーブルと BigQuery ビューを計算する。"""
    conn = duckdb.connect()
    for name, df in raw.items():
        conn.register(name, df)

    built: dict[str, pd.DataFrame] = {}

    with tqdm(total=5, bar_format=bar_fmt) as pbar:
        pbar.set_description("KPI計算  customer_lifecycle      ")
        built["customer_lifecycle"] = lifecycle_df = customer_lifecycle.build(conn)
        conn.register("customer_lifecycle", lifecycle_df)
        pbar.update(1)

        pbar.set_description("KPI計算  feature_health          ")
        built["feature_health"] = health_df = feature_health.build(conn)
        conn.register("feature_health", health_df)
        pbar.update(1)

        pbar.set_description("KPI計算  keiei_feature_health    ")
        built["keiei_feature_health"] = keiei_health_df = feature_health.build_keiei(
            conn
        )
        conn.register("keiei_feature_health", keiei_health_df)
        pbar.update(1)

        pbar.set_description("KPI計算  mini_customer_lifecycle ")
        built["mini_customer_lifecycle"] = mini_lifecycle_df = (
            customer_lifecycle.build_mini(conn)
        )
        conn.register("mini_customer_lifecycle", mini_lifecycle_df)
        pbar.update(1)

        pbar.set_description("KPI計算  mini_feature_health     ")
        built["mini_feature_health"] = mini_health_df = feature_health.build_work_mini(
            conn
        )
        conn.register("mini_feature_health", mini_health_df)
        pbar.update(1)

    with tqdm(total=7, bar_format=bar_fmt) as pbar:
        pbar.set_description("KPI計算  cross_product           ")
        cp_monthly_df, cp_weekly_df = cross_product.build(conn)
        built["cross_product_monthly_company"] = cp_monthly_df
        built["cross_product_company_weekly"] = cp_weekly_df
        conn.register("cross_product_monthly_company", cp_monthly_df)
        conn.register("cross_product_company_weekly", cp_weekly_df)
        pbar.update(1)

        pbar.set_description("KPI計算  work_single_product     ")
        sp_work_monthly_df, sp_work_weekly_df = single_product.build_work(conn)
        built["work_monthly_company"] = sp_work_monthly_df
        built["work_company_weekly"] = sp_work_weekly_df
        conn.register("work_monthly_company", sp_work_monthly_df)
        conn.register("work_company_weekly", sp_work_weekly_df)
        pbar.update(1)

        pbar.set_description("KPI計算  keiei_single_product    ")
        sp_keiei_monthly_df, sp_keiei_weekly_df = single_product.build_keiei(conn)
        built["keiei_monthly_company"] = sp_keiei_monthly_df
        built["keiei_company_weekly"] = sp_keiei_weekly_df
        conn.register("keiei_monthly_company", sp_keiei_monthly_df)
        conn.register("keiei_company_weekly", sp_keiei_weekly_df)
        pbar.update(1)

        pbar.set_description("KPI計算  mini_work_single_product")
        mini_work_monthly_df, mini_work_weekly_df = single_product.build_work_mini(conn)
        built["mini_work_monthly_company"] = mini_work_monthly_df
        built["mini_work_company_weekly"] = mini_work_weekly_df
        conn.register("mini_work_monthly_company", mini_work_monthly_df)
        conn.register("mini_work_company_weekly", mini_work_weekly_df)
        pbar.update(1)

        pbar.set_description("KPI計算  company_loyalty         ")
        built["company_loyalty"] = loyalty_df = company_loyalty.build(conn)
        conn.register("company_loyalty", loyalty_df)
        pbar.update(1)

        pbar.set_description("KPI計算  keiei_company_loyalty   ")
        built["keiei_company_loyalty"] = keiei_loyalty_df = (
            company_loyalty.build_keiei(conn)
        )
        conn.register("keiei_company_loyalty", keiei_loyalty_df)
        pbar.update(1)

        pbar.set_description("KPI計算  mini_company_loyalty    ")
        built["mini_company_loyalty"] = mini_loyalty_df = company_loyalty.build_mini(
            conn
        )
        conn.register("mini_company_loyalty", mini_loyalty_df)
        pbar.update(1)

    views: dict[str, dict[str, Any]] = defaultdict(dict)
    sql_files = sorted(_BQ_DIR.rglob("*.sql"))
    with tqdm(sql_files, bar_format=bar_fmt) as pbar:
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
                views[dataset][table_name] = df
            except Exception as e:
                log.warning("警告: %s スキップ (%s)", rel, e)

    conn.close()
    return built, dict(views)


def update_duckdb() -> None:
    """Redash からデータを取得して DuckDB キャッシュを更新し、
    collections/*.sql の集計結果を BigQuery に保存する。
    """
    load_dotenv()
    bar_fmt = "{l_bar}{bar}| {elapsed}"

    with httpx.Client() as client:
        raw = _fetch_raw(client, bar_fmt)

    built, views = _build_kpi(raw, bar_fmt)

    db.save(**raw, **built)
    if views:
        db.save_views(views)

    chart_list = kpi_config.load_notion_charts()
    if chart_list:
        gcp = kpi_config.load_gcp()
        charts.generate_and_upload(chart_list, gcp)

    log.info("完了")


def bq_update() -> None:
    """kpi-update + BigQuery 書き込み。GCP 設定は config.yml から読む。"""
    gcp = kpi_config.load_gcp()
    os.environ["USE_BIGQUERY"] = "1"
    os.environ.setdefault("GCP_PROJECT_ID", gcp.project_id)
    os.environ.setdefault("BQ_DATASET", gcp.dataset)
    update_duckdb()


def sync_notion() -> None:
    """config.yml の notion.outputs を Notion DB に同期し、embed ブロックを注入する。"""
    load_dotenv()
    conn = db.load()
    notion_sync.sync_all(conn)
    conn.close()
    gcp = kpi_config.load_gcp()
    notion_sync.sync_charts(kpi_config.load_notion_charts(), gcp)


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
