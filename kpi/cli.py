"""CLI エントリーポイント。pyproject.toml の [project.scripts] から呼ばれる。"""

import sys
from pathlib import Path
from typing import Any

import duckdb
import httpx
from dotenv import load_dotenv

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

_OUTPUT_DIR = Path(__file__).parent.parent / "output" / "csv"
_COLLECTIONS_DIR = Path(__file__).parent.parent / "collections"


def update_duckdb() -> None:
    """Redash からデータを取得して DuckDB キャッシュを更新し、
    collections/*.sql の集計結果を BigQuery に保存する。
    """
    print("Redash からデータを取得中...")
    with httpx.Client() as client:
        history_df = work_user_history.fetch(client)
        projects_df = work_process_id_generator.fetch(client)
        companies_df = companies.fetch(client)
        contracts_df = contracts.fetch(client)
        users_df = users.fetch(client)
        keiei_history_df = keiei_user_history.fetch(client)

    print("KPI 指標を計算中...")
    conn = duckdb.connect()
    conn.register("work_user_history", history_df)
    conn.register("work_process_id_generator", projects_df)
    conn.register("companies", companies_df)
    conn.register("contracts", contracts_df)
    conn.register("users", users_df)
    conn.register("keiei_user_history", keiei_history_df)

    lifecycle_df = customer_lifecycle.build(conn)
    conn.register("customer_lifecycle", lifecycle_df)

    health_df = feature_health.build(conn)
    conn.register("feature_health", health_df)
    loyalty_df = company_loyalty.build(conn)
    conn.register("company_loyalty", loyalty_df)

    keiei_health_df = feature_health.build_keiei(conn)
    conn.register("keiei_feature_health", keiei_health_df)
    keiei_loyalty_df = company_loyalty.build_keiei(conn)
    conn.register("keiei_company_loyalty", keiei_loyalty_df)

    print("collections/**/*.sql を BigQuery 用に集計中...")
    views: dict[str, Any] = {}
    for sql_file in sorted(_COLLECTIONS_DIR.rglob("*.sql")):
        rel = sql_file.relative_to(_COLLECTIONS_DIR)
        table_name = "_".join(rel.with_suffix("").parts)
        try:
            views[table_name] = conn.sql(sql_file.read_text()).df()
            print(f"  {rel} → {table_name}")
        except Exception as e:
            print(f"  警告: {rel} スキップ ({e})", file=sys.stderr)

    conn.close()

    print("DuckDB に保存中...")
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
        print("BigQuery に集計結果を保存中...")
        db.save_views(**views)

    print("完了")


def sync_notion() -> None:
    """config.yml の notion.outputs を Notion DB に同期する。"""
    load_dotenv()
    print("DuckDB に接続中...")
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
        print("使い方: kpi-export <sql_file> [<sql_file2> ...]", file=sys.stderr)
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
        print(f"\n=== {rel} ===")
        print(result.to_string())
        result.to_csv(output_path, index=False, encoding="utf-8-sig")
        print(f"-> {output_path} に保存しました")

    conn.close()
