"""Salesforce Plus アクティブ顧客の company_uuid ホワイトリストを生成する。

フロー:
  1. SF から Plus active アカウントを全件取得
  2. CAREECON_CID__c が設定済み -> そのまま company_uuid として採用
  3. CID 未設定 -> DS1 (careecon_db) の companies テーブルと
     社名 + 住所 (都道府県・市区) で突合して company_uuid を補填
  4. company_uuid 列のみを持つ DataFrame を返す
"""

from __future__ import annotations

import re

import httpx
import pandas as pd

from kpi import redash
from kpi.config import REDASH

_PREF_MAP = {
    1: "北海道", 2: "青森県", 3: "岩手県", 4: "宮城県", 5: "秋田県",
    6: "山形県", 7: "福島県", 8: "茨城県", 9: "栃木県", 10: "群馬県",
    11: "埼玉県", 12: "千葉県", 13: "東京都", 14: "神奈川県", 15: "新潟県",
    16: "富山県", 17: "石川県", 18: "福井県", 19: "山梨県", 20: "長野県",
    21: "岐阜県", 22: "静岡県", 23: "愛知県", 24: "三重県", 25: "滋賀県",
    26: "京都府", 27: "大阪府", 28: "兵庫県", 29: "奈良県", 30: "和歌山県",
    31: "鳥取県", 32: "島根県", 33: "岡山県", 34: "広島県", 35: "山口県",
    36: "徳島県", 37: "香川県", 38: "愛媛県", 39: "高知県", 40: "福岡県",
    41: "佐賀県", 42: "長崎県", 43: "熊本県", 44: "大分県", 45: "宮崎県",
    46: "鹿児島県", 47: "沖縄県",
}

_SF_SOQL = """
SELECT
    Name,
    CAREECON_CID__c,
    BillingState,
    BillingCity
FROM Account
WHERE CAREECON_Plus__c = true
  AND CAREECON_Plus_Cancel__c = false
"""

_DS1_SQL = """
SELECT `cid`, `name`, `prefecture_id`, `city`
FROM `companies`
WHERE `deleted_at` IS NULL
"""


_LEGAL_SUFFIXES = re.compile(
    r"株式会社|有限会社|合同会社|合資会社|一般社団法人|特定非営利活動法人"
)


def _normalize(s: str) -> str:
    s = re.sub(r"[\s　]", "", s)
    s = _LEGAL_SUFFIXES.sub("", s)
    return s.lower()


def fetch(client: httpx.Client) -> pd.DataFrame:
    """Plus アクティブ顧客の company_uuid 一覧を返す DataFrame。列: company_uuid"""

    # Step 1: SF Plus active 全件
    sf_rows = redash.run_adhoc_query(client, REDASH.data_sources.sf, _SF_SOQL)
    sf = pd.DataFrame(sf_rows).fillna("")

    confirmed = set(sf.loc[sf["CAREECON_CID__c"] != "", "CAREECON_CID__c"])
    no_cid    = sf[sf["CAREECON_CID__c"] == ""].copy()

    if no_cid.empty:
        return pd.DataFrame({"company_uuid": sorted(confirmed)})

    # Step 2: DS1 companies (住所マッチング用)
    ds1 = pd.DataFrame(
        redash.run_adhoc_query(client, REDASH.data_sources.db, _DS1_SQL)
    ).fillna("")
    ds1["pref"]      = ds1["prefecture_id"].map(_PREF_MAP).fillna("")
    ds1["city_norm"] = ds1["city"].str.strip()
    ds1["name_norm"] = ds1["name"].apply(_normalize)

    # Step 3: 名前 + 住所で段階的突合
    no_cid["name_norm"] = no_cid["Name"].apply(_normalize)
    no_cid["pref"]      = no_cid["BillingState"].str.strip()
    no_cid["city_norm"] = no_cid["BillingCity"].str.strip()

    ref = ds1[["cid", "name_norm", "pref", "city_norm"]].rename(
        columns={"cid": "cas_cid"}
    )

    matched: dict[str, str] = {}  # name_norm → cas_cid

    for on_cols in [
        ["name_norm", "pref", "city_norm"],
        ["name_norm", "pref"],
        ["name_norm"],
    ]:
        rem = no_cid[~no_cid["name_norm"].isin(matched)]
        if rem.empty:
            break
        sub_ref = ref[list({*on_cols, "cas_cid", "name_norm"})].drop_duplicates()
        m = rem.merge(sub_ref, on=on_cols, how="inner")
        cnt = m.groupby("name_norm")["cas_cid"].nunique()
        uniq = m[m["name_norm"].isin(cnt[cnt == 1].index)].drop_duplicates("name_norm")
        for _, row in uniq.iterrows():
            matched[row["name_norm"]] = row["cas_cid"]

    all_uuids = sorted(confirmed | set(matched.values()))
    return pd.DataFrame({"company_uuid": all_uuids})
