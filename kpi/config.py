"""config.yml の各セクションを pydantic で検証して公開する。

パラメータを変更したいときは config.yml を編集するだけでよい。
コードは変更不要。
"""

import functools
from pathlib import Path
from typing import Any, cast

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel

_CONFIG_PATH = Path(__file__).parent.parent / "config.yml"


class FeatureThreshold(BaseModel, frozen=True):
    good_min: int
    normal_min: int


class TierParams(BaseModel, frozen=True):
    rolling_months: int
    weekly_window: int
    avg_months: int
    fan_feature_min: int
    proactive_feature_min: int
    xproduct_score_min: int
    usage_freq_good: int
    usage_freq_normal: int


class RedashDataSources(BaseModel, frozen=True):
    db: int
    cas: int
    work: int
    sf: int


class RedashSavedQueries(BaseModel, frozen=True):
    work_user_history: int


class RedashSettings(BaseModel, frozen=True):
    base_url: str
    data_sources: RedashDataSources
    saved_queries: RedashSavedQueries


class GcpSettings(BaseModel, frozen=True):
    project_id: str
    dataset: str = "kpi"
    charts_bucket: str = ""


class ChartEntry(BaseModel, frozen=True):
    name: str
    script: str
    html: str
    page_id: str = ""  # Notion embed 先。空文字の場合は embed をスキップ


class NotionOutputEntry(BaseModel, frozen=True):
    name: str
    sql: str
    db_id: str
    ds_id: str
    time_col: str = "month"


class NotionConfig(BaseModel, frozen=True):
    months_to_show: int = 18
    outputs: list[NotionOutputEntry] = []
    charts: list[ChartEntry] = []


class _KpiSettings(BaseModel, frozen=True):
    feature_thresholds: dict[str, FeatureThreshold]
    keiei_feature_thresholds: dict[str, FeatureThreshold]
    tier: TierParams
    plan_type_codes: dict[str, str]
    active_plan_types: list[str]


@functools.lru_cache(maxsize=1)
def _raw() -> dict[str, Any]:
    return cast(dict[str, Any], yaml.safe_load(_CONFIG_PATH.read_text()))


def _load() -> _KpiSettings:
    return _KpiSettings.model_validate(_raw()["kpi"])


def load_gcp() -> GcpSettings:
    return GcpSettings.model_validate(_raw()["gcp"])


def load_redash() -> RedashSettings:
    return RedashSettings.model_validate(_raw()["redash"])


def load_notion_config() -> NotionConfig:
    return NotionConfig.model_validate(_raw().get("notion", {}))


def load_notion_charts() -> list[ChartEntry]:
    return load_notion_config().charts


_settings = _load()

FEATURE_THRESHOLDS: dict[str, FeatureThreshold] = dict(_settings.feature_thresholds)
KEIEI_FEATURE_THRESHOLDS: dict[str, FeatureThreshold] = dict(
    _settings.keiei_feature_thresholds
)
TIER: TierParams = _settings.tier
PLAN_TYPE_CODES: dict[str, str] = dict(_settings.plan_type_codes)
ACTIVE_PLAN_TYPES: list[str] = list(_settings.active_plan_types)
REDASH: RedashSettings = load_redash()
