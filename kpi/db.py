"""DuckDB / BigQuery ユーティリティ。

- save()    : DataFrame を DuckDB に永続化する。USE_BIGQUERY=1 なら BigQuery にも書く。
- load()    : DuckDB ファイルから接続を返す(Redash アクセス不要)。
- is_cached(): キャッシュ済みか確認する。

環境変数:
  USE_BIGQUERY   : 非空文字列で BigQuery 書き込みを有効化 (Cloud Run で設定)
  GCP_PROJECT_ID : BigQuery プロジェクト ID
  BQ_DATASET     : BigQuery データセット名 (デフォルト: kpi)
"""

import os
from pathlib import Path

import duckdb
import pandas as pd

DB_PATH = Path(__file__).parent.parent / "cache.duckdb"


def is_cached() -> bool:
    return DB_PATH.exists()


def save(**tables: pd.DataFrame) -> None:
    """DataFrame を DuckDB に保存し、USE_BIGQUERY=1 なら BigQuery にも書く。"""
    _save_duckdb(**tables)
    if os.getenv("USE_BIGQUERY"):
        _save_bigquery(**tables)


def _save_duckdb(**tables: pd.DataFrame) -> None:
    conn = duckdb.connect(str(DB_PATH))
    for name, frame in tables.items():
        conn.execute(f"DROP TABLE IF EXISTS {name}")
        conn.register("_tmp", frame)
        conn.execute(f"CREATE TABLE {name} AS SELECT * FROM _tmp")
        conn.unregister("_tmp")
    conn.close()
    print(f"  キャッシュ保存: {DB_PATH}")


def _save_bigquery(**tables: pd.DataFrame) -> None:
    from google.cloud import bigquery  # type: ignore[import-not-found]

    project = os.environ["GCP_PROJECT_ID"]
    dataset = os.getenv("BQ_DATASET", "kpi")
    client = bigquery.Client(project=project)
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
