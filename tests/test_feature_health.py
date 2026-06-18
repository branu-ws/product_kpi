"""feature_health.build() のユニットテスト。"""

import duckdb
import pandas as pd
import pytest

from kpi import feature_health


@pytest.fixture()
def conn():
    c = duckdb.connect()
    yield c
    c.close()


def _make_lifecycle(uuid, month, stage="plus"):
    return pd.DataFrame(
        {
            "usage_month": [month],
            "company_uuid": [uuid],
            "company_name": ["テスト会社"],
            "plan_type": ["plus"],
            "is_onboarding": [False],
            "lifecycle_stage": [stage],
        }
    )


def _make_history(pid, content, month, count=1):
    df = pd.DataFrame(
        {
            "pid": [pid] * count,
            "content": [content] * count,
            "content_date": [f"{month}-01"] * count,
        }
    )
    df["content_date"] = pd.to_datetime(df["content_date"])
    return df


def _make_projects(pid, uuid):
    return pd.DataFrame({"pid": [pid], "company_uuid": [uuid]})


def _make_companies(uuid):
    return pd.DataFrame({"company_uuid": [uuid], "company_name": ["テスト会社"]})


class TestHealthThreshold:
    def test_good_at_boundary(self, conn):
        uuid, pid, month = "aaaa", 1, "2024-01"
        conn.register("customer_lifecycle", _make_lifecycle(uuid, month))
        conn.register("work_user_history", _make_history(pid, "出面", month, count=10))
        conn.register("work_process_id_generator", _make_projects(pid, uuid))
        conn.register("companies", _make_companies(uuid))

        df = feature_health.build(conn)
        row = df[(df["feature"] == "出面") & (df["usage_month"] == month)]
        assert row.iloc[0]["health"] == "good"

    def test_normal_at_boundary(self, conn):
        uuid, pid, month = "aaaa", 1, "2024-01"
        conn.register("customer_lifecycle", _make_lifecycle(uuid, month))
        conn.register("work_user_history", _make_history(pid, "出面", month, count=3))
        conn.register("work_process_id_generator", _make_projects(pid, uuid))
        conn.register("companies", _make_companies(uuid))

        df = feature_health.build(conn)
        row = df[(df["feature"] == "出面") & (df["usage_month"] == month)]
        assert row.iloc[0]["health"] == "normal"

    def test_good_minus_1_is_normal(self, conn):
        uuid, pid, month = "aaaa", 1, "2024-01"
        conn.register("customer_lifecycle", _make_lifecycle(uuid, month))
        conn.register("work_user_history", _make_history(pid, "出面", month, count=9))
        conn.register("work_process_id_generator", _make_projects(pid, uuid))
        conn.register("companies", _make_companies(uuid))

        df = feature_health.build(conn)
        row = df[(df["feature"] == "出面") & (df["usage_month"] == month)]
        assert row.iloc[0]["health"] == "normal"

    def test_bad_below_normal(self, conn):
        uuid, pid, month = "aaaa", 1, "2024-01"
        conn.register("customer_lifecycle", _make_lifecycle(uuid, month))
        conn.register("work_user_history", _make_history(pid, "出面", month, count=2))
        conn.register("work_process_id_generator", _make_projects(pid, uuid))
        conn.register("companies", _make_companies(uuid))

        df = feature_health.build(conn)
        row = df[(df["feature"] == "出面") & (df["usage_month"] == month)]
        assert row.iloc[0]["health"] == "bad"

    def test_kouteisakusei_good_threshold_is_20(self, conn):
        uuid, pid, month = "aaaa", 1, "2024-01"
        conn.register("customer_lifecycle", _make_lifecycle(uuid, month))
        history = pd.concat(
            [
                _make_history(pid, "大工程", month, count=10),
                _make_history(pid, "小工程", month, count=10),
            ]
        )
        conn.register("work_user_history", history)
        conn.register("work_process_id_generator", _make_projects(pid, uuid))
        conn.register("companies", _make_companies(uuid))

        df = feature_health.build(conn)
        row = df[(df["feature"] == "工程作成") & (df["usage_month"] == month)]
        assert row.iloc[0]["health"] == "good"
        assert row.iloc[0]["usage_count"] == 20


class TestZeroUsageFill:
    def test_missing_usage_filled_as_bad(self, conn):
        uuid, pid, month = "aaaa", 1, "2024-01"
        conn.register("customer_lifecycle", _make_lifecycle(uuid, month))
        conn.register(
            "work_user_history",
            pd.DataFrame(
                {
                    "pid": [pid],
                    "content": ["出面"],
                    "content_date": pd.to_datetime([f"{month}-01"]),
                }
            ),
        )
        conn.register("work_process_id_generator", _make_projects(pid, uuid))
        conn.register("companies", _make_companies(uuid))

        df = feature_health.build(conn)
        no_usage = df[(df["feature"] == "日報") & (df["usage_month"] == month)]
        assert no_usage.iloc[0]["usage_count"] == 0
        assert no_usage.iloc[0]["health"] == "bad"

    def test_retired_excluded(self, conn):
        uuid, pid, month = "aaaa", 1, "2024-01"
        conn.register(
            "customer_lifecycle", _make_lifecycle(uuid, month, stage="retired")
        )
        conn.register("work_user_history", _make_history(pid, "出面", month, count=10))
        conn.register("work_process_id_generator", _make_projects(pid, uuid))
        conn.register("companies", _make_companies(uuid))

        df = feature_health.build(conn)
        assert len(df) == 0
