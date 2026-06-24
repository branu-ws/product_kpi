"""cross_product.build() のユニットテスト。

テストデータの count 選択方針:
  avg_days ≈ working_days (テスト月はすべて完了月) であるため
  count/working_days ≈ count/avg_days と近似できる。これを利用して

  HIGH = 200  → 全 work/keiei feature で clearly good  (score=2)
  ZERO =   0  → clearly bad  (score=0)
"""

import pandas as pd

from kpi import cross_product
from kpi.config import TIER
from tests.helpers import (
    HIGH,
    ZERO,
    empty_companies,
    empty_keiei_history,
    empty_lifecycle,
    empty_projects,
    empty_work_history,
    make_fh,
    make_kfh,
)

_UUID = "aaaa-0001"
_MONTHS = ["2024-01", "2024-02", "2024-03"]


def _register(conn, fh: pd.DataFrame, kfh: pd.DataFrame) -> None:
    conn.register("feature_health", fh)
    conn.register("keiei_feature_health", kfh)
    conn.register("customer_lifecycle", empty_lifecycle())
    conn.register("companies", empty_companies())
    conn.register("work_user_history", empty_work_history())
    conn.register("work_process_id_generator", empty_projects())
    conn.register("keiei_user_history", empty_keiei_history())


# ── integration_tier ──────────────────────────────────────────────────────────


class TestIntegrationTier:
    def test_fan_when_both_products_used_3_months(self, conn):
        fh = make_fh(_UUID, _MONTHS, {"出面": HIGH})
        kfh = make_kfh(_UUID, _MONTHS, {"案件ステータス更新": HIGH})
        _register(conn, fh, kfh)

        monthly, _ = cross_product.build(conn)
        last = monthly[monthly["usage_month"] == "2024-03"]
        assert last.iloc[0]["integration_tier"] == "fan"

    def test_proactive_when_only_work_used_3_months(self, conn):
        # keiei ゼロ → proactive (work のみ)
        fh = make_fh(_UUID, _MONTHS, {"出面": HIGH})
        kfh = make_kfh(_UUID, _MONTHS, {"案件ステータス更新": ZERO})
        _register(conn, fh, kfh)

        monthly, _ = cross_product.build(conn)
        last = monthly[monthly["usage_month"] == "2024-03"]
        assert last.iloc[0]["integration_tier"] == "proactive"

    def test_proactive_when_only_keiei_used_3_months(self, conn):
        # work ゼロ → proactive (keiei のみ)
        fh = make_fh(_UUID, _MONTHS, {"出面": ZERO})
        kfh = make_kfh(_UUID, _MONTHS, {"案件ステータス更新": HIGH})
        _register(conn, fh, kfh)

        monthly, _ = cross_product.build(conn)
        last = monthly[monthly["usage_month"] == "2024-03"]
        assert last.iloc[0]["integration_tier"] == "proactive"

    def test_passive_when_window_less_than_3_months(self, conn):
        # 2ヶ月のみ → window_size=2 < rolling_months=3 → passive
        fh = make_fh(_UUID, ["2024-01", "2024-02"], {"出面": HIGH})
        kfh = make_kfh(_UUID, ["2024-01", "2024-02"], {"案件ステータス更新": HIGH})
        _register(conn, fh, kfh)

        monthly, _ = cross_product.build(conn)
        last = monthly[monthly["usage_month"] == "2024-02"]
        assert last.iloc[0]["integration_tier"] == "passive"

    def test_passive_when_neither_product_used(self, conn):
        # 3ヶ月あっても両スコアゼロ → passive
        fh = make_fh(_UUID, _MONTHS, {"出面": ZERO})
        kfh = make_kfh(_UUID, _MONTHS, {"案件ステータス更新": ZERO})
        _register(conn, fh, kfh)

        monthly, _ = cross_product.build(conn)
        last = monthly[monthly["usage_month"] == "2024-03"]
        assert last.iloc[0]["integration_tier"] == "passive"

    def test_onboarding_overrides_tier(self, conn):
        # fan 条件を満たしていても onboarding-plus → onboarding
        fh = make_fh(_UUID, _MONTHS, {"出面": HIGH}, stage="onboarding-plus")
        kfh = make_kfh(
            _UUID, _MONTHS, {"案件ステータス更新": HIGH}, stage="onboarding-plus"
        )
        _register(conn, fh, kfh)

        monthly, _ = cross_product.build(conn)
        assert (monthly["integration_tier"] == "onboarding").all()

    def test_fan_requires_all_rolling_months(self, conn):
        # 2024-01/02 は work ゼロ、2024-03 だけ HIGH → 3ヶ月連続を満たさない → not fan
        fh = pd.concat(
            [
                make_fh(_UUID, ["2024-01", "2024-02"], {"出面": ZERO}),
                make_fh(_UUID, ["2024-03"], {"出面": HIGH}),
            ]
        )
        kfh = make_kfh(_UUID, _MONTHS, {"案件ステータス更新": HIGH})
        _register(conn, fh, kfh)

        monthly, _ = cross_product.build(conn)
        last = monthly[monthly["usage_month"] == "2024-03"]
        assert last.iloc[0]["integration_tier"] != "fan"

    def test_first_month_always_passive(self, conn):
        # 1ヶ月目は window_size=1 → 常に passive (onboarding でない限り)
        fh = make_fh(_UUID, _MONTHS, {"出面": HIGH})
        kfh = make_kfh(_UUID, _MONTHS, {"案件ステータス更新": HIGH})
        _register(conn, fh, kfh)

        monthly, _ = cross_product.build(conn)
        first = monthly[monthly["usage_month"] == "2024-01"]
        assert first.iloc[0]["integration_tier"] == "passive"


# ── usage_freq ────────────────────────────────────────────────────────────────


class TestUsageFreq:
    def test_good_when_total_score_gte_5(self, conn):
        # work: 3 features xHIGH (score=2) = 6, keiei: 0 → total=6 ≥ 5 → good
        fh = make_fh(_UUID, ["2024-01"], {"出面": HIGH, "日報": HIGH, "報告書": HIGH})
        kfh = make_kfh(_UUID, ["2024-01"], {"案件ステータス更新": ZERO})
        _register(conn, fh, kfh)

        monthly, _ = cross_product.build(conn)
        assert monthly.iloc[0]["usage_freq"] == "good"

    def test_normal_when_total_score_in_normal_range(self, conn):
        # 1 HIGH work feature → work_score=2, total=2
        # Precondition: score=2 must be in [usage_freq_normal, usage_freq_good)
        assert TIER.usage_freq_normal <= 2 < TIER.usage_freq_good, (
            f"Config changed (normal={TIER.usage_freq_normal}, "
            f"good={TIER.usage_freq_good}): update test data setup"
        )
        fh = make_fh(_UUID, ["2024-01"], {"出面": HIGH})
        kfh = make_kfh(_UUID, ["2024-01"], {"案件ステータス更新": ZERO})
        _register(conn, fh, kfh)

        monthly, _ = cross_product.build(conn)
        assert monthly.iloc[0]["usage_freq"] == "normal"

    def test_bad_when_total_score_below_normal(self, conn):
        # ZERO for all → total=0 < usage_freq_normal → bad
        fh = make_fh(_UUID, ["2024-01"], {"出面": ZERO})
        kfh = make_kfh(_UUID, ["2024-01"], {"案件ステータス更新": ZERO})
        _register(conn, fh, kfh)

        monthly, _ = cross_product.build(conn)
        assert monthly.iloc[0]["total_score"] < TIER.usage_freq_normal
        assert monthly.iloc[0]["usage_freq"] == "bad"

    def test_work_and_keiei_scores_summed(self, conn):
        # work: 1 feature = 2, keiei: 2 features = 4 → total=6 → good
        fh = make_fh(_UUID, ["2024-01"], {"出面": HIGH})
        kfh = make_kfh(
            _UUID,
            ["2024-01"],
            {"案件ステータス更新": HIGH, "見積原価登録": HIGH},
        )
        _register(conn, fh, kfh)

        monthly, _ = cross_product.build(conn)
        assert monthly.iloc[0]["total_score"] == 6
        assert monthly.iloc[0]["usage_freq"] == "good"

    def test_total_score_at_normal_boundary(self, conn):
        # 1 HIGH work (score=2) + ZERO keiei → total=2 = usage_freq_normal
        # Precondition: 1 HIGH feature must produce exactly usage_freq_normal
        assert TIER.usage_freq_normal == 2, (
            f"Config changed (normal={TIER.usage_freq_normal}): update test data setup"
        )
        fh = make_fh(_UUID, ["2024-01"], {"出面": HIGH})
        kfh = make_kfh(_UUID, ["2024-01"], {"案件ステータス更新": ZERO})
        _register(conn, fh, kfh)

        monthly, _ = cross_product.build(conn)
        assert monthly.iloc[0]["total_score"] == TIER.usage_freq_normal
        assert monthly.iloc[0]["usage_freq"] == "normal"


# ── 週次結果のスキーマ確認 ────────────────────────────────────────────────────


class TestWeeklySchema:
    def test_weekly_returns_dataframe(self, conn):
        # 空の週次テーブルでも DataFrame を返す
        fh = make_fh(_UUID, _MONTHS, {"出面": HIGH})
        kfh = make_kfh(_UUID, _MONTHS, {"案件ステータス更新": HIGH})
        _register(conn, fh, kfh)

        _, weekly = cross_product.build(conn)
        assert isinstance(weekly, pd.DataFrame)
        expected_cols = {
            "week_start",
            "company_uuid",
            "work_score",
            "keiei_score",
            "usage_freq",
            "integration_tier",
        }
        assert expected_cols <= set(weekly.columns)
