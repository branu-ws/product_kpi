import httpx
import pandas as pd

from kpi import redash

_QUERY_ID = 914
_DATA_SOURCE_ID = 7  # 実DBのデータソースID(Query Results=11 とは別)

_SQL = """
SELECT
  s.project_id  AS pid,
  '大工程'      AS content,
  lp.created_at AS content_date,
  NULL          AS created_by,
  NULL          AS bool_ai_assist
FROM large_processes lp
JOIN schedules s ON s.id = lp.schedule_id

UNION ALL

SELECT
  s.project_id  AS pid,
  '小工程'      AS content,
  sp.created_at AS content_date,
  NULL          AS created_by,
  NULL          AS bool_ai_assist
FROM small_processes sp
JOIN schedules s ON s.id = sp.schedule_id

UNION ALL

SELECT
  s.project_id           AS pid,
  '出来高'               AS content,
  lp.progress_updated_on AS content_date,
  NULL                   AS created_by,
  NULL                   AS bool_ai_assist
FROM large_processes lp
JOIN schedules s ON s.id = lp.schedule_id
WHERE lp.progress_updated_on IS NOT NULL

UNION ALL

SELECT
  s.project_id           AS pid,
  '出来高'               AS content,
  sp.progress_updated_on AS content_date,
  NULL                   AS created_by,
  NULL                   AS bool_ai_assist
FROM small_processes sp
JOIN schedules s ON s.id = sp.schedule_id
WHERE sp.progress_updated_on IS NOT NULL

UNION ALL

SELECT
  dr.project_id        AS pid,
  '日報'               AS content,
  dr.construction_date AS content_date,
  u.name               AS created_by,
  NULL                 AS bool_ai_assist
FROM daily_reports dr
JOIN users u ON u.uid = dr.uid

UNION ALL

SELECT
  a.project_id AS pid,
  '出面'       AS content,
  a.work_date  AS content_date,
  u.name       AS created_by,
  NULL         AS bool_ai_assist
FROM attendances a
JOIN users u ON u.id = a.user_id

UNION ALL

SELECT
  r.project_id  AS pid,
  '報告書'      AS content,
  r.created_at  AS content_date,
  u.name        AS created_by,
  r.report_type AS bool_ai_assist
FROM reports r
JOIN users u ON u.id = r.user_id
WHERE r.project_id IS NOT NULL
  AND r.deleted_at <= '1970-01-01 00:00:00'

UNION ALL

SELECT
  bp.project_id   AS pid,
  'ホワイトボード' AS content,
  bp.created_at   AS content_date,
  NULL            AS created_by,
  NULL            AS bool_ai_assist
FROM board_posts bp
WHERE bp.project_id IS NOT NULL
"""


def _to_df(rows: list[dict[str, object]]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["content_date"] = pd.to_datetime(df["content_date"], errors="coerce")
    return df


def fetch(client: httpx.Client) -> pd.DataFrame:
    """work_user_history を取得して DataFrame で返す。

    キャッシュ(query 914)があれば即返し、なければ SQL を直接実行する。
    """
    try:
        rows = redash.run_saved_query(client, _QUERY_ID)
    except RuntimeError:
        print("  キャッシュなし。SQL を直接実行します...")
        rows = redash.run_adhoc_query(client, _DATA_SOURCE_ID, _SQL)

    return _to_df(rows)
