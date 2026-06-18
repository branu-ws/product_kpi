"""config.yml の kpi セクションを pydantic で検証して公開する。

パラメータを変更したいときは config.yml を編集するだけでよい。
コードは変更不要。
"""

from pathlib import Path

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel

_CONFIG_PATH = Path(__file__).parent.parent / "config.yml"


class FeatureThreshold(BaseModel, frozen=True):
    good_min: int
    normal_min: int


class LoyaltyParams(BaseModel, frozen=True):
    god_good_min: int
    god_months: int
    fan_good_min: int
    fan_months: int
    jisou_good_min: int
    jisou_months: int
    dansoku_months: int
    tamani_months: int
    rihan_months: int


class GcpSettings(BaseModel, frozen=True):
    project_id: str
    dataset: str = "kpi"


class _KpiSettings(BaseModel, frozen=True):
    feature_thresholds: dict[str, FeatureThreshold]
    keiei_feature_thresholds: dict[str, FeatureThreshold]
    loyalty: LoyaltyParams
    plan_type_codes: dict[str, str]
    active_plan_types: list[str]


def _load() -> _KpiSettings:
    raw = yaml.safe_load(_CONFIG_PATH.read_text())
    return _KpiSettings.model_validate(raw["kpi"])


def load_gcp() -> GcpSettings:
    raw = yaml.safe_load(_CONFIG_PATH.read_text())
    return GcpSettings.model_validate(raw["gcp"])


_settings = _load()

FEATURE_THRESHOLDS: dict[str, FeatureThreshold] = dict(_settings.feature_thresholds)
KEIEI_FEATURE_THRESHOLDS: dict[str, FeatureThreshold] = dict(
    _settings.keiei_feature_thresholds
)
LOYALTY: LoyaltyParams = _settings.loyalty
PLAN_TYPE_CODES: dict[str, str] = dict(_settings.plan_type_codes)
ACTIVE_PLAN_TYPES: list[str] = list(_settings.active_plan_types)
