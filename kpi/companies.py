import httpx
import pandas as pd

from kpi import redash

_DATA_SOURCE_ID = 1  # companies.name が存在するデータソース(query 910 で確認済み)

_SQL = """
SELECT
    cid  AS company_uuid,
    name AS company_name
FROM
    companies
WHERE
    name NOT IN ('越智個人', '開発部')
    AND name NOT LIKE '%テスト%'
    AND name NOT LIKE '%BRANU%'
    AND name NOT LIKE '%ブラニュー%'
    AND name NOT LIKE '%CAREECON%'
    AND name != '-'
    AND name != ''
"""


def fetch(client: httpx.Client) -> pd.DataFrame:
    """company_uuid(UUID) -> company_name のマッピングを取得して DataFrame で返す。"""
    rows = redash.run_adhoc_query(client, _DATA_SOURCE_ID, _SQL)
    return pd.DataFrame(rows)
