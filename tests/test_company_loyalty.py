"""company_loyalty.build() のユニットテスト — 各ティア境界値。"""

import duckdb
import pandas as pd
import pytest

from kpi import company_loyalty


@pytest.fixture()
def conn():
    c = duckdb.connect()
    yield c
    c.close()


def _feature_health(uuid, months, good=0, normal=0):
    """指定した月数分の feature_health 行を生成する。"""
    rows = []
    for month in months:
        for i in range(good):
            rows.append(
                {
                    "usage_month": month,
                    "company_uuid": uuid,
                    "company_name": "テスト",
                    "plan_type": "plus",
                    "is_onboarding": False,
                    "lifecycle_stage": "plus",
                    "feature": f"機能G{i}",
                    "usage_count": 20,
                    "health": "good",
                }
            )
        for i in range(normal):
            rows.append(
                {
                    "usage_month": month,
                    "company_uuid": uuid,
                    "company_name": "テスト",
                    "plan_type": "plus",
                    "is_onboarding": False,
                    "lifecycle_stage": "plus",
                    "feature": f"機能N{i}",
                    "usage_count": 5,
                    "health": "normal",
                }
            )
        bad_count = max(0, 6 - good - normal)
        for i in range(bad_count):
            rows.append(
                {
                    "usage_month": month,
                    "company_uuid": uuid,
                    "company_name": "テスト",
                    "plan_type": "plus",
                    "is_onboarding": False,
                    "lifecycle_stage": "plus",
                    "feature": f"機能B{i}",
                    "usage_count": 0,
                    "health": "bad",
                }
            )
    return pd.DataFrame(rows)


def _history(uuid, months, count=1):
    rows = [
        {"pid": 1, "content": "出面", "content_date": f"{m}-01"}
        for m in months
        for _ in range(count)
    ]
    df = pd.DataFrame(rows)
    df["content_date"] = pd.to_datetime(df["content_date"])
    return df


def _projects(uuid):
    return pd.DataFrame({"pid": [1], "company_uuid": [uuid]})


def _register(conn, uuid, months, good=0, normal=0, usage_count=1):
    conn.register("feature_health", _feature_health(uuid, months, good, normal))
    conn.register("work_user_history", _history(uuid, months, usage_count))
    conn.register("work_process_id_generator", _projects(uuid))


def _tier(conn, uuid, month):
    df = company_loyalty.build(conn)
    mask = (df["company_uuid"] == uuid) & (df["usage_month"] == month)
    return df[mask].iloc[0]["loyalty_tier"]


class TestGod:
    def test_god_requires_good5_for_3months(self, conn):
        uuid = "aaaa"
        months = ["2024-01", "2024-02", "2024-03"]
        _register(conn, uuid, months, good=5)
        assert _tier(conn, uuid, "2024-03") == "神"

    def test_god_fails_with_good4(self, conn):
        uuid = "aaaa"
        months = ["2024-01", "2024-02", "2024-03"]
        _register(conn, uuid, months, good=4)
        assert _tier(conn, uuid, "2024-03") != "神"

    def test_god_fails_with_only_2months(self, conn):
        uuid = "aaaa"
        months = ["2024-01", "2024-02"]
        _register(conn, uuid, months, good=5)
        assert _tier(conn, uuid, "2024-02") != "神"


class TestFan:
    def test_fan_requires_good2_for_3months(self, conn):
        uuid = "aaaa"
        months = ["2024-01", "2024-02", "2024-03"]
        _register(conn, uuid, months, good=2)
        assert _tier(conn, uuid, "2024-03") == "ファン"

    def test_fan_fails_with_good1(self, conn):
        uuid = "aaaa"
        months = ["2024-01", "2024-02", "2024-03"]
        _register(conn, uuid, months, good=1)
        assert _tier(conn, uuid, "2024-03") not in ("神", "ファン")


class TestJisou:
    def test_jisou_requires_good1_for_2months(self, conn):
        uuid = "aaaa"
        months = ["2024-01", "2024-02"]
        _register(conn, uuid, months, good=1)
        assert _tier(conn, uuid, "2024-02") == "自走"

    def test_jisou_fails_with_1month(self, conn):
        uuid = "aaaa"
        months = ["2024-01"]
        _register(conn, uuid, months, good=1)
        assert _tier(conn, uuid, "2024-01") not in ("神", "ファン", "自走")


class TestDansoku:
    def test_2month_continuous_requires_normal1_for_2months(self, conn):
        uuid = "aaaa"
        months = ["2024-01", "2024-02"]
        _register(conn, uuid, months, good=0, normal=1)
        assert _tier(conn, uuid, "2024-02") == "2か月連続活用"


class TestDansokukatsu:
    def test_dansokukatsu_with_good1_single_month(self, conn):
        uuid = "aaaa"
        months = ["2024-01"]
        _register(conn, uuid, months, good=1)
        assert _tier(conn, uuid, "2024-01") == "断続的活用"

    def test_dansokukatsu_with_normal1_single_month(self, conn):
        uuid = "aaaa"
        months = ["2024-01"]
        _register(conn, uuid, months, good=0, normal=1)
        assert _tier(conn, uuid, "2024-01") == "断続的活用"


class TestMazui:
    def test_mazui_when_all_bad(self, conn):
        uuid = "aaaa"
        months = ["2024-01"]
        _register(conn, uuid, months, good=0, normal=0, usage_count=1)
        assert _tier(conn, uuid, "2024-01") == "まずい"


class TestRihan:
    def test_rihan_requires_zero_usage_for_3months(self, conn):
        uuid = "aaaa"
        months = ["2024-01", "2024-02", "2024-03"]
        conn.register("feature_health", _feature_health(uuid, months, good=0, normal=0))
        conn.register(
            "work_user_history",
            pd.DataFrame(
                {
                    "pid": [1],
                    "content": ["出面"],
                    "content_date": pd.to_datetime(["2024-01-01"]),
                }
            ),
        )
        conn.register("work_process_id_generator", _projects(uuid))
        assert _tier(conn, uuid, "2024-03") == "離反状態"
