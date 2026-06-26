#!/usr/bin/env python3
"""board_posts の実態と、ホワイトボード機能に対応するテーブルを調査する。

使い方:
    uv run python scripts/investigate_whiteboard.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv()

from kpi import redash
from kpi.config import REDASH

DS_WORK = REDASH.data_sources.work  # 7: careecon_work


def run(client: httpx.Client, sql: str) -> list[dict]:
    return redash.run_adhoc_query(client, DS_WORK, sql)


def show_table(client: httpx.Client, table: str) -> None:
    print(f"\n{'='*60}")
    print(f"テーブル: {table}")
    print("=" * 60)

    cols = run(client, f"SHOW COLUMNS FROM `{table}`")
    for col in cols:
        print(f"  {col.get('Field', ''):35s} {col.get('Type', '')}")

    cnt = run(client, f"SELECT COUNT(*) AS cnt FROM `{table}`")
    print(f"  → 総件数: {cnt[0]['cnt']:,}")

    sample = run(client, f"SELECT * FROM `{table}` LIMIT 3")
    if sample:
        print("  サンプル (3件):")
        for row in sample:
            print(f"    {row}")


def main() -> None:
    with httpx.Client(timeout=180) as client:

        # 1. board_posts の実態を確認
        print("\n【1】board_posts の構造を確認")
        show_table(client, "board_posts")

        # 2. DS7 の全テーブル一覧を取得して whiteboard 系を探す
        print("\n\n【2】DS7 全テーブル一覧 (whiteboard / white_board / board 系を抽出)")
        tables_raw = run(client, "SHOW TABLES")
        all_tables = [list(row.values())[0] for row in tables_raw]
        print(f"  総テーブル数: {len(all_tables)}")

        keywords = ["white", "board", "wb", "kanban", "sticky", "memo", "note"]
        hits = [t for t in all_tables if any(kw in t.lower() for kw in keywords)]
        print(f"  キーワードヒット: {hits}")

        for t in hits:
            if t != "board_posts":  # board_posts は上で確認済み
                show_table(client, t)

        # 3. 全テーブル名を出力（機能っぽいもの目視確認用）
        print("\n\n【3】DS7 全テーブル名 (アルファベット順)")
        for t in sorted(all_tables):
            print(f"  {t}")


if __name__ == "__main__":
    main()
