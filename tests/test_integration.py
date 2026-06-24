"""全 KPI モジュールの E2E インテグレーションテスト。

外部サービス (Redash / BigQuery / Notion) には接触せず、合成データで
  customer_lifecycle → feature_health → single_product / cross_product
のパイプライン全体が連結して動作することを確認する。
"""

import pandas as pd
import pytest

from kpi import cross_product, customer_lifecycle, feature_health, single_product


def _make_companies(*uuids: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "company_uuid": list(uuids),
            "company_name": [f"会社{i}" for i in range(len(uuids))],
        }
    )


def _make_contracts(uuid: str, plan: str = "plus", start: str = "2023-10-01") -> dict:
    return {
        "company_uuid": uuid,
        "plan_type": plan,
        "start_date": pd.Timestamp(start),
        "end_date": pd.NaT,
        "status": "active",
    }


def _make_work_history(pid: int, months: list[str], count: int = 15) -> pd.DataFrame:
    rows = [
        {"pid": pid, "content": "出面", "content_date": pd.Timestamp(f"{m}-15")}
        for m in months
        for _ in range(count)
    ]
    return pd.DataFrame(rows)


@pytest.fixture()
def pipeline_conn(conn):
    """full pipeline 用テーブルをセットアップ済みの DuckDB 接続を返す。"""
    uuid = "uuid-pipeline"
    pid = 999
    months = [f"2024-0{i}" for i in range(1, 7)]

    conn.register("companies", _make_companies(uuid))
    conn.register("contracts", pd.DataFrame([_make_contracts(uuid)]))
    conn.register("work_user_history", _make_work_history(pid, months))
    conn.register(
        "work_process_id_generator",
        pd.DataFrame({"pid": [pid], "company_uuid": [uuid]}),
    )
    conn.register(
        "keiei_user_history",
        pd.DataFrame(
            {
                "company_uuid": pd.Series([], dtype=str),
                "content": pd.Series([], dtype=str),
                "content_date": pd.Series([], dtype="datetime64[ns]"),
            }
        ),
    )

    lifecycle_df = customer_lifecycle.build(conn)
    conn.register("customer_lifecycle", lifecycle_df)

    fh_df = feature_health.build(conn)
    conn.register("feature_health", fh_df)

    empty_kfh = pd.DataFrame(
        columns=[
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
    )
    conn.register("keiei_feature_health", empty_kfh)

    return conn


class TestSingleProductPipeline:
    def test_monthly_schema(self, pipeline_conn):
        monthly, _ = single_product.build_work(pipeline_conn)

        required = {
            "usage_month",
            "company_uuid",
            "company_name",
            "diversity_tier",
            "usage_freq",
            "feature_score",
        }
        assert required <= set(monthly.columns)

    def test_monthly_has_rows(self, pipeline_conn):
        monthly, _ = single_product.build_work(pipeline_conn)
        assert len(monthly) > 0

    def test_diversity_tier_values_are_valid(self, pipeline_conn):
        monthly, _ = single_product.build_work(pipeline_conn)
        valid = {"fan", "proactive", "passive", "onboarding"}
        assert set(monthly["diversity_tier"].unique()) <= valid

    def test_usage_freq_values_are_valid(self, pipeline_conn):
        monthly, _ = single_product.build_work(pipeline_conn)
        valid = {"good", "normal", "bad"}
        assert set(monthly["usage_freq"].unique()) <= valid

    def test_weekly_schema(self, pipeline_conn):
        _, weekly = single_product.build_work(pipeline_conn)

        required = {
            "week_start",
            "company_uuid",
            "feature_score",
            "usage_freq",
            "diversity_tier",
        }
        assert required <= set(weekly.columns)

    def test_lifecycle_stages_flow_into_diversity_tier(self, pipeline_conn):
        # 6ヶ月以上のデータがあれば onboarding 後に plus ステージへ移行している
        monthly, _ = single_product.build_work(pipeline_conn)
        stages = set(monthly["diversity_tier"].unique())
        # fan/proactive/passive のいずれかが含まれている
        assert stages & {"fan", "proactive", "passive"}


class TestCrossProductPipeline:
    def test_monthly_schema(self, pipeline_conn):
        monthly, _ = cross_product.build(pipeline_conn)

        required = {
            "usage_month",
            "company_uuid",
            "company_name",
            "work_score",
            "keiei_score",
            "total_score",
            "integration_tier",
            "usage_freq",
        }
        assert required <= set(monthly.columns)

    def test_monthly_has_rows(self, pipeline_conn):
        monthly, _ = cross_product.build(pipeline_conn)
        assert len(monthly) > 0

    def test_integration_tier_values_are_valid(self, pipeline_conn):
        monthly, _ = cross_product.build(pipeline_conn)
        valid = {"fan", "proactive", "passive", "onboarding"}
        assert set(monthly["integration_tier"].unique()) <= valid

    def test_keiei_score_zero_with_empty_keiei_history(self, pipeline_conn):
        # keiei_user_history が空なので keiei_score は常に 0
        monthly, _ = cross_product.build(pipeline_conn)
        assert (monthly["keiei_score"] == 0).all()

    def test_total_score_equals_work_plus_keiei(self, pipeline_conn):
        monthly, _ = cross_product.build(pipeline_conn)
        assert (
            monthly["total_score"] == monthly["work_score"] + monthly["keiei_score"]
        ).all()


class TestPipelineConsistency:
    def test_months_align_between_lifecycle_and_single_product(self, pipeline_conn):
        lifecycle_df = (
            pipeline_conn.sql(
                "SELECT DISTINCT month FROM customer_lifecycle ORDER BY month"
            )
            .df()["month"]
            .tolist()
        )

        monthly, _ = single_product.build_work(pipeline_conn)
        sp_months = sorted(monthly["usage_month"].unique().tolist())

        # single_product の月は customer_lifecycle の月に含まれる
        assert set(sp_months) <= set(lifecycle_df)

    def test_feature_score_non_negative(self, pipeline_conn):
        monthly, _ = single_product.build_work(pipeline_conn)
        assert (monthly["feature_score"] >= 0).all()
