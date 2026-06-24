"""顧客ロイヤリティ階層テーブルを生成する。

feature_health (or keiei_feature_health) から月次 per-company のスコアを集計し、
ローリングウィンドウで loyalty_tier を判定する。

CLAUDE.md 定義の判定優先順位 (高→低):
  神         : good ≥5機能 x 直近3か月すべて
  ファン      : good ≥2機能 x 直近3か月すべて
  自走        : good ≥1機能 x 直近2か月すべて
  2か月連続活用: normal以上≥1機能 x 直近2か月すべて
  断続的活用  : normal以上≥1機能 x 当月
  まずい      : 全機能 bad
  離反状態    : 全機能の利用回数ゼロ x 直近3か月すべて
"""

from __future__ import annotations

import duckdb
import pandas as pd

_LOYALTY_SQL = """
WITH monthly_scores AS (
    SELECT
        month,
        company_uuid,
        company_name,
        plan_type,
        is_onboarding,
        lifecycle_stage,
        COUNT(CASE WHEN health = 'good'              THEN 1 END) AS good_count,
        COUNT(CASE WHEN health IN ('good', 'normal') THEN 1 END) AS normal_plus_count,
        SUM(usage_count)                                          AS total_usage
    FROM {source_table}
    GROUP BY
        month, company_uuid, company_name, plan_type, is_onboarding, lifecycle_stage
),
rolling AS (
    SELECT
        *,
        COUNT(*)  OVER w3 AS w3_size,
        COUNT(*)  OVER w2 AS w2_size,
        MIN(CASE WHEN good_count        >= 5 THEN 1 ELSE 0 END) OVER w3 AS god_3m,
        MIN(CASE WHEN good_count        >= 2 THEN 1 ELSE 0 END) OVER w3 AS fan_3m,
        MIN(CASE WHEN good_count        >= 1 THEN 1 ELSE 0 END) OVER w2 AS proactive_2m,
        MIN(CASE WHEN normal_plus_count >= 1 THEN 1 ELSE 0 END) OVER w2 AS two_month_2m,
        CASE WHEN normal_plus_count >= 1 THEN 1 ELSE 0 END AS occasional_1m,
        MIN(CASE WHEN total_usage       =  0 THEN 1 ELSE 0 END) OVER w3 AS abandoned_3m
    FROM monthly_scores
    WINDOW
        w3 AS (PARTITION BY company_uuid ORDER BY month
               ROWS BETWEEN 2 PRECEDING AND CURRENT ROW),
        w2 AS (PARTITION BY company_uuid ORDER BY month
               ROWS BETWEEN 1 PRECEDING AND CURRENT ROW)
)
SELECT
    month,
    company_uuid,
    company_name,
    plan_type,
    is_onboarding,
    lifecycle_stage,
    good_count,
    (normal_plus_count - good_count) AS normal_count,
    CASE
        WHEN w3_size >= 3 AND god_3m       = 1 THEN '神'
        WHEN w3_size >= 3 AND fan_3m       = 1 THEN 'ファン'
        WHEN w2_size >= 2 AND proactive_2m = 1 THEN '自走'
        WHEN w2_size >= 2 AND two_month_2m = 1 THEN '2か月連続活用'
        WHEN occasional_1m                 = 1 THEN '断続的活用'
        WHEN w3_size >= 3 AND abandoned_3m = 1 THEN '離反状態'
        ELSE 'まずい'
    END AS loyalty_tier
FROM rolling
ORDER BY month, company_name
"""


def build(conn: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """feature_health から company_loyalty を生成する。"""
    return conn.sql(_LOYALTY_SQL.format(source_table="feature_health")).df()


def build_keiei(conn: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """keiei_feature_health から keiei_company_loyalty を生成する。"""
    return conn.sql(_LOYALTY_SQL.format(source_table="keiei_feature_health")).df()


def build_mini(conn: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """mini_feature_health から mini_company_loyalty を生成する。"""
    return conn.sql(_LOYALTY_SQL.format(source_table="mini_feature_health")).df()
