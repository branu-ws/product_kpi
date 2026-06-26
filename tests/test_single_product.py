"""single_product.build_work() / build_keiei() のユニットテスト。

count 選択方針 (cross_product と同じ):
  HIGH = 200  → 稼働日割で clearly good  (score=2, normal_plus_count に加算)
  MID  =   6  → 工程作成含む全 work feature で clearly normal  (score=1)
  ZERO =   0  → clearly bad  (score=0)
"""

import pandas as pd

from kpi import single_product
from kpi.config import TIER
from tests.helpers import (
    HIGH,
    MID,
    ZERO,
    empty_companies,
    empty_keiei_history,
    empty_lifecycle,
    empty_projects,
    empty_work_history,
    make_fh,
    make_kfh,
)

_UUID = "bbbb-0002"
_MONTHS = ["2024-01", "2024-02", "2024-03", "2024-04"]


def _register_work(conn, fh: pd.DataFrame) -> None:
    conn.register("feature_health", fh)
    conn.register("customer_lifecycle", empty_lifecycle())
    conn.register("companies", empty_companies())
    conn.register("work_user_history", empty_work_history())
    conn.register("work_process_id_generator", empty_projects())


def _register_keiei(conn, kfh: pd.DataFrame) -> None:
    conn.register("keiei_feature_health", kfh)
    conn.register("customer_lifecycle", empty_lifecycle())
    conn.register("companies", empty_companies())
    conn.register("keiei_user_history", empty_keiei_history())


# ── diversity_tier (work) ─────────────────────────────────────────────────────


class TestWorkDiversityTier:
    def test_fan_when_2_features_normal_plus_3_months(self, conn):
        # 出面(HIGH)+日報(HIGH) × 4ヶ月 → 4ヶ月目のTierは直前3完了月で判定 → fan
        fh = make_fh(_UUID, _MONTHS, {"出面": HIGH, "日報": HIGH})
        _register_work(conn, fh)

        monthly, _ = single_product.build_work(conn)
        last = monthly[monthly["usage_month"] == "2024-04"]
        assert last.iloc[0]["diversity_tier"] == "fan"

    def test_proactive_when_1_feature_normal_plus_3_months(self, conn):
        # 出面(HIGH)のみ × 4ヶ月 → 4ヶ月目のTierは直前3完了月で判定 → proactive
        fh = make_fh(_UUID, _MONTHS, {"出面": HIGH})
        _register_work(conn, fh)

        monthly, _ = single_product.build_work(conn)
        last = monthly[monthly["usage_month"] == "2024-04"]
        assert last.iloc[0]["diversity_tier"] == "proactive"

    def test_passive_when_no_feature_normal_plus(self, conn):
        # 全機能ゼロ → normal_plus_count=0 < pro_min=1 → passive
        fh = make_fh(_UUID, _MONTHS, {"出面": ZERO})
        _register_work(conn, fh)

        monthly, _ = single_product.build_work(conn)
        last = monthly[monthly["usage_month"] == "2024-03"]
        assert last.iloc[0]["diversity_tier"] == "passive"

    def test_passive_when_window_less_than_3_months(self, conn):
        # 2ヶ月のみ → window_size=2 < rolling_months=3 → passive
        fh = make_fh(_UUID, ["2024-01", "2024-02"], {"出面": HIGH, "日報": HIGH})
        _register_work(conn, fh)

        monthly, _ = single_product.build_work(conn)
        last = monthly[monthly["usage_month"] == "2024-02"]
        assert last.iloc[0]["diversity_tier"] == "passive"

    def test_onboarding_overrides_tier(self, conn):
        # fan 条件を満たしていても onboarding-plus → onboarding
        fh = make_fh(
            _UUID, _MONTHS, {"出面": HIGH, "日報": HIGH}, stage="onboarding-plus"
        )
        _register_work(conn, fh)

        monthly, _ = single_product.build_work(conn)
        assert (monthly["diversity_tier"] == "onboarding").all()

    def test_first_month_is_passive(self, conn):
        # 1ヶ月目は window_size=1 → passive
        fh = make_fh(_UUID, _MONTHS, {"出面": HIGH, "日報": HIGH})
        _register_work(conn, fh)

        monthly, _ = single_product.build_work(conn)
        first = monthly[monthly["usage_month"] == "2024-01"]
        assert first.iloc[0]["diversity_tier"] == "passive"

    def test_fan_requires_fan_min_features_all_months(self, conn):
        # 2024-03 だけ1機能 normal+ → fan_all3=0 → proactive (not fan)
        fh = pd.concat(
            [
                make_fh(_UUID, ["2024-01", "2024-02"], {"出面": HIGH, "日報": HIGH}),
                make_fh(_UUID, ["2024-03"], {"出面": HIGH}),
            ]
        )
        _register_work(conn, fh)

        monthly, _ = single_product.build_work(conn)
        last = monthly[monthly["usage_month"] == "2024-03"]
        assert last.iloc[0]["diversity_tier"] != "fan"

    def test_mid_usage_counts_as_normal_plus(self, conn):
        # MID (clearly normal) → normal_plus_count に加算される
        fh = make_fh(_UUID, _MONTHS, {"出面": MID, "日報": MID})
        _register_work(conn, fh)

        monthly, _ = single_product.build_work(conn)
        last = monthly[monthly["usage_month"] == "2024-04"]
        # MID は both features で normal → normal_plus_count=2 → fan ✓
        assert last.iloc[0]["diversity_tier"] == "fan"


# ── usage_freq (work) ─────────────────────────────────────────────────────────


class TestWorkUsageFreq:
    def test_good_when_feature_score_gte_5(self, conn):
        # 3 features xHIGH (score=2) = 6 ≥ 5 → good
        fh = make_fh(_UUID, ["2024-01"], {"出面": HIGH, "日報": HIGH, "報告書": HIGH})
        _register_work(conn, fh)

        monthly, _ = single_product.build_work(conn)
        assert monthly.iloc[0]["usage_freq"] == "good"

    def test_normal_when_feature_score_in_normal_range(self, conn):
        # 1 HIGH feature → score=2
        # Precondition: score=2 must be in [usage_freq_normal, usage_freq_good)
        assert TIER.usage_freq_normal <= 2 < TIER.usage_freq_good, (
            f"Config changed (normal={TIER.usage_freq_normal}, "
            f"good={TIER.usage_freq_good}): update test data setup"
        )
        fh = make_fh(_UUID, ["2024-01"], {"出面": HIGH})
        _register_work(conn, fh)

        monthly, _ = single_product.build_work(conn)
        assert monthly.iloc[0]["usage_freq"] == "normal"

    def test_bad_when_feature_score_below_normal(self, conn):
        # ZERO → score=0 < usage_freq_normal → bad
        fh = make_fh(_UUID, ["2024-01"], {"出面": ZERO})
        _register_work(conn, fh)

        monthly, _ = single_product.build_work(conn)
        assert monthly.iloc[0]["usage_freq"] == "bad"

    def test_mid_usage_gives_score_1_per_feature(self, conn):
        # 3 features xMID (score=1) = 3 → normal
        # good_min=10 の機能を選択 (日報=5/報告書=4 は MID=6 で good になるため除外)
        fh = make_fh(_UUID, ["2024-01"], {"出面": MID, "掲示板": MID, "出来高": MID})
        _register_work(conn, fh)

        monthly, _ = single_product.build_work(conn)
        assert monthly.iloc[0]["usage_freq"] == "normal"


# ── weekly schema ─────────────────────────────────────────────────────────────


class TestWorkWeeklySchema:
    def test_weekly_returns_dataframe(self, conn):
        fh = make_fh(_UUID, _MONTHS, {"出面": HIGH})
        _register_work(conn, fh)

        _, weekly = single_product.build_work(conn)
        assert isinstance(weekly, pd.DataFrame)
        expected_cols = {
            "week_start",
            "company_uuid",
            "feature_score",
            "usage_freq",
            "diversity_tier",
        }
        assert expected_cols <= set(weekly.columns)


# ── diversity_tier (keiei) ────────────────────────────────────────────────────


class TestKeieiDiversityTier:
    def test_fan_when_2_keiei_features_3_months(self, conn):
        kfh = make_kfh(
            _UUID, _MONTHS, {"案件ステータス更新": HIGH, "見積原価登録": HIGH}
        )
        _register_keiei(conn, kfh)

        monthly, _ = single_product.build_keiei(conn)
        last = monthly[monthly["usage_month"] == "2024-04"]
        assert last.iloc[0]["diversity_tier"] == "fan"

    def test_proactive_when_1_keiei_feature_3_months(self, conn):
        kfh = make_kfh(_UUID, _MONTHS, {"案件ステータス更新": HIGH})
        _register_keiei(conn, kfh)

        monthly, _ = single_product.build_keiei(conn)
        last = monthly[monthly["usage_month"] == "2024-04"]
        assert last.iloc[0]["diversity_tier"] == "proactive"

    def test_passive_when_no_keiei_feature_used(self, conn):
        kfh = make_kfh(_UUID, _MONTHS, {"案件ステータス更新": ZERO})
        _register_keiei(conn, kfh)

        monthly, _ = single_product.build_keiei(conn)
        last = monthly[monthly["usage_month"] == "2024-03"]
        assert last.iloc[0]["diversity_tier"] == "passive"

    def test_onboarding_overrides_keiei_tier(self, conn):
        kfh = make_kfh(
            _UUID,
            _MONTHS,
            {"案件ステータス更新": HIGH, "見積原価登録": HIGH},
            stage="onboarding-plus",
        )
        _register_keiei(conn, kfh)

        monthly, _ = single_product.build_keiei(conn)
        assert (monthly["diversity_tier"] == "onboarding").all()

    def test_keiei_passive_when_window_less_than_3(self, conn):
        kfh = make_kfh(_UUID, ["2024-01", "2024-02"], {"案件ステータス更新": HIGH})
        _register_keiei(conn, kfh)

        monthly, _ = single_product.build_keiei(conn)
        last = monthly[monthly["usage_month"] == "2024-02"]
        assert last.iloc[0]["diversity_tier"] == "passive"
