"""施工管理プロダクトのユーザー情報を取得する。

user_id は work_user_history.created_by と対応する DS7 の users.id。
"""

import httpx
import pandas as pd

from kpi import redash

_DATA_SOURCE_ID = 7

_SQL = """
SELECT
    u.id          AS user_id,
    u.uid         AS user_uuid,
    u.name        AS user_name,
    comp.cid      AS company_uuid,
    u.deleted_at,
    u.created_at
FROM users AS u
INNER JOIN companies_users AS cu   ON cu.user_id    = u.id
INNER JOIN companies       AS comp ON comp.id        = cu.company_id
WHERE comp.cid IS NOT NULL
"""


def fetch(client: httpx.Client) -> pd.DataFrame:
    """DS7 からユーザー一覧を取得する。"""
    print("  DS7 からユーザー情報を取得中...")
    rows = redash.run_adhoc_query(client, _DATA_SOURCE_ID, _SQL)
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(
            columns=[
                "user_id",
                "user_uuid",
                "user_name",
                "company_uuid",
                "deleted_at",
                "created_at",
            ]
        )
    df["created_at"] = pd.to_datetime(df["created_at"])
    df["deleted_at"] = pd.to_datetime(df["deleted_at"], errors="coerce")
    return df
