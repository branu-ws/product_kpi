"""KPI 閾値・ロイヤリティ判定パラメータ。ここの数値を変えるだけで全体に反映される。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class FeatureThreshold:
    good_min: int
    normal_min: int


@dataclass(frozen=True)
class LoyaltyParams:
    god_good_min: int = 5  # 神: good 機能数の最小値
    god_months: int = 3  # 神: 継続月数
    fan_good_min: int = 2  # ファン: good 機能数の最小値
    fan_months: int = 3  # ファン: 継続月数
    jisou_good_min: int = 1  # 自走: good 機能数の最小値
    jisou_months: int = 2  # 自走: 継続月数
    dansoku_months: int = 2  # 断続的に活用: normal 継続月数
    tamani_months: int = 1  # たまに活用: good/normal が 1 か月以上
    rihan_months: int = 3  # 離反状態: 利用回数ゼロが続く月数


FEATURE_THRESHOLDS: dict[str, FeatureThreshold] = {
    "工程作成": FeatureThreshold(good_min=20, normal_min=5),
    "出面": FeatureThreshold(good_min=10, normal_min=3),
    "出来高": FeatureThreshold(good_min=10, normal_min=3),
    "ホワイトボード": FeatureThreshold(good_min=10, normal_min=3),
    "日報": FeatureThreshold(good_min=10, normal_min=3),
    "報告書": FeatureThreshold(good_min=10, normal_min=3),
}

KEIEI_FEATURE_THRESHOLDS: dict[str, FeatureThreshold] = {
    "案件ステータス更新": FeatureThreshold(good_min=2, normal_min=1),
    "見積原価登録": FeatureThreshold(good_min=2, normal_min=1),
    "見積売上登録": FeatureThreshold(good_min=2, normal_min=1),
    "実績原価登録": FeatureThreshold(good_min=2, normal_min=1),
    "実績売上登録": FeatureThreshold(good_min=2, normal_min=1),
    "請求書発行": FeatureThreshold(good_min=2, normal_min=1),
    "OCR処理": FeatureThreshold(good_min=2, normal_min=1),
    "原価ページPV": FeatureThreshold(good_min=2, normal_min=1),
}

LOYALTY = LoyaltyParams()

# CAS items.code → plan_type のマッピング
PLAN_TYPE_CODES: dict[str, str] = {
    "business": "plus",
    "business_annual": "plus",
    "personal_annual": "mini",
}

# 分析対象プラン: "mini" を追加すれば mini も含まれる
ACTIVE_PLAN_TYPES: list[str] = ["plus"]
