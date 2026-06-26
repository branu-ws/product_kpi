"""config.yml の読み込みと値の検証ユニットテスト。"""

from kpi.config import (
    ACTIVE_PLAN_TYPES,
    FEATURE_THRESHOLDS,
    KEIEI_FEATURE_THRESHOLDS,
    PLAN_TYPE_CODES,
    REDASH,
    TIER,
)


class TestTierParams:
    def test_rolling_months(self):
        assert TIER.rolling_months == 3

    def test_weekly_window(self):
        assert TIER.weekly_window > 0

    def test_avg_months(self):
        assert TIER.avg_months == 12

    def test_fan_feature_min(self):
        assert TIER.fan_feature_min == 2

    def test_proactive_feature_min(self):
        assert TIER.proactive_feature_min == 1

    def test_xproduct_score_min(self):
        assert TIER.xproduct_score_min == 1

    def test_usage_freq_good(self):
        assert TIER.usage_freq_good > TIER.usage_freq_normal > 0

    def test_usage_freq_normal(self):
        assert 0 < TIER.usage_freq_normal < TIER.usage_freq_good


class TestRedashSettings:
    def test_base_url(self):
        assert REDASH.base_url == "https://redash.careecon.jp"

    def test_data_source_db(self):
        assert REDASH.data_sources.db == 1

    def test_data_source_cas(self):
        assert REDASH.data_sources.cas == 2

    def test_data_source_work(self):
        assert REDASH.data_sources.work == 7

    def test_saved_query_work_user_history(self):
        assert REDASH.saved_queries.work_user_history == 914


class TestFeatureThresholds:
    def test_work_idenmen_thresholds(self):
        thr = FEATURE_THRESHOLDS["出面"]
        assert thr.good_min > thr.normal_min > 0

    def test_work_koutei_thresholds(self):
        thr = FEATURE_THRESHOLDS["工程作成"]
        assert thr.good_min > thr.normal_min > 0

    def test_all_work_features_present(self):
        expected = {"工程作成", "出面", "出来高", "掲示板", "日報", "報告書", "AIアシスタント", "写真アップロード", "フォルダ作成"}
        assert set(FEATURE_THRESHOLDS.keys()) == expected

    def test_all_keiei_features_present(self):
        expected = {
            "案件ステータス更新",
            "見積原価登録",
            "見積売上登録",
            "実績原価登録",
            "実績売上登録",
            "請求書発行",
            "OCR処理",
            "原価ページPV",
        }
        assert set(KEIEI_FEATURE_THRESHOLDS.keys()) == expected

    def test_keiei_good_min(self):
        for thr in KEIEI_FEATURE_THRESHOLDS.values():
            assert thr.good_min == 2
            assert thr.normal_min == 1


class TestPlanConfig:
    def test_active_plan_types(self):
        assert ACTIVE_PLAN_TYPES == ["plus"]

    def test_plan_type_codes_plus(self):
        assert PLAN_TYPE_CODES["business"] == "plus"
        assert PLAN_TYPE_CODES["business_annual"] == "plus"

    def test_plan_type_codes_mini(self):
        assert PLAN_TYPE_CODES["personal_annual"] == "mini"
