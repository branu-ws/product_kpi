"""Notion DB に output6 データを同期する。

使い方:
    uv run python sync_notion.py

前提: update_duckdb.py が先に実行済みで cache.duckdb が存在すること。
"""

from dotenv import load_dotenv

from kpi import db, notion_sync


def main() -> None:
    load_dotenv()
    print("DuckDB に接続中...")
    conn = db.load()
    notion_sync.sync_all(conn)
    conn.close()


if __name__ == "__main__":
    main()
