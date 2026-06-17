"""企業 x 月 のロイヤリティ階層判定。"""

import duckdb
import pandas as pd

from kpi.config import LOYALTY


def build(conn: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """feature_health + work_user_history からロイヤリティ階層 DataFrame を生成する。

    ウィンドウサイズはパラメータから自動計算するため、
    kpi/config.py の LOYALTY の値を変えるだけで判定基準が変わる。

    離反状態の判定には work_user_history の月次合計利用回数を使用する。
    conn に work_user_history と work_process_id_generator が登録済みであること。
    """
    p = LOYALTY
    wl = max(p.god_months, p.fan_months, p.rihan_months) - 1
    ws = max(p.jisou_months, p.dansoku_months) - 1

    result: pd.DataFrame = conn.sql(f"""
        WITH company_monthly_usage AS (
            SELECT
                strftime(h.content_date, '%Y-%m') AS usage_month,
                proj.company_uuid,
                COUNT(*) AS total_usage
            FROM work_user_history AS h
            INNER JOIN work_process_id_generator AS proj ON h.pid = proj.pid
            GROUP BY usage_month, proj.company_uuid
        ),
        monthly_counts AS (
            SELECT
                fh.usage_month,
                fh.company_uuid,
                fh.company_name,
                fh.plan_type,
                fh.is_onboarding,
                fh.lifecycle_stage,
                SUM(CASE WHEN fh.health = 'good'   THEN 1 ELSE 0 END) AS good_count,
                SUM(CASE WHEN fh.health = 'normal' THEN 1 ELSE 0 END) AS normal_count,
                SUM(CASE WHEN fh.health = 'bad'    THEN 1 ELSE 0 END) AS bad_count,
                COUNT(*) AS total_features,
                COALESCE(u.total_usage, 0) AS total_usage
            FROM feature_health AS fh
            LEFT JOIN company_monthly_usage AS u
                ON  fh.company_uuid = u.company_uuid
                AND fh.usage_month  = u.usage_month
            GROUP BY
                fh.usage_month, fh.company_uuid, fh.company_name,
                fh.plan_type, fh.is_onboarding, fh.lifecycle_stage, u.total_usage
        ),
        rolling AS (
            SELECT
                *,
                COUNT(*) OVER (
                    PARTITION BY company_uuid ORDER BY usage_month
                    ROWS BETWEEN {wl} PRECEDING AND CURRENT ROW
                ) AS wl_size,
                MIN(good_count) OVER (
                    PARTITION BY company_uuid ORDER BY usage_month
                    ROWS BETWEEN {wl} PRECEDING AND CURRENT ROW
                ) AS wl_min_good,
                MIN(total_usage) OVER (
                    PARTITION BY company_uuid ORDER BY usage_month
                    ROWS BETWEEN {wl} PRECEDING AND CURRENT ROW
                ) AS wl_min_usage,
                COUNT(*) OVER (
                    PARTITION BY company_uuid ORDER BY usage_month
                    ROWS BETWEEN {ws} PRECEDING AND CURRENT ROW
                ) AS ws_size,
                MIN(good_count) OVER (
                    PARTITION BY company_uuid ORDER BY usage_month
                    ROWS BETWEEN {ws} PRECEDING AND CURRENT ROW
                ) AS ws_min_good,
                MIN(normal_count) OVER (
                    PARTITION BY company_uuid ORDER BY usage_month
                    ROWS BETWEEN {ws} PRECEDING AND CURRENT ROW
                ) AS ws_min_normal
            FROM monthly_counts
        )
        SELECT
            usage_month,
            company_uuid,
            company_name,
            plan_type,
            is_onboarding,
            lifecycle_stage,
            good_count,
            normal_count,
            bad_count,
            CASE
                WHEN wl_size >= {p.god_months}
                     AND wl_min_good >= {p.god_good_min}    THEN '神'
                WHEN wl_size >= {p.fan_months}
                     AND wl_min_good >= {p.fan_good_min}    THEN 'ファン'
                WHEN ws_size >= {p.jisou_months}
                     AND ws_min_good >= {p.jisou_good_min}  THEN '自走'
                WHEN ws_size >= {p.dansoku_months}
                     AND ws_min_normal >= 1                  THEN '2か月連続活用'
                WHEN good_count >= 1
                     OR  normal_count >= 1                   THEN '断続的活用'
                WHEN wl_size >= {p.rihan_months}
                     AND wl_min_usage = 0                    THEN '離反状態'
                ELSE 'まずい'
            END AS loyalty_tier
        FROM rolling
        ORDER BY usage_month, company_name
    """).df()

    return result


def build_keiei(conn: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """keiei_feature_health + keiei_user_history から
    ロイヤリティ階層 DataFrame を生成する。
    """
    p = LOYALTY
    wl = max(p.god_months, p.fan_months, p.rihan_months) - 1
    ws = max(p.jisou_months, p.dansoku_months) - 1

    result: pd.DataFrame = conn.sql(f"""
        WITH company_monthly_usage AS (
            SELECT
                strftime(h.content_date, '%Y-%m') AS usage_month,
                h.company_uuid,
                COUNT(*) AS total_usage
            FROM keiei_user_history AS h
            GROUP BY usage_month, h.company_uuid
        ),
        monthly_counts AS (
            SELECT
                fh.usage_month,
                fh.company_uuid,
                fh.company_name,
                fh.plan_type,
                fh.is_onboarding,
                fh.lifecycle_stage,
                SUM(CASE WHEN fh.health = 'good'   THEN 1 ELSE 0 END) AS good_count,
                SUM(CASE WHEN fh.health = 'normal' THEN 1 ELSE 0 END) AS normal_count,
                SUM(CASE WHEN fh.health = 'bad'    THEN 1 ELSE 0 END) AS bad_count,
                COUNT(*) AS total_features,
                COALESCE(u.total_usage, 0) AS total_usage
            FROM keiei_feature_health AS fh
            LEFT JOIN company_monthly_usage AS u
                ON  fh.company_uuid = u.company_uuid
                AND fh.usage_month  = u.usage_month
            GROUP BY
                fh.usage_month, fh.company_uuid, fh.company_name,
                fh.plan_type, fh.is_onboarding, fh.lifecycle_stage, u.total_usage
        ),
        rolling AS (
            SELECT
                *,
                COUNT(*) OVER (
                    PARTITION BY company_uuid ORDER BY usage_month
                    ROWS BETWEEN {wl} PRECEDING AND CURRENT ROW
                ) AS wl_size,
                MIN(good_count) OVER (
                    PARTITION BY company_uuid ORDER BY usage_month
                    ROWS BETWEEN {wl} PRECEDING AND CURRENT ROW
                ) AS wl_min_good,
                MIN(total_usage) OVER (
                    PARTITION BY company_uuid ORDER BY usage_month
                    ROWS BETWEEN {wl} PRECEDING AND CURRENT ROW
                ) AS wl_min_usage,
                COUNT(*) OVER (
                    PARTITION BY company_uuid ORDER BY usage_month
                    ROWS BETWEEN {ws} PRECEDING AND CURRENT ROW
                ) AS ws_size,
                MIN(good_count) OVER (
                    PARTITION BY company_uuid ORDER BY usage_month
                    ROWS BETWEEN {ws} PRECEDING AND CURRENT ROW
                ) AS ws_min_good,
                MIN(normal_count) OVER (
                    PARTITION BY company_uuid ORDER BY usage_month
                    ROWS BETWEEN {ws} PRECEDING AND CURRENT ROW
                ) AS ws_min_normal
            FROM monthly_counts
        )
        SELECT
            usage_month,
            company_uuid,
            company_name,
            plan_type,
            is_onboarding,
            lifecycle_stage,
            good_count,
            normal_count,
            bad_count,
            CASE
                WHEN wl_size >= {p.god_months}
                     AND wl_min_good >= {p.god_good_min}    THEN '神'
                WHEN wl_size >= {p.fan_months}
                     AND wl_min_good >= {p.fan_good_min}    THEN 'ファン'
                WHEN ws_size >= {p.jisou_months}
                     AND ws_min_good >= {p.jisou_good_min}  THEN '自走'
                WHEN ws_size >= {p.dansoku_months}
                     AND ws_min_normal >= 1                  THEN '2か月連続活用'
                WHEN good_count >= 1
                     OR  normal_count >= 1                   THEN '断続的活用'
                WHEN wl_size >= {p.rihan_months}
                     AND wl_min_usage = 0                    THEN '離反状態'
                ELSE 'まずい'
            END AS loyalty_tier
        FROM rolling
        ORDER BY usage_month, company_name
    """).df()

    return result
