import httpx
import pandas as pd

from kpi import redash
from kpi.config import REDASH

_SQL = """
SELECT
  s.project_id  AS pid,
  '大工程'      AS content,
  lp.created_at AS content_date,
  lp.id         AS source_id,
  NULL          AS user_id,
  NULL          AS platform
FROM large_processes lp
JOIN schedules s ON s.id = lp.schedule_id

UNION ALL

SELECT
  s.project_id  AS pid,
  '小工程'      AS content,
  sp.created_at AS content_date,
  sp.id         AS source_id,
  NULL          AS user_id,
  NULL          AS platform
FROM small_processes sp
JOIN schedules s ON s.id = sp.schedule_id

UNION ALL

SELECT
  s.project_id           AS pid,
  '出来高'               AS content,
  lp.progress_updated_on AS content_date,
  lp.id                  AS source_id,
  NULL                   AS user_id,
  NULL                   AS platform
FROM large_processes lp
JOIN schedules s ON s.id = lp.schedule_id
WHERE lp.progress_updated_on IS NOT NULL

UNION ALL

SELECT
  s.project_id           AS pid,
  '出来高'               AS content,
  sp.progress_updated_on AS content_date,
  sp.id                  AS source_id,
  NULL                   AS user_id,
  NULL                   AS platform
FROM small_processes sp
JOIN schedules s ON s.id = sp.schedule_id
WHERE sp.progress_updated_on IS NOT NULL

UNION ALL

SELECT
  dr.project_id        AS pid,
  '日報'               AS content,
  dr.construction_date AS content_date,
  dr.id                AS source_id,
  u.id                 AS user_id,
  NULL                 AS platform
FROM daily_reports dr
JOIN users u ON u.uid = dr.uid

UNION ALL

SELECT
  a.project_id AS pid,
  '出面'       AS content,
  a.work_date  AS content_date,
  a.id         AS source_id,
  u.id         AS user_id,
  CASE WHEN a.check_in_at IS NOT NULL THEN 'app' ELSE 'browser' END AS platform
FROM attendances a
JOIN users u ON u.id = a.user_id

UNION ALL

SELECT
  r.project_id AS pid,
  '報告書'     AS content,
  r.created_at AS content_date,
  r.id         AS source_id,
  u.id         AS user_id,
  NULL         AS platform
FROM reports r
JOIN users u ON u.id = r.user_id
WHERE r.project_id IS NOT NULL
  AND r.deleted_at <= '1970-01-01 00:00:00'

UNION ALL

SELECT
  bp.project_id AS pid,
  '掲示板'      AS content,
  bp.created_at AS content_date,
  bp.id         AS source_id,
  NULL          AS user_id,
  CASE
    WHEN MAX(CASE WHEN img.device_uuid IS NOT NULL
                       AND img.device_uuid != '' THEN 1 ELSE 0 END) = 1 THEN 'app'
    WHEN MAX(CASE WHEN img.id IS NOT NULL THEN 1 ELSE 0 END) = 1 THEN 'browser'
    ELSE NULL
  END           AS platform
FROM board_posts bp
LEFT JOIN content_resources cr
  ON cr.resource_id = bp.id AND cr.resource_type = 'BoardPost'
LEFT JOIN contents img
  ON img.id = cr.content_id AND img.type = 'Content::Image'
WHERE bp.project_id IS NOT NULL
GROUP BY bp.project_id, bp.created_at, bp.id
"""


_AI_SQL = """
SELECT
  cid        AS company_uuid,
  'AIアシスタント' AS content,
  created_at AS content_date
FROM ai_logs
WHERE tag = 'start_session'
"""

_CONTENTS_SQL = """
SELECT
  comp.cid        AS company_uuid,
  CASE
    WHEN cont.type = 'Content::Image'     THEN '写真アップロード'
    WHEN cont.type = 'Content::Directory' THEN 'フォルダ作成'
  END             AS content,
  cont.created_at AS content_date,
  CASE
    WHEN cont.device_uuid IS NOT NULL AND cont.device_uuid != '' THEN 'app'
    ELSE 'browser'
  END             AS platform
FROM contents cont
JOIN companies comp ON cont.company_id = comp.id
WHERE cont.created_at >= DATE_SUB(CURRENT_DATE, INTERVAL 2 YEAR)
  AND (
    (cont.type = 'Content::Image')
    OR (cont.type = 'Content::Directory' AND cont.root_model IS NULL)
  )
"""


def _to_df(rows: list[dict[str, object]]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["content_date"] = pd.to_datetime(df["content_date"], errors="coerce")
    return df


def fetch(client: httpx.Client) -> pd.DataFrame:
    """work_user_history を取得して DataFrame で返す。"""
    rows = redash.run_adhoc_query(client, REDASH.data_sources.work, _SQL)
    return _to_df(rows)


def fetch_ai(client: httpx.Client) -> pd.DataFrame:
    """ai_logs の start_session を company_uuid ベースで取得する。"""
    rows = redash.run_adhoc_query(client, REDASH.data_sources.work, _AI_SQL)
    return _to_df(rows)


def fetch_contents(client: httpx.Client) -> pd.DataFrame:
    """写真アップロード・フォルダ作成を contents テーブルから取得する。"""
    rows = redash.run_adhoc_query(client, REDASH.data_sources.work, _CONTENTS_SQL)
    return _to_df(rows)


_DAILY_REPORT_ATTRS_SQL = """
SELECT
  dr.id AS source_id,
  CASE WHEN COUNT(drc.id) > 0 THEN 1 ELSE 0 END AS has_photo,
  COUNT(drc.id)                                   AS photo_count,
  CASE WHEN EXISTS (
    SELECT 1 FROM ai_logs al
    JOIN users u ON al.uid = u.id
    WHERE u.uid = dr.uid
      AND DATE(al.created_at) = DATE(dr.created_at)
      AND al.tag = 'save_report'
  ) THEN 1 ELSE 0 END                             AS has_ai,
  DATEDIFF(DATE(dr.created_at), dr.construction_date) AS lag_days
FROM daily_reports dr
LEFT JOIN daily_reports_contents drc ON drc.daily_report_id = dr.id
GROUP BY dr.id, dr.created_at, dr.construction_date
"""


def fetch_daily_report_attrs(client: httpx.Client) -> pd.DataFrame:
    """日報ごとの写真添付有無・枚数・遡り日数を取得する。ファネル分析の基礎テーブル用。"""
    rows = redash.run_adhoc_query(
        client, REDASH.data_sources.work, _DAILY_REPORT_ATTRS_SQL
    )
    df = pd.DataFrame(rows)
    df["has_photo"] = df["has_photo"].astype(bool)
    df["photo_count"] = df["photo_count"].astype(int)
    df["has_ai"] = df["has_ai"].astype(bool)
    df["lag_days"] = df["lag_days"].astype(int)
    return df


_REPORT_ATTRS_SQL = """
SELECT
  r.id                                                    AS source_id,
  CASE WHEN r.report_type = 1 THEN 1 ELSE 0 END          AS has_ai
FROM reports r
WHERE r.project_id IS NOT NULL
"""


def fetch_report_attrs(client: httpx.Client) -> pd.DataFrame:
    """報告書ごとのAI生成フラグを取得する。ファネル分析の基礎テーブル用。"""
    rows = redash.run_adhoc_query(client, REDASH.data_sources.work, _REPORT_ATTRS_SQL)
    df = pd.DataFrame(rows)
    df["has_ai"] = df["has_ai"].astype(bool)
    return df
