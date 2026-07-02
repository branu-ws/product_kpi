"""DuckDB ユーティリティ。

- save()  : 正規化 DataFrame を DuckDB に保存する。
- load()  : DuckDB ファイルから接続を返す (Redash アクセス不要)。
- is_cached() : キャッシュ済みか確認する。
"""

import logging
from pathlib import Path

import duckdb
import pandas as pd

log = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / "cache.duckdb"


def is_cached() -> bool:
    return DB_PATH.exists()


def save(**tables: pd.DataFrame) -> None:
    """正規化 DataFrame を DuckDB に保存する。"""
    conn = duckdb.connect(str(DB_PATH))
    for name, frame in tables.items():
        conn.execute(f"DROP TABLE IF EXISTS {name}")
        conn.register("_tmp", frame)
        conn.execute(f"CREATE TABLE {name} AS SELECT * FROM _tmp")
        conn.unregister("_tmp")
    conn.close()
    log.info("キャッシュ保存: %s", DB_PATH)


def load() -> duckdb.DuckDBPyConnection:
    """永続化済みの DuckDB 接続を返す。"""
    return duckdb.connect(str(DB_PATH), read_only=True)
