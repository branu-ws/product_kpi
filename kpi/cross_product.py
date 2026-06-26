"""クロスプロダクト KPI (稼働日正規化)。

月次 per-company と週次 per-company の2テーブルを生成する。
  cross_product_monthly_company : company x usage_month x scores x integration_tier
  cross_product_company_weekly  : company x week_start  x scores x usage_freq

integration_tier の判定:
  onboarding : lifecycle_stage が onboarding-*
  fan        : 直近3ヶ月すべてで work_score>=1 かつ keiei_score>=1
  proactive  : 直近3ヶ月すべてで work_score>=1 または keiei_score>=1
  passive    : 上記以外

usage_freq の判定 (total_score = work_score + keiei_score):
  good   : >=5
  normal : >=3
  bad    : <3
"""

import duckdb
import pandas as pd

from kpi.build_context import make_build_context, make_thresholds
from kpi.config import (
    ACTIVE_PLAN_TYPES,
    FEATURE_THRESHOLDS,
    KEIEI_FEATURE_THRESHOLDS,
    TIER,
)

_MONTHLY_SQL = """
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
        END) AS work_score
    FROM feature_health fh
    JOIN _cp_work_thr  wt ON fh.feature = wt.feature
    JOIN _cp_wd_monthly wd ON fh.month  = wd.usage_month
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
        MAX(work_score) AS work_score
    FROM work_scores
    GROUP BY usage_month, company_uuid, company_name
),
keiei_scores AS (
    SELECT
        kh.month AS usage_month,
        kh.company_uuid,
        SUM(CASE
            WHEN kh.usage_count::DOUBLE / wd.working_days >= kt.daily_good   THEN 2
            WHEN kh.usage_count::DOUBLE / wd.working_days >= kt.daily_normal THEN 1
            ELSE 0
        END) AS keiei_score
    FROM keiei_feature_health kh
    JOIN _cp_keiei_thr kt ON kh.feature = kt.feature
    JOIN _cp_wd_monthly wd ON kh.month  = wd.usage_month
    GROUP BY kh.month, kh.company_uuid
),
combined AS (
    SELECT
        w.usage_month, w.company_uuid, w.company_name, w.lifecycle_rank,
        w.work_score,
        COALESCE(k.keiei_score, 0)                AS keiei_score,
        w.work_score + COALESCE(k.keiei_score, 0) AS total_score
    FROM work_deduped w
    LEFT JOIN keiei_scores k
        ON w.company_uuid = k.company_uuid AND w.usage_month = k.usage_month
),
rolling AS (
    SELECT
        *,
        COUNT(*) OVER (
            PARTITION BY company_uuid ORDER BY usage_month
            ROWS BETWEEN {rolling_months} PRECEDING AND 1 PRECEDING
        ) AS window_size,
        MIN(
            CASE WHEN work_score >= {xp_min} AND keiei_score >= {xp_min}
                 THEN 1 ELSE 0 END
        ) OVER (
            PARTITION BY company_uuid ORDER BY usage_month
            ROWS BETWEEN {rolling_months} PRECEDING AND 1 PRECEDING
        ) AS fan_all3,
        MIN(
            CASE WHEN work_score >= {xp_min} OR keiei_score >= {xp_min}
                 THEN 1 ELSE 0 END
        ) OVER (
            PARTITION BY company_uuid ORDER BY usage_month
            ROWS BETWEEN {rolling_months} PRECEDING AND 1 PRECEDING
        ) AS proactive_all3
    FROM combined
)
SELECT
    usage_month,
    company_uuid,
    company_name,
    work_score,
    keiei_score,
    total_score,
    CASE
        WHEN lifecycle_rank IN (5, 3)               THEN 'onboarding'
        WHEN window_size >= {rolling_months} AND fan_all3      = 1 THEN 'fan'
        WHEN window_size >= {rolling_months} AND proactive_all3 = 1 THEN 'proactive'
        ELSE                                             'passive'
    END AS integration_tier,
    CASE
        WHEN total_score >= {freq_good}   THEN 'good'
        WHEN total_score >= {freq_normal} THEN 'normal'
        ELSE                                   'bad'
    END AS usage_freq
FROM rolling
ORDER BY usage_month, company_name
"""

_WEEKLY_SQL = """
WITH all_week_company AS (
    SELECT wd.week_start, cl.company_uuid
    FROM _cp_wd_weekly wd
    JOIN customer_lifecycle cl
        ON STRFTIME(DATE_TRUNC('month', wd.week_start + INTERVAL '6 days'), '%Y-%m') = cl.month
    WHERE cl.plan_type IN ({plan_filter})
      AND cl.lifecycle_stage != 'retired'
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
        '大工程', '小工程', '出面', '出来高', '掲示板', '日報', '報告書'
    )
      AND h.content_date >= (SELECT MIN(week_start) FROM _cp_wd_weekly)
      AND p.company_uuid IN (SELECT DISTINCT company_uuid FROM all_week_company)
    GROUP BY week_start, p.company_uuid, feature
),
keiei_raw AS (
    SELECT
        DATE_TRUNC('week', h.content_date::DATE) AS week_start,
        h.company_uuid,
        h.content AS feature,
        COUNT(*) AS usage_count
    FROM keiei_user_history h
    WHERE h.content IN (SELECT feature FROM _cp_keiei_thr)
      AND h.content_date >= (SELECT MIN(week_start) FROM _cp_wd_weekly)
      AND h.company_uuid IN (SELECT DISTINCT company_uuid FROM all_week_company)
    GROUP BY week_start, h.company_uuid, h.content
),
work_scores AS (
    SELECT
        awc.week_start,
        awc.company_uuid,
        COALESCE(SUM(CASE
            WHEN r.usage_count::DOUBLE / wd.working_days >= wt.daily_good   THEN 2
            WHEN r.usage_count::DOUBLE / wd.working_days >= wt.daily_normal THEN 1
            ELSE 0
        END), 0) AS work_score
    FROM all_week_company awc
    JOIN _cp_wd_weekly wd ON awc.week_start = wd.week_start
    LEFT JOIN work_raw r
        ON awc.company_uuid = r.company_uuid AND awc.week_start = r.week_start
    LEFT JOIN _cp_work_thr wt ON r.feature = wt.feature
    GROUP BY awc.week_start, awc.company_uuid
),
keiei_scores AS (
    SELECT
        awc.week_start,
        awc.company_uuid,
        COALESCE(SUM(CASE
            WHEN r.usage_count::DOUBLE / wd.working_days >= kt.daily_good   THEN 2
            WHEN r.usage_count::DOUBLE / wd.working_days >= kt.daily_normal THEN 1
            ELSE 0
        END), 0) AS keiei_score
    FROM all_week_company awc
    JOIN _cp_wd_weekly wd ON awc.week_start = wd.week_start
    LEFT JOIN keiei_raw r
        ON awc.company_uuid = r.company_uuid AND awc.week_start = r.week_start
    LEFT JOIN _cp_keiei_thr kt ON r.feature = kt.feature
    GROUP BY awc.week_start, awc.company_uuid
),
combined AS (
    SELECT
        w.week_start,
        w.company_uuid,
        c.company_name,
        w.work_score,
        k.keiei_score,
        w.work_score + k.keiei_score AS total_score
    FROM work_scores w
    JOIN keiei_scores k
        ON w.company_uuid = k.company_uuid AND w.week_start = k.week_start
    LEFT JOIN companies c ON w.company_uuid = c.company_uuid
),
-- integration_tier: 当月の月次ティアと一致させる
month_tier AS (
    SELECT
        company_uuid,
        integration_tier,
        usage_month AS apply_month
    FROM _cp_monthly_company
)
SELECT
    cw.week_start,
    cw.company_uuid,
    cw.company_name,
    cw.work_score,
    cw.keiei_score,
    cw.total_score,
    CASE
        WHEN cw.total_score >= {freq_good}   THEN 'good'
        WHEN cw.total_score >= {freq_normal} THEN 'normal'
        ELSE                                      'bad'
    END AS usage_freq,
    COALESCE(mt.integration_tier, 'passive') AS integration_tier
FROM combined cw
LEFT JOIN month_tier mt
    ON  cw.company_uuid = mt.company_uuid
    AND STRFTIME(
        DATE_TRUNC('month', cw.week_start + INTERVAL '6 days'), '%Y-%m'
    ) = mt.apply_month
ORDER BY cw.week_start, cw.company_uuid
"""


def build(
    conn: duckdb.DuckDBPyConnection,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """クロスプロダクト KPI を計算して2つの DataFrame を返す。

    Returns:
        monthly_df : company x usage_month (integration_tier, usage_freq 付き)
        weekly_df  : company x week_start  (usage_freq, integration_tier 付き, 直近12週)
    """
    all_months: list[str] = (
        conn.sql("SELECT DISTINCT month FROM feature_health ORDER BY month")
        .df()["month"]
        .tolist()
    )
    ctx = make_build_context(all_months)

    work_thr = make_thresholds(FEATURE_THRESHOLDS, ctx.avg_days)
    keiei_thr = make_thresholds(KEIEI_FEATURE_THRESHOLDS, ctx.avg_days)
    conn.register("_cp_work_thr", work_thr)
    conn.register("_cp_keiei_thr", keiei_thr)
    conn.register("_cp_wd_monthly", ctx.wd_monthly)
    conn.register("_cp_wd_weekly", ctx.wd_weekly)

    tier_params = {
        "rolling_months": TIER.rolling_months,
        "rolling_preceding": TIER.rolling_months - 1,
        "xp_min": TIER.xproduct_score_min,
        "freq_good": TIER.usage_freq_good,
        "freq_normal": TIER.usage_freq_normal,
    }
    monthly_df: pd.DataFrame = conn.sql(_MONTHLY_SQL.format(**tier_params)).df()
    conn.register("_cp_monthly_company", monthly_df)

    plan_filter = ", ".join(f"'{p}'" for p in ACTIVE_PLAN_TYPES)
    weekly_df: pd.DataFrame = conn.sql(
        _WEEKLY_SQL.format(plan_filter=plan_filter, **tier_params)
    ).df()

    for t in [
        "_cp_work_thr",
        "_cp_keiei_thr",
        "_cp_wd_monthly",
        "_cp_wd_weekly",
        "_cp_monthly_company",
    ]:
        conn.unregister(t)

    return monthly_df, weekly_df
