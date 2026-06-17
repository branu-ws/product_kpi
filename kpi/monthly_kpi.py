"""月別 KPI 集計。

月別 x content ごとに下記を集計する。
- content_count  : 利用回数
- company_count  : 利用企業数
- user_count     : 利用ユーザー数
"""

import duckdb
import pandas as pd


def build(conn: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """月別 KPI DataFrame を返す。

    Args:
        conn: work_user_history / work_process_id_generator / companies
              テーブルを持つ DuckDB 接続
    """
    return conn.sql("""
        SELECT
            strftime(h.content_date, '%Y-%m') AS usage_month,
            h.content,
            COUNT(*)                           AS content_count,
            COUNT(DISTINCT c.company_name)     AS company_count,
            COUNT(DISTINCT h.created_by)       AS user_count
        FROM work_user_history AS h
        INNER JOIN work_process_id_generator AS p ON h.pid = p.pid
        INNER JOIN companies AS c ON p.company_uuid = c.company_uuid
        GROUP BY usage_month, h.content
        ORDER BY usage_month, h.content
    """).df()
