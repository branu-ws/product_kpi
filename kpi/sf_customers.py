"""Salesforce Plus アクティブ顧客の company_uuid ホワイトリストを生成する。

フロー:
  1. SF から Plus active アカウントを全件取得
  2. CAREECON_CID__c が設定済み -> そのまま company_uuid として採用
  3. CID 未設定 -> DS1 (careecon_db) の companies テーブルと
     社名 + 住所 (都道府県・市区前方一致) で突合して company_uuid を補填
  4. company_uuid 列のみを持つ DataFrame を返す

マッチング戦略:
  - 社名は NFKC 正規化 (全角→半角) + 法人格 + 記号除去
  - DS1 のマルチバリアント展開: ドメインサフィックス除去・担当者名括弧抽出
  - 市区は SF の BillingCity と DS1 の city で前方一致
    例: SF "朝霞市" vs DS1 "朝霞市宮戸" -> 一致
  - 複数候補がある場合は最初の UUID を採用 (take first)
"""

from __future__ import annotations

import re
import unicodedata

import httpx
import pandas as pd

from kpi import redash
from kpi.config import REDASH

_PREF_MAP = {
    1: "北海道",
    2: "青森県",
    3: "岩手県",
    4: "宮城県",
    5: "秋田県",
    6: "山形県",
    7: "福島県",
    8: "茨城県",
    9: "栃木県",
    10: "群馬県",
    11: "埼玉県",
    12: "千葉県",
    13: "東京都",
    14: "神奈川県",
    15: "新潟県",
    16: "富山県",
    17: "石川県",
    18: "福井県",
    19: "山梨県",
    20: "長野県",
    21: "岐阜県",
    22: "静岡県",
    23: "愛知県",
    24: "三重県",
    25: "滋賀県",
    26: "京都府",
    27: "大阪府",
    28: "兵庫県",
    29: "奈良県",
    30: "和歌山県",
    31: "鳥取県",
    32: "島根県",
    33: "岡山県",
    34: "広島県",
    35: "山口県",
    36: "徳島県",
    37: "香川県",
    38: "愛媛県",
    39: "高知県",
    40: "福岡県",
    41: "佐賀県",
    42: "長崎県",
    43: "熊本県",
    44: "大分県",
    45: "宮崎県",
    46: "鹿児島県",
    47: "沖縄県",
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

_SF_MINI_SOQL = """
SELECT
    Name,
    CAREECON_CID__c,
    BillingState,
    BillingCity
FROM Account
WHERE (CAREECON_mini__c = true OR new_CAREECON_mini__c = true)
  AND ContractStatus__c NOT IN ('解約', '強制解約', '倒産', 'キャンセル')
"""

_DS1_SQL = """
SELECT `cid`, `name`, `prefecture_id`, `city`
FROM `companies`
WHERE `deleted_at` IS NULL
"""

_CAS_ACCOUNTS_SQL = "SELECT cid FROM accounts"

# NFKC 後に残る法人格: 全角括弧は NFKC で ASCII に変換済み
_LEGAL_SUFFIXES = re.compile(
    r"株式会社|有限会社|合同会社|合資会社|一般社団法人|特定非営利活動法人|NPO法人|"
    r"社団法人|財団法人|医療法人|学校法人|宗教法人|協同組合|農業協同組合|事業協同組合|"
    r"\(株\)|\(有\)|\(合\)"
)
_DOMAIN_SUFFIX = re.compile(r"_[A-Za-z0-9\-]+\.[A-Za-z]{2,}$")
# DS1 name の担当者名括弧: 全角と ASCII の両形式にマッチ
_PAREN_CONTENT = re.compile(r"[（(]([^）)]+)[）)]")  # noqa: RUF001
# NFKC 後に除去する記号 (全角括弧/スラッシュは NFKC で ASCII 化済み)
_STRIP_CHARS = re.compile(
    r"[\s\-\.·。、「」『』【】〔〕()/]"  # noqa: RUF001
)


def _normalize(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)  # 全角→半角、㈱→(株) なども変換
    s = _LEGAL_SUFFIXES.sub("", s)
    s = _STRIP_CHARS.sub("", s)
    return s.lower()


def _ds1_name_variants(name: str) -> list[str]:
    """DS1 の社名から複数の正規化バリアントを返す。

    DS1 には「社名_domain.co.jp」「担当者名(社名)_domain.co.jp」のような
    汚れた形式で登録されているケースがある。ドメイン除去・括弧内抽出の
    バリアントを返すことで突合精度を高める。
    """
    variants: set[str] = set()
    variants.add(_normalize(name))
    no_domain = _DOMAIN_SUFFIX.sub("", name)
    variants.add(_normalize(no_domain))
    for m in _PAREN_CONTENT.finditer(no_domain):
        v = _normalize(m.group(1))
        if len(v) >= 4:
            variants.add(v)
    return list(variants)


def _city_prefix_match(sf_city: str, ds1_city: str) -> bool:
    """SF の BillingCity と DS1 の city を前方一致で比較する。

    DS1 の city は「朝霞市宮戸」のように市区名+町名まで含むことがある。
    SF の BillingCity は「朝霞市」止まりのことが多いため、
    どちらかがもう一方の先頭に一致すれば同一市区とみなす。
    """
    a, b = sf_city.strip(), ds1_city.strip()
    return bool(a) and bool(b) and (a.startswith(b) or b.startswith(a))


def _match_step(
    no_cid: pd.DataFrame,
    ref: pd.DataFrame,
    use_pref: bool,
    use_city: bool,
) -> dict[str, str]:
    """name_norm [+ pref [+ city前方一致]] で突合して {name_norm: cas_cid} を返す。

    複数候補がある場合は最初の UUID を採用する。
    """
    result: dict[str, str] = {}
    for _, sf_row in no_cid.iterrows():
        name = sf_row["name_norm"]
        cands = ref[ref["name_norm"] == name]
        if use_pref:
            cands = cands[cands["pref"] == sf_row["pref"]]
        if use_city:
            sf_city = sf_row["city_norm"]
            cands = cands[
                cands["city_norm"].apply(
                    lambda c, sf=sf_city: _city_prefix_match(sf, c)
                )
            ]
        if not cands.empty:
            result[name] = cands["cas_cid"].iloc[0]
    return result


def _fetch(client: httpx.Client, soql: str) -> pd.DataFrame:
    """SOQL で SF から取得した顧客を DS1 突合して返す DataFrame。

    列: company_uuid, sf_company_name
    """

    # Step 1: SF から全件取得
    sf_rows = redash.run_adhoc_query(client, REDASH.data_sources.sf, soql)
    sf = pd.DataFrame(sf_rows).fillna("")

    # SF 社名マップ (CID設定済み)
    sf_names: dict[str, str] = dict(
        zip(
            sf.loc[sf["CAREECON_CID__c"] != "", "CAREECON_CID__c"],
            sf.loc[sf["CAREECON_CID__c"] != "", "Name"],
            strict=True,
        )
    )
    confirmed = set(sf_names.keys())
    no_cid = sf[sf["CAREECON_CID__c"] == ""].copy()

    if no_cid.empty:
        return pd.DataFrame(
            {
                "company_uuid": sorted(confirmed),
                "sf_company_name": [sf_names[u] for u in sorted(confirmed)],
            }
        )

    # Step 2: DS1 companies (住所マッチング用)
    # CAS accounts に存在する UUID のみを候補にすることで
    # DS7 にだけ登録されている別会社への誤マッチを防ぐ
    cas_uuids = {
        r["cid"]
        for r in redash.run_adhoc_query(
            client, REDASH.data_sources.cas, _CAS_ACCOUNTS_SQL
        )
    }
    ds1 = pd.DataFrame(
        redash.run_adhoc_query(client, REDASH.data_sources.db, _DS1_SQL)
    ).fillna("")
    ds1["pref"] = ds1["prefecture_id"].map(_PREF_MAP).fillna("")
    ds1["city_norm"] = ds1["city"].str.strip()
    ds1["name_norm"] = ds1["name"].apply(_normalize)
    _ds1_cas = ds1[ds1["cid"].isin(cas_uuids)].copy()
    extra_rows = []
    for _, row in _ds1_cas.iterrows():
        for v in _ds1_name_variants(row["name"]):
            if v != row["name_norm"]:
                extra_rows.append({**row, "name_norm": v})
    if extra_rows:
        _ds1_cas = pd.concat(
            [_ds1_cas, pd.DataFrame(extra_rows)], ignore_index=True
        ).drop_duplicates(subset="name_norm", keep="first")
    ref = _ds1_cas[["cid", "name_norm", "pref", "city_norm"]].rename(
        columns={"cid": "cas_cid"}
    )

    # Step 3: 名前 + 住所で段階的突合 (精度順、高いものから)
    no_cid["name_norm"] = no_cid["Name"].apply(_normalize)
    no_cid["pref"] = no_cid["BillingState"].str.strip()
    no_cid["city_norm"] = no_cid["BillingCity"].str.strip()
    # name_norm → SF表示名 マップ (マッチング後の社名復元用)
    sf_name_by_norm: dict[str, str] = dict(
        zip(no_cid["name_norm"], no_cid["Name"], strict=True)
    )

    matched: dict[str, str] = {}  # name_norm → cas_cid
    matched_sf_name: dict[str, str] = {}  # cas_cid  → SF表示名

    for use_pref, use_city in [
        (True, True),  # 名前 + 都道府県 + 市区前方一致
        (True, False),  # 名前 + 都道府県
        (False, False),  # 名前のみ
    ]:
        rem = no_cid[~no_cid["name_norm"].isin(matched)]
        if rem.empty:
            break
        step = _match_step(rem, ref, use_pref, use_city)
        matched.update(step)
        for norm, uuid in step.items():
            matched_sf_name[uuid] = sf_name_by_norm.get(norm, "")

    all_uuids = sorted(confirmed | set(matched.values()))
    all_names = [sf_names.get(u) or matched_sf_name.get(u, "") for u in all_uuids]
    return pd.DataFrame({"company_uuid": all_uuids, "sf_company_name": all_names})


def fetch(client: httpx.Client) -> pd.DataFrame:
    """Plus アクティブ顧客を返す DataFrame。列: company_uuid, sf_company_name"""
    return _fetch(client, _SF_SOQL)


def fetch_mini(client: httpx.Client) -> pd.DataFrame:
    """Mini アクティブ顧客を返す DataFrame。列: company_uuid, sf_company_name"""
    return _fetch(client, _SF_MINI_SOQL)
