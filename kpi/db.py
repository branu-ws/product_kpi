"""DuckDB / BigQuery ユーティリティ。

- save()       : 正規化 DataFrame を DuckDB に保存する (BigQuery には上げない)。
- save_views() : collections/*.sql の集計結果を BigQuery のみに保存する。
                 {dataset: {table: df}} の形式でデータセットごとに分けて保存。
- load()       : DuckDB ファイルから接続を返す (Redash アクセス不要)。
- is_cached()  : キャッシュ済みか確認する。

環境変数:
  USE_BIGQUERY   : 非空文字列で BigQuery 書き込みを有効化 (Cloud Run で設定)
  GCP_PROJECT_ID : BigQuery プロジェクト ID
  BQ_DATASET     : トップレベル SQL のデフォルトデータセット名 (デフォルト: kpi)
"""

import os
from pathlib import Path

import duckdb
import pandas as pd

DB_PATH = Path(__file__).parent.parent / "cache.duckdb"


def is_cached() -> bool:
    return DB_PATH.exists()


def save(**tables: pd.DataFrame) -> None:
    """正規化 DataFrame を DuckDB に保存する。BigQuery には上げない。"""
    _save_duckdb(**tables)


def save_views(views: dict[str, dict[str, pd.DataFrame]]) -> None:
    """集計済み DataFrame を BigQuery のみに保存する (USE_BIGQUERY=1 のときだけ有効)。

    views = {dataset_name: {table_name: df, ...}, ...}
    collections/ のサブディレクトリがそのまま BigQuery データセットになる。
    データセットが存在しない場合は自動作成する。
    """
    if not os.getenv("USE_BIGQUERY"):
        return
    for dataset, tables in views.items():
        _save_bigquery(dataset, **tables)


def _save_duckdb(**tables: pd.DataFrame) -> None:
    conn = duckdb.connect(str(DB_PATH))
    for name, frame in tables.items():
        conn.execute(f"DROP TABLE IF EXISTS {name}")
        conn.register("_tmp", frame)
        conn.execute(f"CREATE TABLE {name} AS SELECT * FROM _tmp")
        conn.unregister("_tmp")
    conn.close()
    print(f"  キャッシュ保存: {DB_PATH}")


def _save_bigquery(dataset: str, **tables: pd.DataFrame) -> None:
    from google.api_core.exceptions import Conflict
    from google.cloud import bigquery

    project = os.environ["GCP_PROJECT_ID"]
    client: bigquery.Client = bigquery.Client(project=project)

    ds = bigquery.Dataset(f"{project}.{dataset}")
    ds.location = "asia-northeast1"
    try:
        client.create_dataset(ds)
        print(f"  BigQuery データセット作成: {dataset}")
    except Conflict:
        pass

    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        autodetect=True,
    )
    for name, frame in tables.items():
        table_ref = f"{project}.{dataset}.{name}"
        job = client.load_table_from_dataframe(frame, table_ref, job_config=job_config)
        job.result()
        print(f"  BigQuery 保存: {table_ref} ({len(frame):,} rows)")


def load() -> duckdb.DuckDBPyConnection:
    """永続化済みの DuckDB 接続を返す。"""
    return duckdb.connect(str(DB_PATH), read_only=True)
