"""顧客ライフサイクルステージ (plan_type x onboarding) テーブル。

lifecycle_stage の値:
  onboarding-plus  : Plus 契約かつ契約開始月から 3 か月以内
  plus             : Plus 契約かつ 3 か月超
  onboarding-mini  : Mini 契約かつ契約開始月から 3 か月以内
  mini             : Mini 契約かつ 3 か月超
  retired          : 全契約が終了し、当月にアクティブな契約なし

plus/mini と onboarding は独立した軸なので MECE になっている。
同一月に複数契約が重なる場合は plus を優先する。

設計方針:
  Plus ライフサイクルは SF をプライマリソース (sf_all_plus_customers / sf_customers) として構築する。
  CAS (contracts) は「Plus 開始日」の算出と「過去月の在籍確認」にのみ使用する。
  これにより CAS の登録遅れ・プラン変更タイムラグが顧客の存在判定に影響しない。
"""

import duckdb
import pandas as pd

# CAS で有効な契約を「その月をカバーしている」と判定する条件 (DuckDB SQL 断片)
_CAS_ACTIVE_COND = """
    (con.status = 'active'
     AND (con.end_date IS NULL
          OR strftime(con.end_date, '%Y-%m') >= m.month))
    OR
    (con.status = 'finished'
     AND con.end_date IS NOT NULL
     AND strftime(con.end_date, '%Y-%m') >= m.month
     AND strftime(con.end_date, '%Y-%m') < strftime(CURRENT_DATE, '%Y-%m'))
"""

# 同じ条件を con2 で参照する版 (NOT EXISTS の内側で使う)
_CAS_ACTIVE_COND2 = _CAS_ACTIVE_COND.replace("con.", "con2.")


def build(
    conn: duckdb.DuckDBPyConnection,
    *,
    sf_table: str = "sf_all_plus_customers",
) -> pd.DataFrame:
    """customer_lifecycle DataFrame を生成する。

    Plus ライフサイクルは SF ファースト設計:
      sf_all_plus_customers を基底として全 Plus 顧客を展開し、
      CAS は Plus 開始日と過去月の在籍確認にのみ利用する。

    Mini ライフサイクルは従来通り CAS ファースト設計。
    """
    tables = {r[0] for r in conn.execute("SHOW TABLES").fetchall()}

    keiei_months_union = (
        """UNION
        SELECT DISTINCT strftime(content_date, '%Y-%m') AS month
        FROM keiei_user_history
        WHERE content_date IS NOT NULL"""
        if "keiei_user_history" in tables
        else ""
    )

    if sf_table == "sf_all_plus_customers" and "sf_customers" in tables:
        result = _build_sf_first(conn, keiei_months_union)
    else:
        result = _build_cas_first(conn, sf_table, tables, keiei_months_union)

    return result


def _build_sf_first(
    conn: duckdb.DuckDBPyConnection,
    keiei_months_union: str,
) -> pd.DataFrame:
    """SF をプライマリとした Plus 顧客ライフサイクルを構築する。

    active:  sf_all_plus_customers に存在し、「sf_customers でアクティブ」または
             「CAS にその月をカバーする契約がある」月を active とする。
    retired: sf_all_plus_customers に存在し、CAS が finished かつ active でない月。
    """
    return conn.sql(f"""
        WITH all_months AS (
            SELECT DISTINCT strftime(content_date, '%Y-%m') AS month
            FROM work_user_history
            {keiei_months_union}
        ),

        -- SF Plus 顧客ごとの「Plus 開始日」を確定する。
        -- CAS Plus 契約開始日 と SF-override 初発火月 の早い方を採用する。
        sf_plus_start AS (
            SELECT company_uuid, MIN(plus_start_date) AS plus_start_date FROM (

                -- Path 1: CAS に Plus 契約がある → その最古開始日
                SELECT company_uuid, MIN(start_date) AS plus_start_date
                FROM contracts
                WHERE plan_type = 'plus'
                GROUP BY company_uuid

                UNION ALL

                -- Path 2: CAS に Plus 契約がない (Mini→Plus 移行タイムラグ等) →
                -- SF override が初めて発火する月を Plus 開始日とみなす
                SELECT sf.company_uuid,
                       CAST(MIN(m.month) || '-01' AS DATE) AS plus_start_date
                FROM sf_customers sf
                CROSS JOIN all_months m
                -- CAS に何らかの契約が存在し始めた月以降のみ対象
                INNER JOIN (
                    SELECT company_uuid, MIN(start_date) AS earliest_start
                    FROM contracts GROUP BY company_uuid
                ) earliest
                    ON  sf.company_uuid = earliest.company_uuid
                    AND strftime(earliest.earliest_start, '%Y-%m') <= m.month
                WHERE m.month <= strftime(CURRENT_DATE, '%Y-%m')
                  AND NOT EXISTS (
                      SELECT 1 FROM contracts con2
                      WHERE con2.company_uuid = sf.company_uuid
                        AND strftime(con2.start_date, '%Y-%m') <= m.month
                        AND ({_CAS_ACTIVE_COND2})
                  )
                GROUP BY sf.company_uuid
            )
            GROUP BY company_uuid
        ),

        -- Plus 顧客の active 月を展開する
        active_ranked AS (
            SELECT
                m.month,
                sfc.company_uuid,
                comp.company_name,
                'plus'              AS plan_type,
                ps.plus_start_date  AS start_date,
                -- is_onboarding: Plus 開始月から 3 か月以内
                m.month < strftime(
                    CAST(ps.plus_start_date AS DATE) + INTERVAL '3' MONTH, '%Y-%m'
                )                   AS is_onboarding,
                1                   AS rn
            FROM all_months m
            CROSS JOIN sf_all_plus_customers sfc
            JOIN companies comp    ON comp.company_uuid = sfc.company_uuid
            JOIN sf_plus_start ps  ON ps.company_uuid  = sfc.company_uuid
            WHERE strftime(ps.plus_start_date, '%Y-%m') <= m.month
              AND m.month <= strftime(CURRENT_DATE, '%Y-%m')
              AND (
                  -- SF で現在もアクティブ（CAS 状態に依らず）
                  EXISTS (
                      SELECT 1 FROM sf_customers sc
                      WHERE sc.company_uuid = sfc.company_uuid
                  )
                  OR
                  -- 過去月: CAS にその月をカバーする有効契約があった
                  EXISTS (
                      SELECT 1 FROM contracts con
                      WHERE con.company_uuid = sfc.company_uuid
                        AND strftime(con.start_date, '%Y-%m') <= m.month
                        AND ({_CAS_ACTIVE_COND})
                  )
              )
        ),

        active AS (SELECT * FROM active_ranked WHERE rn = 1),

        -- 解約済み (sf_all_plus_customers に存在するが active でない) 月
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
            FROM all_months m
            INNER JOIN contracts con
                ON  strftime(con.end_date, '%Y-%m') < m.month
                AND con.status = 'finished'
            INNER JOIN companies comp
                ON comp.company_uuid = con.company_uuid
            INNER JOIN sf_all_plus_customers sfc
                ON sfc.company_uuid = con.company_uuid
            WHERE NOT EXISTS (
                SELECT 1 FROM active a
                WHERE a.company_uuid = con.company_uuid
                  AND a.month        = m.month
            )
        )

        SELECT
            month, company_uuid, company_name, plan_type, is_onboarding,
            CASE
                WHEN plan_type = 'plus' AND is_onboarding THEN 'onboarding-plus'
                WHEN plan_type = 'plus'                    THEN 'plus'
                WHEN plan_type = 'mini' AND is_onboarding THEN 'onboarding-mini'
                WHEN plan_type = 'mini'                    THEN 'mini'
            END AS lifecycle_stage
        FROM active

        UNION ALL

        SELECT
            month, company_uuid, company_name, plan_type, is_onboarding,
            'retired' AS lifecycle_stage
        FROM retired_ranked WHERE rn = 1

        ORDER BY month, company_name
    """).df()


def _build_cas_first(
    conn: duckdb.DuckDBPyConnection,
    sf_table: str,
    tables: set,
    keiei_months_union: str,
) -> pd.DataFrame:
    """Mini など CAS ファーストのライフサイクルを構築する (従来ロジック)。"""
    sf_join = (
        f"INNER JOIN {sf_table} AS sf ON con.company_uuid = sf.company_uuid"
        if sf_table in tables
        else ""
    )

    return conn.sql(f"""
        WITH all_months AS (
            SELECT DISTINCT strftime(content_date, '%Y-%m') AS month
            FROM work_user_history
            {keiei_months_union}
        ),
        first_contract AS (
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
                AND ({_CAS_ACTIVE_COND})
            INNER JOIN companies AS comp ON con.company_uuid = comp.company_uuid
            {sf_join}
            INNER JOIN first_contract AS fc
                ON  con.company_uuid = fc.company_uuid
                AND con.plan_type    = fc.plan_type
        ),
        active AS (SELECT * FROM active_ranked WHERE rn = 1),
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
                  AND a.month = m.month
            )
        )
        SELECT
            month, company_uuid, company_name, plan_type, is_onboarding,
            CASE
                WHEN plan_type = 'plus' AND is_onboarding THEN 'onboarding-plus'
                WHEN plan_type = 'plus'                    THEN 'plus'
                WHEN plan_type = 'mini' AND is_onboarding THEN 'onboarding-mini'
                WHEN plan_type = 'mini'                    THEN 'mini'
            END AS lifecycle_stage
        FROM active

        UNION ALL

        SELECT
            month, company_uuid, company_name, plan_type, is_onboarding,
            'retired' AS lifecycle_stage
        FROM retired_ranked WHERE rn = 1

        ORDER BY month, company_name
    """).df()


def build_mini(conn: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Mini 顧客の customer_lifecycle DataFrame を生成する。"""
    tables = {r[0] for r in conn.execute("SHOW TABLES").fetchall()}
    keiei_months_union = (
        """UNION
        SELECT DISTINCT strftime(content_date, '%Y-%m') AS month
        FROM keiei_user_history
        WHERE content_date IS NOT NULL"""
        if "keiei_user_history" in tables
        else ""
    )
    return _build_cas_first(conn, "mini_sf_customers", tables, keiei_months_union)
