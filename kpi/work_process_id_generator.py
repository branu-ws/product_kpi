import httpx
import pandas as pd

from kpi import redash

_DATA_SOURCE_ID = 7

_SQL = """
SELECT
    p.id         AS pid,
    p.company_id AS company_id,
    comp.cid     AS company_uuid,
    p.created_at AS project_created_at
FROM
    projects p
INNER JOIN
    companies comp ON p.company_id = comp.id
WHERE
    comp.cid NOT IN (
        '05118182-b7ae-40d5-9881-b1f19b79ce23', '8b8281ce-3cb4-4338-8847-a55a9137c3e7',
        '648d2989-2149-4250-9292-ab1406d0ef86', 'e56ed477-118c-40bf-b20a-ac6b40223731',
        'c50e187a-642b-43de-be8e-04c502e1c3ea', 'ae3ff8b9-ea07-4f4d-9eb1-18b62fd0fa9b',
        '8562f27c-f87d-4cd6-854c-0908f723db56', 'fe6b76a5-e1b9-4828-a997-0053cef80383',
        'd0b312f2-b6cd-4d0e-b007-170e55d24ad1', '9fd24e05-b8fd-46d7-9db1-0978abf90cf7',
        '671574ff-0d25-4f94-80b6-a7df1d3da541', '48bbc7a2-74e7-4ed7-9397-2ac584ec46ed',
        '38a2fe10-7091-4236-ba29-3c02cf9cf181', '686e2166-dbda-4115-8f1d-b118f3cf6f82',
        '51ca71b1-1ec9-4d48-9748-5cf566c6644e'
    )
    AND (comp.deleted_at IS NULL OR comp.deleted_at <= '1970-01-01 00:00:00')
"""


def _to_df(rows: list[dict[str, object]]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["project_created_at"] = pd.to_datetime(df["project_created_at"], errors="coerce")
    return df


def fetch(client: httpx.Client) -> pd.DataFrame:
    """有効なプロジェクト一覧を取得して DataFrame で返す。"""
    rows = redash.run_adhoc_query(client, _DATA_SOURCE_ID, _SQL)
    return _to_df(rows)
