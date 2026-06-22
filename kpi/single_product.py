"""単一プロダクト KPI (稼働日正規化, 機能多様性ティア)。

月次 per-company と週次 per-company の2テーブルをプロダクトごとに生成する。
  work_monthly_company  : company x usage_month x feature_score x diversity_tier
  work_company_weekly   : company x week_start  x feature_score x usage_freq
  keiei_monthly_company : 同上 (経営管理)
  keiei_company_weekly  : 同上 (経営管理)

diversity_tier の判定 (直近3ヶ月ローリング):
  onboarding : lifecycle_stage が onboarding-*
  fan        : 直近3ヶ月すべてで normal_plus_count>=2
  proactive  : 直近3ヶ月すべてで normal_plus_count>=1
  passive    : 上記以外

usage_freq の判定 (稼働日正規化の feature_score 合計):
  good   : >=5
  normal : >=3
  bad    : <3
"""

from datetime import date, timedelta

import duckdb
import pandas as pd

from kpi.config import (
    ACTIVE_PLAN_TYPES,
    FEATURE_THRESHOLDS,
    KEIEI_FEATURE_THRESHOLDS,
    TIER,
    FeatureThreshold,
)
from kpi.working_days import avg_per_month, build_monthly, build_weekly

_WORK_MONTHLY_SQL = """
WITH work_scores AS (
    SELECT
        fh.month AS usage_month,
        fh.company_uuid,
        fh.company_name,
        fh.lifecycle_stage,
        SUM(CASE
            WHEN fh.usage_count::DOUBLE / wd.working_days >= wt.daily_good   THEN 2
            WHEN fh.usage_count::DOUBLE / wd.working_days >= wt.daily_normal THEN 1
            ELSE 0
        END) AS feature_score,
        SUM(CASE
            WHEN fh.usage_count::DOUBLE / wd.working_days >= wt.daily_normal THEN 1
            ELSE 0
        END) AS normal_plus_count
    FROM feature_health fh
    JOIN _sp_work_thr  wt ON fh.feature = wt.feature
    JOIN _sp_wd_monthly wd ON fh.month  = wd.usage_month
    GROUP BY fh.month, fh.company_uuid, fh.company_name, fh.lifecycle_stage
),
work_deduped AS (
    SELECT
        usage_month, company_uuid, company_name,
        MAX(CASE lifecycle_stage
            WHEN 'onboarding-plus' THEN 5
            WHEN 'plus'            THEN 4
            WHEN 'onboarding-mini' THEN 3
            WHEN 'mini'            THEN 2
            ELSE 0
        END) AS lifecycle_rank,
        MAX(feature_score)     AS feature_score,
        MAX(normal_plus_count) AS normal_plus_count
    FROM work_scores
    GROUP BY usage_month, company_uuid, company_name
),
rolling AS (
    SELECT
        *,
        COUNT(*) OVER (
            PARTITION BY company_uuid ORDER BY usage_month
            ROWS BETWEEN {rolling_preceding} PRECEDING AND CURRENT ROW
        ) AS window_size,
        MIN(CASE WHEN normal_plus_count >= {fan_min} THEN 1 ELSE 0 END) OVER (
            PARTITION BY company_uuid ORDER BY usage_month
            ROWS BETWEEN {rolling_preceding} PRECEDING AND CURRENT ROW
        ) AS fan_all3,
        MIN(CASE WHEN normal_plus_count >= {pro_min} THEN 1 ELSE 0 END) OVER (
            PARTITION BY company_uuid ORDER BY usage_month
            ROWS BETWEEN {rolling_preceding} PRECEDING AND CURRENT ROW
        ) AS proactive_all3
    FROM work_deduped
)
SELECT
    usage_month,
    company_uuid,
    company_name,
    feature_score,
    CASE
        WHEN lifecycle_rank IN (5, 3)                 THEN 'onboarding'
        WHEN window_size >= {rolling_months} AND fan_all3      = 1 THEN 'fan'
        WHEN window_size >= {rolling_months} AND proactive_all3 = 1 THEN 'proactive'
        ELSE                                               'passive'
    END AS diversity_tier,
    CASE
        WHEN feature_score >= {freq_good}   THEN 'good'
        WHEN feature_score >= {freq_normal} THEN 'normal'
        ELSE                                     'bad'
    END AS usage_freq
FROM rolling
ORDER BY usage_month, company_name
"""

_WORK_WEEKLY_SQL = """
WITH active_companies AS (
    SELECT DISTINCT company_uuid
    FROM customer_lifecycle
    WHERE plan_type IN ({plan_filter})
      AND lifecycle_stage != 'retired'
      AND month = (SELECT MAX(month) FROM customer_lifecycle)
),
all_week_company AS (
    SELECT wd.week_start, ac.company_uuid
    FROM _sp_wd_weekly wd
    CROSS JOIN active_companies ac
),
work_raw AS (
    SELECT
        DATE_TRUNC('week', h.content_date::DATE) AS week_start,
        p.company_uuid,
        CASE WHEN h.content IN ('大工程', '小工程')
             THEN '工程作成' ELSE h.content END AS feature,
        COUNT(*) AS usage_count
    FROM work_user_history h
    JOIN work_process_id_generator p ON h.pid = p.pid
    WHERE h.content IN (
        '大工程', '小工程', '出面', '出来高', 'ホワイトボード', '日報', '報告書'
    )
      AND h.content_date >= (SELECT MIN(week_start) FROM _sp_wd_weekly)
      AND p.company_uuid IN (SELECT company_uuid FROM active_companies)
    GROUP BY week_start, p.company_uuid, feature
),
work_scores AS (
    SELECT
        awc.week_start,
        awc.company_uuid,
        COALESCE(SUM(CASE
            WHEN r.usage_count::DOUBLE / wd.working_days >= wt.daily_good   THEN 2
            WHEN r.usage_count::DOUBLE / wd.working_days >= wt.daily_normal THEN 1
            ELSE 0
        END), 0) AS feature_score
    FROM all_week_company awc
    JOIN _sp_wd_weekly wd ON awc.week_start = wd.week_start
    LEFT JOIN work_raw r
        ON awc.company_uuid = r.company_uuid AND awc.week_start = r.week_start
    LEFT JOIN _sp_work_thr wt ON r.feature = wt.feature
    GROUP BY awc.week_start, awc.company_uuid
),
combined AS (
    SELECT
        ws.week_start,
        ws.company_uuid,
        c.company_name,
        ws.feature_score
    FROM work_scores ws
    LEFT JOIN companies c ON ws.company_uuid = c.company_uuid
),
month_tier AS (
    SELECT
        company_uuid,
        diversity_tier,
        usage_month AS apply_month
    FROM _sp_work_monthly
)
SELECT
    cw.week_start,
    cw.company_uuid,
    cw.company_name,
    cw.feature_score,
    CASE
        WHEN cw.feature_score >= {freq_good}   THEN 'good'
        WHEN cw.feature_score >= {freq_normal} THEN 'normal'
        ELSE                                        'bad'
    END AS usage_freq,
    COALESCE(mt.diversity_tier, 'passive') AS diversity_tier
FROM combined cw
LEFT JOIN month_tier mt
    ON  cw.company_uuid = mt.company_uuid
    AND STRFTIME(
        DATE_TRUNC('month', cw.week_start + INTERVAL '6 days'), '%Y-%m'
    ) = mt.apply_month
ORDER BY cw.week_start, cw.company_uuid
"""

_KEIEI_MONTHLY_SQL = """
WITH keiei_scores AS (
    SELECT
        kh.month AS usage_month,
        kh.company_uuid,
        kh.company_name,
        kh.lifecycle_stage,
        SUM(CASE
            WHEN kh.usage_count::DOUBLE / wd.working_days >= kt.daily_good   THEN 2
            WHEN kh.usage_count::DOUBLE / wd.working_days >= kt.daily_normal THEN 1
            ELSE 0
        END) AS feature_score,
        SUM(CASE
            WHEN kh.usage_count::DOUBLE / wd.working_days >= kt.daily_normal THEN 1
            ELSE 0
        END) AS normal_plus_count
    FROM keiei_feature_health kh
    JOIN _sp_keiei_thr  kt ON kh.feature = kt.feature
    JOIN _sp_wd_monthly wd ON kh.month   = wd.usage_month
    GROUP BY kh.month, kh.company_uuid, kh.company_name, kh.lifecycle_stage
),
keiei_deduped AS (
    SELECT
        usage_month, company_uuid, company_name,
        MAX(CASE lifecycle_stage
            WHEN 'onboarding-plus' THEN 5
            WHEN 'plus'            THEN 4
            WHEN 'onboarding-mini' THEN 3
            WHEN 'mini'            THEN 2
            ELSE 0
        END) AS lifecycle_rank,
        MAX(feature_score)     AS feature_score,
        MAX(normal_plus_count) AS normal_plus_count
    FROM keiei_scores
    GROUP BY usage_month, company_uuid, company_name
),
rolling AS (
    SELECT
        *,
        COUNT(*) OVER (
            PARTITION BY company_uuid ORDER BY usage_month
            ROWS BETWEEN {rolling_preceding} PRECEDING AND CURRENT ROW
        ) AS window_size,
        MIN(CASE WHEN normal_plus_count >= {fan_min} THEN 1 ELSE 0 END) OVER (
            PARTITION BY company_uuid ORDER BY usage_month
            ROWS BETWEEN {rolling_preceding} PRECEDING AND CURRENT ROW
        ) AS fan_all3,
        MIN(CASE WHEN normal_plus_count >= {pro_min} THEN 1 ELSE 0 END) OVER (
            PARTITION BY company_uuid ORDER BY usage_month
            ROWS BETWEEN {rolling_preceding} PRECEDING AND CURRENT ROW
        ) AS proactive_all3
    FROM keiei_deduped
)
SELECT
    usage_month,
    company_uuid,
    company_name,
    feature_score,
    CASE
        WHEN lifecycle_rank IN (5, 3)                 THEN 'onboarding'
        WHEN window_size >= {rolling_months} AND fan_all3      = 1 THEN 'fan'
        WHEN window_size >= {rolling_months} AND proactive_all3 = 1 THEN 'proactive'
        ELSE                                               'passive'
    END AS diversity_tier,
    CASE
        WHEN feature_score >= {freq_good}   THEN 'good'
        WHEN feature_score >= {freq_normal} THEN 'normal'
        ELSE                                     'bad'
    END AS usage_freq
FROM rolling
ORDER BY usage_month, company_name
"""

_KEIEI_WEEKLY_SQL = """
WITH active_companies AS (
    SELECT DISTINCT company_uuid
    FROM customer_lifecycle
    WHERE plan_type IN ({plan_filter})
      AND lifecycle_stage != 'retired'
      AND month = (SELECT MAX(month) FROM customer_lifecycle)
),
all_week_company AS (
    SELECT wd.week_start, ac.company_uuid
    FROM _sp_wd_weekly wd
    CROSS JOIN active_companies ac
),
keiei_raw AS (
    SELECT
        DATE_TRUNC('week', h.content_date::DATE) AS week_start,
        h.company_uuid,
        h.content AS feature,
        COUNT(*) AS usage_count
    FROM keiei_user_history h
    WHERE h.content IN (SELECT feature FROM _sp_keiei_thr)
      AND h.content_date >= (SELECT MIN(week_start) FROM _sp_wd_weekly)
      AND h.company_uuid IN (SELECT company_uuid FROM active_companies)
    GROUP BY week_start, h.company_uuid, h.content
),
keiei_scores AS (
    SELECT
        awc.week_start,
        awc.company_uuid,
        COALESCE(SUM(CASE
            WHEN r.usage_count::DOUBLE / wd.working_days >= kt.daily_good   THEN 2
            WHEN r.usage_count::DOUBLE / wd.working_days >= kt.daily_normal THEN 1
            ELSE 0
        END), 0) AS feature_score
    FROM all_week_company awc
    JOIN _sp_wd_weekly wd ON awc.week_start = wd.week_start
    LEFT JOIN keiei_raw r
        ON awc.company_uuid = r.company_uuid AND awc.week_start = r.week_start
    LEFT JOIN _sp_keiei_thr kt ON r.feature = kt.feature
    GROUP BY awc.week_start, awc.company_uuid
),
combined AS (
    SELECT
        ks.week_start,
        ks.company_uuid,
        c.company_name,
        ks.feature_score
    FROM keiei_scores ks
    LEFT JOIN companies c ON ks.company_uuid = c.company_uuid
),
month_tier AS (
    SELECT
        company_uuid,
        diversity_tier,
        usage_month AS apply_month
    FROM _sp_keiei_monthly
)
SELECT
    cw.week_start,
    cw.company_uuid,
    cw.company_name,
    cw.feature_score,
    CASE
        WHEN cw.feature_score >= {freq_good}   THEN 'good'
        WHEN cw.feature_score >= {freq_normal} THEN 'normal'
        ELSE                                        'bad'
    END AS usage_freq,
    COALESCE(mt.diversity_tier, 'passive') AS diversity_tier
FROM combined cw
LEFT JOIN month_tier mt
    ON  cw.company_uuid = mt.company_uuid
    AND STRFTIME(
        DATE_TRUNC('month', cw.week_start + INTERVAL '6 days'), '%Y-%m'
    ) = mt.apply_month
ORDER BY cw.week_start, cw.company_uuid
"""


def _make_thresholds(
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


def build_work(
    conn: duckdb.DuckDBPyConnection,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """施工管理の単一プロダクト KPI を計算して (monthly_df, weekly_df) を返す。"""
    today = date.today()
    cur_ym = today.strftime("%Y-%m")

    all_months: list[str] = conn.sql(
        "SELECT DISTINCT month FROM feature_health ORDER BY month"
    ).df()["month"].tolist()

    complete_months = [m for m in all_months if m < cur_ym][-TIER.avg_months:]
    avg_days = avg_per_month(complete_months)

    work_thr = _make_thresholds(FEATURE_THRESHOLDS, avg_days)
    wd_monthly = build_monthly(all_months)

    this_monday = today - timedelta(days=today.weekday())
    weeks = [this_monday - timedelta(weeks=i) for i in range(TIER.weekly_window)][::-1]
    wd_weekly = build_weekly(weeks)

    conn.register("_sp_work_thr", work_thr)
    conn.register("_sp_wd_monthly", wd_monthly)
    conn.register("_sp_wd_weekly", wd_weekly)

    tier_params = {
        "rolling_months": TIER.rolling_months,
        "rolling_preceding": TIER.rolling_months - 1,
        "fan_min": TIER.fan_feature_min,
        "pro_min": TIER.proactive_feature_min,
        "freq_good": TIER.usage_freq_good,
        "freq_normal": TIER.usage_freq_normal,
    }
    monthly_df: pd.DataFrame = conn.sql(_WORK_MONTHLY_SQL.format(**tier_params)).df()
    conn.register("_sp_work_monthly", monthly_df)

    plan_filter = ", ".join(f"'{p}'" for p in ACTIVE_PLAN_TYPES)
    weekly_df: pd.DataFrame = conn.sql(
        _WORK_WEEKLY_SQL.format(plan_filter=plan_filter, **tier_params)
    ).df()

    for t in ["_sp_work_thr", "_sp_wd_monthly", "_sp_wd_weekly", "_sp_work_monthly"]:
        conn.unregister(t)

    return monthly_df, weekly_df


def build_keiei(
    conn: duckdb.DuckDBPyConnection,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """経営管理の単一プロダクト KPI を計算して (monthly_df, weekly_df) を返す。"""
    today = date.today()
    cur_ym = today.strftime("%Y-%m")

    all_months: list[str] = conn.sql(
        "SELECT DISTINCT month FROM keiei_feature_health ORDER BY month"
    ).df()["month"].tolist()

    complete_months = [m for m in all_months if m < cur_ym][-TIER.avg_months:]
    avg_days = avg_per_month(complete_months)

    keiei_thr = _make_thresholds(KEIEI_FEATURE_THRESHOLDS, avg_days)
    wd_monthly = build_monthly(all_months)

    this_monday = today - timedelta(days=today.weekday())
    weeks = [this_monday - timedelta(weeks=i) for i in range(TIER.weekly_window)][::-1]
    wd_weekly = build_weekly(weeks)

    conn.register("_sp_keiei_thr", keiei_thr)
    conn.register("_sp_wd_monthly", wd_monthly)
    conn.register("_sp_wd_weekly", wd_weekly)

    tier_params = {
        "rolling_months": TIER.rolling_months,
        "rolling_preceding": TIER.rolling_months - 1,
        "fan_min": TIER.fan_feature_min,
        "pro_min": TIER.proactive_feature_min,
        "freq_good": TIER.usage_freq_good,
        "freq_normal": TIER.usage_freq_normal,
    }
    monthly_df: pd.DataFrame = conn.sql(_KEIEI_MONTHLY_SQL.format(**tier_params)).df()
    conn.register("_sp_keiei_monthly", monthly_df)

    plan_filter = ", ".join(f"'{p}'" for p in ACTIVE_PLAN_TYPES)
    weekly_df: pd.DataFrame = conn.sql(
        _KEIEI_WEEKLY_SQL.format(plan_filter=plan_filter, **tier_params)
    ).df()

    for t in ["_sp_keiei_thr", "_sp_wd_monthly", "_sp_wd_weekly", "_sp_keiei_monthly"]:
        conn.unregister(t)

    return monthly_df, weekly_df
