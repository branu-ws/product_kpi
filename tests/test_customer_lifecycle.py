"""customer_lifecycle.build() のユニットテスト。"""

import pandas as pd

from kpi import customer_lifecycle


def _register(conn, companies, contracts, history):
    conn.register("companies", companies)
    conn.register("contracts", contracts)
    conn.register("work_user_history", history)


def _companies(*uuids):
    return pd.DataFrame(
        {
            "company_uuid": list(uuids),
            "company_name": [f"会社{i}" for i in range(len(uuids))],
        }
    )


def _history(*months):
    df = pd.DataFrame(
        {
            "content_date": [f"{m}-01" for m in months],
            "pid": [1] * len(months),
            "content": ["x"] * len(months),
        }
    )
    df["content_date"] = pd.to_datetime(df["content_date"])
    return df


def _contract(uuid, plan, start, end=None, status="active"):
    return {
        "company_uuid": uuid,
        "plan_type": plan,
        "start_date": pd.Timestamp(start),
        "end_date": pd.Timestamp(end) if end else pd.NaT,
        "status": status,
    }


class TestOnboarding:
    def test_within_3_months_is_onboarding(self, conn):
        uuid = "aaaa"
        _register(
            conn,
            _companies(uuid),
            pd.DataFrame([_contract(uuid, "plus", "2024-01-01")]),
            _history("2024-01", "2024-02", "2024-03"),
        )
        df = customer_lifecycle.build(conn)
        assert df[df["month"] == "2024-01"]["is_onboarding"].all()
        assert df[df["month"] == "2024-02"]["is_onboarding"].all()
        assert df[df["month"] == "2024-03"]["is_onboarding"].all()

    def test_month_4_is_not_onboarding(self, conn):
        uuid = "aaaa"
        _register(
            conn,
            _companies(uuid),
            pd.DataFrame([_contract(uuid, "plus", "2024-01-01")]),
            _history("2024-01", "2024-02", "2024-03", "2024-04"),
        )
        df = customer_lifecycle.build(conn)
        assert not df[df["month"] == "2024-04"]["is_onboarding"].any()

    def test_lifecycle_stage_onboarding_plus(self, conn):
        uuid = "aaaa"
        _register(
            conn,
            _companies(uuid),
            pd.DataFrame([_contract(uuid, "plus", "2024-01-01")]),
            _history("2024-01"),
        )
        df = customer_lifecycle.build(conn)
        assert (df["lifecycle_stage"] == "onboarding-plus").all()

    def test_lifecycle_stage_plus_after_onboarding(self, conn):
        uuid = "aaaa"
        _register(
            conn,
            _companies(uuid),
            pd.DataFrame([_contract(uuid, "plus", "2024-01-01")]),
            _history("2024-04"),
        )
        df = customer_lifecycle.build(conn)
        assert (df["lifecycle_stage"] == "plus").all()

    def test_lifecycle_stage_onboarding_mini(self, conn):
        uuid = "aaaa"
        _register(
            conn,
            _companies(uuid),
            pd.DataFrame([_contract(uuid, "mini", "2024-01-01")]),
            _history("2024-01"),
        )
        df = customer_lifecycle.build(conn)
        assert (df["lifecycle_stage"] == "onboarding-mini").all()

    def test_lifecycle_stage_mini_after_onboarding(self, conn):
        uuid = "aaaa"
        _register(
            conn,
            _companies(uuid),
            pd.DataFrame([_contract(uuid, "mini", "2024-01-01")]),
            _history("2024-04"),
        )
        df = customer_lifecycle.build(conn)
        assert (df["lifecycle_stage"] == "mini").all()


class TestPlusPriority:
    def test_plus_wins_over_mini_same_month(self, conn):
        uuid = "aaaa"
        contracts = pd.DataFrame(
            [
                _contract(uuid, "mini", "2024-01-01"),
                _contract(uuid, "plus", "2024-01-01"),
            ]
        )
        _register(conn, _companies(uuid), contracts, _history("2024-01"))
        df = customer_lifecycle.build(conn)
        assert len(df[df["month"] == "2024-01"]) == 1
        assert df.iloc[0]["plan_type"] == "plus"


class TestRetired:
    def test_finished_contract_becomes_retired(self, conn):
        uuid = "aaaa"
        contracts = pd.DataFrame(
            [_contract(uuid, "plus", "2024-01-01", "2024-02-28", "finished")]
        )
        _register(
            conn, _companies(uuid), contracts, _history("2024-01", "2024-02", "2024-03")
        )
        df = customer_lifecycle.build(conn)
        stage = df[df["month"] == "2024-03"]["lifecycle_stage"]
        assert (stage == "retired").all()

    def test_active_contract_is_not_retired(self, conn):
        uuid = "aaaa"
        _register(
            conn,
            _companies(uuid),
            pd.DataFrame([_contract(uuid, "plus", "2024-01-01")]),
            _history("2024-01"),
        )
        df = customer_lifecycle.build(conn)
        assert "retired" not in df["lifecycle_stage"].values
