"""企業 x 機能 x 月 のヘルス判定 (good / normal / bad)。"""

import duckdb
import pandas as pd

from kpi.config import ACTIVE_PLAN_TYPES, FEATURE_THRESHOLDS, KEIEI_FEATURE_THRESHOLDS


def build(conn: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """work_user_history 等からフィーチャーヘルス DataFrame を生成する。

    大工程 + 小工程 は工程作成として合算する。
    contracts テーブルで契約期間中かつ ACTIVE_PLAN_TYPES に含まれる企業のみ対象。
    利用なしの企業 x 機能 x 月 は usage_count=0 (bad) として補完する。
    """
    thresholds_df = pd.DataFrame(
        [
            {"feature": k, "good_min": v.good_min, "normal_min": v.normal_min}
            for k, v in FEATURE_THRESHOLDS.items()
        ]
    )
    conn.register("_thresholds", thresholds_df)

    plan_filter = ", ".join(f"'{p}'" for p in ACTIVE_PLAN_TYPES)

    result: pd.DataFrame = conn.sql(f"""
        WITH monthly_usage AS (
            SELECT
                strftime(h.content_date, '%Y-%m') AS usage_month,
                p.company_uuid,
                c.company_name,
                CASE
                    WHEN h.content IN ('大工程', '小工程') THEN '工程作成'
                    ELSE h.content
                END AS feature,
                COUNT(*) AS usage_count
            FROM work_user_history AS h
            INNER JOIN work_process_id_generator AS p ON h.pid = p.pid
            INNER JOIN companies AS c ON p.company_uuid = c.company_uuid
            WHERE h.content IN (
                '大工程', '小工程', '出面', '出来高', 'ホワイトボード', '日報', '報告書'
            )
            GROUP BY usage_month, p.company_uuid, c.company_name, feature
        ),
        all_months AS (
            SELECT DISTINCT strftime(content_date, '%Y-%m') AS usage_month
            FROM work_user_history
        ),
        active_per_month AS (
            -- ACTIVE_PLAN_TYPES に "mini" を追加すれば mini も含まれる
            -- retired は除外、onboarding フラグは customer_lifecycle から取得
            SELECT DISTINCT
                usage_month,
                company_uuid,
                company_name,
                plan_type,
                is_onboarding,
                lifecycle_stage
            FROM customer_lifecycle
            WHERE plan_type IN ({plan_filter})
              AND lifecycle_stage != 'retired'
        ),
        full_matrix AS (
            SELECT
                a.usage_month,
                a.company_uuid,
                a.company_name,
                a.plan_type,
                a.is_onboarding,
                a.lifecycle_stage,
                t.feature
            FROM active_per_month AS a
            CROSS JOIN _thresholds AS t
        ),
        usage_filled AS (
            SELECT
                mx.usage_month,
                mx.company_uuid,
                mx.company_name,
                mx.plan_type,
                mx.is_onboarding,
                mx.lifecycle_stage,
                mx.feature,
                COALESCE(u.usage_count, 0) AS usage_count
            FROM full_matrix AS mx
            LEFT JOIN monthly_usage AS u
                ON  mx.usage_month  = u.usage_month
                AND mx.company_uuid = u.company_uuid
                AND mx.feature      = u.feature
        )
        SELECT
            uf.usage_month,
            uf.company_uuid,
            uf.company_name,
            uf.plan_type,
            uf.is_onboarding,
            uf.lifecycle_stage,
            uf.feature,
            uf.usage_count,
            CASE
                WHEN uf.usage_count >= t.good_min   THEN 'good'
                WHEN uf.usage_count >= t.normal_min THEN 'normal'
                ELSE 'bad'
            END AS health
        FROM usage_filled AS uf
        INNER JOIN _thresholds AS t ON uf.feature = t.feature
        ORDER BY uf.usage_month, uf.company_name, uf.feature
    """).df()

    conn.unregister("_thresholds")
    return result


def build_keiei(conn: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """keiei_user_history から経営管理・CRM のフィーチャーヘルス DataFrame を生成する。

    keiei_user_history は company_uuid を直接持つため pid join 不要。
    """
    thresholds_df = pd.DataFrame(
        [
            {"feature": k, "good_min": v.good_min, "normal_min": v.normal_min}
            for k, v in KEIEI_FEATURE_THRESHOLDS.items()
        ]
    )
    conn.register("_keiei_thresholds", thresholds_df)

    plan_filter = ", ".join(f"'{p}'" for p in ACTIVE_PLAN_TYPES)

    result: pd.DataFrame = conn.sql(f"""
        WITH monthly_usage AS (
            SELECT
                strftime(h.content_date, '%Y-%m') AS usage_month,
                h.company_uuid,
                c.company_name,
                h.content AS feature,
                COUNT(*) AS usage_count
            FROM keiei_user_history AS h
            INNER JOIN companies AS c ON h.company_uuid = c.company_uuid
            WHERE h.content IN (SELECT feature FROM _keiei_thresholds)
            GROUP BY usage_month, h.company_uuid, c.company_name, feature
        ),
        active_per_month AS (
            SELECT DISTINCT
                usage_month,
                company_uuid,
                company_name,
                plan_type,
                is_onboarding,
                lifecycle_stage
            FROM customer_lifecycle
            WHERE plan_type IN ({plan_filter})
              AND lifecycle_stage != 'retired'
        ),
        full_matrix AS (
            SELECT
                a.usage_month,
                a.company_uuid,
                a.company_name,
                a.plan_type,
                a.is_onboarding,
                a.lifecycle_stage,
                t.feature
            FROM active_per_month AS a
            CROSS JOIN _keiei_thresholds AS t
        ),
        usage_filled AS (
            SELECT
                mx.usage_month,
                mx.company_uuid,
                mx.company_name,
                mx.plan_type,
                mx.is_onboarding,
                mx.lifecycle_stage,
                mx.feature,
                COALESCE(u.usage_count, 0) AS usage_count
            FROM full_matrix AS mx
            LEFT JOIN monthly_usage AS u
                ON  mx.usage_month  = u.usage_month
                AND mx.company_uuid = u.company_uuid
                AND mx.feature      = u.feature
        )
        SELECT
            uf.usage_month,
            uf.company_uuid,
            uf.company_name,
            uf.plan_type,
            uf.is_onboarding,
            uf.lifecycle_stage,
            uf.feature,
            uf.usage_count,
            CASE
                WHEN uf.usage_count >= t.good_min   THEN 'good'
                WHEN uf.usage_count >= t.normal_min THEN 'normal'
                ELSE 'bad'
            END AS health
        FROM usage_filled AS uf
        INNER JOIN _keiei_thresholds AS t ON uf.feature = t.feature
        ORDER BY uf.usage_month, uf.company_name, uf.feature
    """).df()

    conn.unregister("_keiei_thresholds")
    return result
