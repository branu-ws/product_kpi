"""顧客ライフサイクルステージ (plan_type x onboarding) テーブル。

lifecycle_stage の値:
  onboarding-plus  : Plus 契約かつ契約開始月から 3 か月以内
  plus             : Plus 契約かつ 3 か月超
  onboarding-mini  : Mini 契約かつ契約開始月から 3 か月以内
  mini             : Mini 契約かつ 3 か月超
  retired          : 全契約が終了し、当月にアクティブな契約なし

plus/mini と onboarding は独立した軸なので MECE になっている。
同一月に複数契約が重なる場合は plus を優先する。
"""

import duckdb
import pandas as pd


def build(
    conn: duckdb.DuckDBPyConnection,
    *,
    sf_table: str = "sf_all_plus_customers",
) -> pd.DataFrame:
    """customer_lifecycle DataFrame を生成する。

    conn に work_user_history / contracts / companies が登録済みであること。
    sf_table が登録されている場合はそのホワイトリストで絞り込む。
    """
    tables = {r[0] for r in conn.execute("SHOW TABLES").fetchall()}
    sf_join = (
        f"INNER JOIN {sf_table} AS sf ON con.company_uuid = sf.company_uuid"
        if sf_table in tables
        else ""
    )
    # CAS が finished / 未登録でも SF がアクティブなら active 扱いにするオーバーライド。
    # Plus ビルドのみ。Mini は mini_sf_customers を使い別途管理。
    sf_override_union = ""
    if sf_table == "sf_all_plus_customers" and "sf_customers" in tables:
        sf_override_union = """
        UNION ALL
        -- SF はアクティブだが CAS にその月をカバーする有効契約がない顧客
        -- （Mini→Plus 移行タイムラグ等で CAS が遅れているケースへの対応）
        SELECT
            m.month,
            sf.company_uuid,
            comp.company_name,
            'plus'                     AS plan_type,
            earliest.earliest_start    AS start_date,
            FALSE                      AS is_onboarding,
            1                          AS rn
        FROM all_months AS m
        INNER JOIN sf_customers AS sf ON TRUE
        INNER JOIN companies AS comp ON sf.company_uuid = comp.company_uuid
        -- CAS に少なくとも 1 件の契約がある月以降のみ（完全新規は対象外）
        INNER JOIN (
            SELECT company_uuid, MIN(start_date) AS earliest_start
            FROM contracts
            GROUP BY company_uuid
        ) AS earliest
            ON  sf.company_uuid = earliest.company_uuid
            AND strftime(earliest.earliest_start, '%Y-%m') <= m.month
        WHERE m.month <= strftime(CURRENT_DATE, '%Y-%m')
        AND NOT EXISTS (
            SELECT 1 FROM contracts con2
            WHERE con2.company_uuid = sf.company_uuid
              AND strftime(con2.start_date, '%Y-%m') <= m.month
              AND (
                  (con2.status = 'active'
                   AND (con2.end_date IS NULL
                        OR strftime(con2.end_date, '%Y-%m') >= m.month))
                  OR
                  (con2.status = 'finished'
                   AND con2.end_date IS NOT NULL
                   AND strftime(con2.end_date, '%Y-%m') >= m.month
                   AND strftime(con2.end_date, '%Y-%m')
                       < strftime(CURRENT_DATE, '%Y-%m'))
              )
        )
        """
    keiei_months_union = (
        """UNION
        SELECT DISTINCT strftime(content_date, '%Y-%m') AS month
        FROM keiei_user_history
        WHERE content_date IS NOT NULL"""
        if "keiei_user_history" in tables
        else ""
    )

    result: pd.DataFrame = conn.sql(f"""
        WITH all_months AS (
            SELECT DISTINCT strftime(content_date, '%Y-%m') AS month
            FROM work_user_history
            {keiei_months_union}
        ),
        first_contract AS (
            -- Plus→Plus更新はリセットしない、Mini→Plusはリセットする
            -- plan_type別のMINを使うことで両方を解決
            SELECT company_uuid, plan_type, MIN(start_date) AS first_start_date
            FROM contracts
            GROUP BY company_uuid, plan_type
        ),
        active_ranked AS (
            SELECT
                m.month,
                con.company_uuid,
                comp.company_name,
                con.plan_type,
                con.start_date,
                m.month < strftime(
                    CAST(fc.first_start_date AS DATE) + INTERVAL '3' MONTH, '%Y-%m'
                ) AS is_onboarding,
                ROW_NUMBER() OVER (
                    PARTITION BY m.month, con.company_uuid
                    ORDER BY
                        CASE WHEN con.plan_type = 'plus' THEN 0 ELSE 1 END,
                        con.start_date DESC
                ) AS rn
            FROM all_months AS m
            INNER JOIN contracts AS con
                ON strftime(con.start_date, '%Y-%m') <= m.month
                AND (
                    -- 現在も継続中の契約
                    (con.status = 'active'
                     AND (con.end_date IS NULL
                          OR strftime(con.end_date, '%Y-%m') >= m.month))
                    OR
                    -- 解約済みだがその月はアクティブだった契約
                    -- (将来日付の finished は不正データなので除外)
                    (con.status = 'finished'
                     AND con.end_date IS NOT NULL
                     AND strftime(con.end_date, '%Y-%m') >= m.month
                     AND strftime(con.end_date, '%Y-%m')
                         < strftime(CURRENT_DATE, '%Y-%m'))
                )
            INNER JOIN companies AS comp ON con.company_uuid = comp.company_uuid
            {sf_join}
            INNER JOIN first_contract AS fc
                ON  con.company_uuid = fc.company_uuid
                AND con.plan_type    = fc.plan_type
            {sf_override_union}
        ),
        active AS (
            SELECT * FROM active_ranked WHERE rn = 1
        ),
        retired_ranked AS (
            SELECT
                m.month,
                con.company_uuid,
                comp.company_name,
                con.plan_type,
                con.start_date,
                FALSE AS is_onboarding,
                ROW_NUMBER() OVER (
                    PARTITION BY m.month, con.company_uuid
                    ORDER BY con.end_date DESC
                ) AS rn
            FROM all_months AS m
            INNER JOIN contracts AS con
                ON  strftime(con.end_date, '%Y-%m') < m.month
                AND con.status = 'finished'
            INNER JOIN companies AS comp ON con.company_uuid = comp.company_uuid
            {sf_join}
            WHERE NOT EXISTS (
                SELECT 1 FROM active AS a
                WHERE a.company_uuid = con.company_uuid
                  AND a.month  = m.month
            )
        )
        SELECT
            month,
            company_uuid,
            company_name,
            plan_type,
            is_onboarding,
            CASE
                WHEN plan_type = 'plus' AND is_onboarding THEN 'onboarding-plus'
                WHEN plan_type = 'plus'                    THEN 'plus'
                WHEN plan_type = 'mini' AND is_onboarding THEN 'onboarding-mini'
                WHEN plan_type = 'mini'                    THEN 'mini'
            END AS lifecycle_stage
        FROM active

        UNION ALL

        SELECT
            month,
            company_uuid,
            company_name,
            plan_type,
            is_onboarding,
            'retired' AS lifecycle_stage
        FROM retired_ranked
        WHERE rn = 1

        ORDER BY month, company_name
    """).df()

    return result


def build_mini(conn: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Mini 顧客の customer_lifecycle DataFrame を生成する。

    mini_sf_customers テーブルをホワイトリストとして使用する。
    """
    return build(conn, sf_table="mini_sf_customers")
