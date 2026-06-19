"""日本の稼働日(祝日除く平日)の計算ユーティリティ。"""

from calendar import monthrange
from datetime import date, timedelta

import jpholiday
import pandas as pd


def _is_working(d: date) -> bool:
    return d.weekday() < 5 and not jpholiday.is_holiday(d)


def _count(start: date, end: date) -> int:
    return sum(
        1
        for i in range((end - start).days + 1)
        if _is_working(start + timedelta(i))
    )


def _month_bounds(ym: str) -> tuple[date, date]:
    y, m = int(ym[:4]), int(ym[5:])
    return date(y, m, 1), date(y, m, monthrange(y, m)[1])


def build_monthly(months: list[str]) -> pd.DataFrame:
    """usage_month → working_days の DataFrame を返す。"""
    return pd.DataFrame(
        [{"usage_month": ym, "working_days": _count(*_month_bounds(ym))}
         for ym in months]
    )


def build_weekly(weeks: list[date]) -> pd.DataFrame:
    """week_start (月曜) → working_days の DataFrame を返す。"""
    return pd.DataFrame(
        [{"week_start": w, "working_days": _count(w, w + timedelta(6))} for w in weeks]
    )


def avg_per_month(months: list[str]) -> float:
    """指定月リストの平均稼働日数を返す。日次閾値の基準値として使う。"""
    return sum(_count(*_month_bounds(m)) for m in months) / len(months)
