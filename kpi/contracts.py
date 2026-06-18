"""CAS から施工管理の契約情報を取得する。

plan_type: 'plus' (ビジネスプラン) / 'mini' (CAREECON miniプラン)
status   : 'active' / 'finished'

UUID の橋渡し:
  contracts.company_id → accounts.company_id → accounts.cid (UUID)
  accounts.cid = DS7 companies.cid = feature_health で使う company_uuid
  ※ CAS の company_id と DS1 の companies.id は別番号体系のため直接 JOIN 不可
"""

import httpx
import pandas as pd

from kpi import redash
from kpi.config import PLAN_TYPE_CODES

_CAS_DS_ID = 2

_ITEM_CODES = list(PLAN_TYPE_CODES.keys())
_ITEM_CODES_SQL = ", ".join(f'"{c}"' for c in _ITEM_CODES)

_SQL_CAS = f"""
SELECT
    c.company_id,
    c.status,
    c.start_date,
    c.end_date,
    i.code AS item_code
FROM contracts c
INNER JOIN items i    ON c.item_id    = i.id
INNER JOIN services s ON i.service_id = s.id
WHERE s.code = 'careecon_work'
  AND c.status IN ('active', 'finished')
  AND i.code IN ({_ITEM_CODES_SQL})
"""


def fetch(client: httpx.Client) -> pd.DataFrame:
    """CAS から施工管理の契約情報を取得し plan_type 付きで返す。

    CAS の accounts.cid (UUID) を経由して company_uuid を解決する。
    DS1 へのクロス問い合わせは不要。
    """
    rows_cas = redash.run_adhoc_query(client, _CAS_DS_ID, _SQL_CAS)
    df_cas = pd.DataFrame(rows_cas)

    if df_cas.empty:
        return pd.DataFrame(
            columns=["company_uuid", "plan_type", "status", "start_date", "end_date"]
        )

    df_cas["plan_type"] = df_cas["item_code"].map(PLAN_TYPE_CODES)

    company_ids = [str(int(x)) for x in df_cas["company_id"].dropna().unique()]
    ids_sql = ", ".join(company_ids)

    sql_accounts = (
        f"SELECT company_id, cid AS company_uuid "
        f"FROM accounts WHERE company_id IN ({ids_sql}) AND cid IS NOT NULL"
    )
    rows_accounts = redash.run_adhoc_query(client, _CAS_DS_ID, sql_accounts)
    df_accounts = pd.DataFrame(rows_accounts).drop_duplicates(subset=["company_id"])

    df = df_cas.merge(df_accounts, on="company_id", how="inner")
    df["start_date"] = pd.to_datetime(df["start_date"])
    df["end_date"] = pd.to_datetime(df["end_date"], errors="coerce")

    return df[["company_uuid", "plan_type", "status", "start_date", "end_date"]]
