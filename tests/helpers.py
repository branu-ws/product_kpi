"""テスト補助関数 — 空テーブルファクトリと feature_health 行ビルダ。"""

import pandas as pd

_FH_COLS = [
    "month",
    "company_uuid",
    "company_name",
    "plan_type",
    "is_onboarding",
    "lifecycle_stage",
    "feature",
    "usage_count",
    "health",
]


# ── 空テーブルファクトリ ─────────────────────────────────────────────────────


def empty_lifecycle() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "month": pd.Series([], dtype=str),
            "company_uuid": pd.Series([], dtype=str),
            "company_name": pd.Series([], dtype=str),
            "plan_type": pd.Series([], dtype=str),
            "is_onboarding": pd.Series([], dtype=bool),
            "lifecycle_stage": pd.Series([], dtype=str),
        }
    )


def empty_work_history() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "pid": pd.Series([], dtype="int64"),
            "content": pd.Series([], dtype=str),
            "content_date": pd.Series([], dtype="datetime64[ns]"),
            "source_id": pd.Series([], dtype="int64"),
            "user_id": pd.Series([], dtype="Int64"),
        }
    )


def empty_projects() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "pid": pd.Series([], dtype="int64"),
            "company_uuid": pd.Series([], dtype=str),
        }
    )


def empty_keiei_history() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "company_uuid": pd.Series([], dtype=str),
            "content": pd.Series([], dtype=str),
            "content_date": pd.Series([], dtype="datetime64[ns]"),
        }
    )


def empty_companies() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "company_uuid": pd.Series([], dtype=str),
            "company_name": pd.Series([], dtype=str),
        }
    )


def empty_feature_health() -> pd.DataFrame:
    return pd.DataFrame(columns=_FH_COLS)


# ── feature_health / keiei_feature_health ビルダ ────────────────────────────

#: 稼働日割で clearly good になるカウント (any feature の good_min の 10 倍以上)
HIGH = 200
#: 工程作成(good_min=20)を含む全 work feature で clearly normal になるカウント
#  normal_min_max=5, good_min_min=10 の間 → 6 が安全
MID = 6
#: clearly bad
ZERO = 0


def make_fh(
    uuid: str,
    months: list[str],
    feature_counts: dict[str, int],
    stage: str = "plus",
) -> pd.DataFrame:
    """feature_health DataFrame を生成する。

    feature_counts = {"出面": HIGH, "日報": ZERO, ...}
    """
    rows = [
        {
            "month": month,
            "company_uuid": uuid,
            "company_name": "会社テスト",
            "plan_type": "plus",
            "is_onboarding": stage.startswith("onboarding"),
            "lifecycle_stage": stage,
            "feature": feature,
            "usage_count": count,
            "health": "test",
        }
        for month in months
        for feature, count in feature_counts.items()
    ]
    return pd.DataFrame(rows) if rows else empty_feature_health()


def make_kfh(
    uuid: str,
    months: list[str],
    feature_counts: dict[str, int],
    stage: str = "plus",
) -> pd.DataFrame:
    """keiei_feature_health DataFrame を生成する。"""
    rows = [
        {
            "month": month,
            "company_uuid": uuid,
            "company_name": "会社テスト",
            "plan_type": "plus",
            "is_onboarding": stage.startswith("onboarding"),
            "lifecycle_stage": stage,
            "feature": feature,
            "usage_count": count,
            "health": "test",
        }
        for month in months
        for feature, count in feature_counts.items()
    ]
    return pd.DataFrame(rows) if rows else empty_feature_health()
