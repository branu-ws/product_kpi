#!/usr/bin/env python3
"""DS7 (careecon_work) のログイン関連テーブルを探索するスクリプト。

使い方:
    uv run python scripts/explore_login_tables.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

from kpi import redash
from kpi.config import REDASH

DS_WORK = REDASH.data_sources.work   # 7: careecon_work
DS_DB   = REDASH.data_sources.db     # 1: careecon_db
DS_CAS  = REDASH.data_sources.cas    # 2: careecon_cas


def run(client: httpx.Client, ds_id: int, sql: str) -> list[dict]:
    return redash.run_adhoc_query(client, ds_id, sql)


def describe(client: httpx.Client, ds_id: int, table: str) -> None:
    print(f"\n--- [{ds_id}] {table} ---")
    cols = run(client, ds_id, f"SHOW COLUMNS FROM `{table}`")
    for col in cols:
        print(f"  {col.get('Field',''):35s} {col.get('Type','')}")
    cnt = run(client, ds_id, f"SELECT COUNT(*) AS cnt FROM `{table}`")
    print(f"  → 総件数: {cnt[0]['cnt']:,}")
    sample = run(client, ds_id, f"SELECT * FROM `{table}` LIMIT 3")
    if sample:
        print("  サンプル (3件):")
        for row in sample:
            print(f"    {row}")


def main() -> None:
    with httpx.Client(timeout=180) as client:

        # ── DS7: content_access_histories / summaries ─────────────────────────
        print("=== DS7: content_access_histories ===")
        describe(client, DS_WORK, "content_access_histories")

        print("\n=== DS7: content_access_summaries ===")
        describe(client, DS_WORK, "content_access_summaries")

        # ── DS7: users (Devise sign_in フィールド確認) ─────────────────────────
        print("\n=== DS7: users (全カラム) ===")
        cols = run(client, DS_WORK, "SHOW COLUMNS FROM `users`")
        for col in cols:
            print(f"  {col.get('Field',''):35s} {col.get('Type','')}")

        # ── DS1/DS2: ログイン系テーブルを探す ─────────────────────────────────
        for ds_id, label in [(DS_DB, "DS1 careecon_db"), (DS_CAS, "DS2 careecon_cas")]:
            print(f"\n=== {label}: SHOW TABLES ===")
            tables = run(client, ds_id, "SHOW TABLES")
            all_tables = [list(row.values())[0] for row in tables]
            login_kws = ["login", "session", "sign_in", "signin", "auth", "access_log", "user_log", "user_session"]
            hits = [t for t in all_tables if any(kw in t.lower() for kw in login_kws)]
            if hits:
                for t in hits:
                    describe(client, ds_id, t)
            else:
                print("  ログイン系テーブルなし")

            # users テーブルのカラムも確認
            if "users" in all_tables:
                print(f"\n=== {label}: users カラム ===")
                cols = run(client, ds_id, "SHOW COLUMNS FROM `users`")
                for col in cols:
                    print(f"  {col.get('Field',''):35s} {col.get('Type','')}")


if __name__ == "__main__":
    main()
