"""稼働日計算の共通ビルドコンテキスト。

cross_product / single_product の build 関数が共有するボイラープレートを集約する。
"""

from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from kpi.config import TIER, FeatureThreshold
from kpi.working_days import avg_per_month, build_monthly, build_weekly


@dataclass(frozen=True)
class BuildContext:
    all_months: list[str]
    avg_days: float
    wd_monthly: pd.DataFrame
    wd_weekly: pd.DataFrame


def make_build_context(all_months: list[str]) -> BuildContext:
    today = date.today()
    cur_ym = today.strftime("%Y-%m")
    complete = [m for m in all_months if m < cur_ym][-TIER.avg_months :]
    avg_days = avg_per_month(complete)

    this_monday = today - timedelta(days=today.weekday())
    weeks = [this_monday - timedelta(weeks=i) for i in range(TIER.weekly_window)][::-1]

    return BuildContext(
        all_months=all_months,
        avg_days=avg_days,
        wd_monthly=build_monthly(all_months),
        wd_weekly=build_weekly(weeks),
    )


def make_thresholds(
    thresholds: dict[str, FeatureThreshold], avg_days: float
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "feature": k,
                "daily_good": v.good_min / avg_days,
                "daily_normal": v.normal_min / avg_days,
            }
            for k, v in thresholds.items()
        ]
    )
