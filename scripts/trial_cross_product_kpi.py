#!/usr/bin/env python3
"""新クロスプロダクト KPI 試作スクリプト（稼働日正規化）。

使い方:
    uv run python scripts/trial_cross_product_kpi.py

出力:
    output/csv/trial_cp_monthly.csv  月次 integration_tier × usage_freq 集計
    output/csv/trial_cp_weekly.csv   週次 usage_freq 集計（直近12週）
"""

from __future__ import annotations

import sys
from calendar import monthrange
from datetime import date, timedelta
from pathlib import Path

import jpholiday
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from kpi import db
from kpi.config import ACTIVE_PLAN_TYPES, FEATURE_THRESHOLDS, KEIEI_FEATURE_THRESHOLDS

OUTPUT_DIR = Path(__file__).parent.parent / "output" / "csv"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── 稼働日ユーティリティ ──────────────────────────────────────────────────────


def _is_working(d: date) -> bool:
    return d.weekday() < 5 and not jpholiday.is_holiday(d)


def _working_days_between(start: date, end: date) -> int:
    return sum(
        1
        for i in range((end - start).days + 1)
        if _is_working(start + timedelta(i))
    )


def _month_bounds(ym: str) -> tuple[date, date]:
    y, m = int(ym[:4]), int(ym[5:])
    return date(y, m, 1), date(y, m, monthrange(y, m)[1])


def build_wd_monthly(months: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"usage_month": ym, "working_days": _working_days_between(*_month_bounds(ym))}
            for ym in months
        ]
    )


def build_wd_weekly(weeks: list[date]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "week_start": w,
                "working_days": _working_days_between(w, w + timedelta(6)),
            }
            for w in weeks
        ]
    )


# ── 日次閾値（月次閾値 ÷ 基準稼働日） ────────────────────────────────────────


def build_daily_thresholds(avg_days: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    work = pd.DataFrame(
        [
            {
                "feature": k,
                "daily_good": v.good_min / avg_days,
                "daily_normal": v.normal_min / avg_days,
            }
            for k, v in FEATURE_THRESHOLDS.items()
        ]
    )
    keiei = pd.DataFrame(
        [
            {
                "feature": k,
                "daily_good": v.good_min / avg_days,
                "daily_normal": v.normal_min / avg_days,
            }
            for k, v in KEIEI_FEATURE_THRESHOLDS.items()
        ]
    )
    return work, keiei


# ── 月次 KPI ─────────────────────────────────────────────────────────────────

_MONTHLY_COMPANY_SQL = """
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
    JOIN _work_thr   wt ON fh.feature = wt.feature
    JOIN _wd_monthly wd ON fh.month   = wd.usage_month
    GROUP BY fh.month, fh.company_uuid, fh.company_name, fh.lifecycle_stage
),
work_scores_deduped AS (
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
    JOIN _keiei_thr  kt ON kh.feature = kt.feature
    JOIN _wd_monthly wd ON kh.month   = wd.usage_month
    GROUP BY kh.month, kh.company_uuid
),
combined AS (
    SELECT
        w.usage_month, w.company_uuid, w.company_name, w.lifecycle_rank,
        w.work_score,
        COALESCE(k.keiei_score, 0)                AS keiei_score,
        w.work_score + COALESCE(k.keiei_score, 0) AS total_score
    FROM work_scores_deduped w
    LEFT JOIN keiei_scores k
        ON w.company_uuid = k.company_uuid AND w.usage_month = k.usage_month
),
rolling AS (
    SELECT
        *,
        COUNT(*) OVER (
            PARTITION BY company_uuid ORDER BY usage_month
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ) AS window_size,
        MIN(CASE WHEN work_score >= 1 AND keiei_score >= 1 THEN 1 ELSE 0 END) OVER (
            PARTITION BY company_uuid ORDER BY usage_month
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ) AS fan_all3,
        MIN(CASE WHEN work_score >= 1 OR keiei_score >= 1 THEN 1 ELSE 0 END) OVER (
            PARTITION BY company_uuid ORDER BY usage_month
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
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
        WHEN window_size >= 3 AND fan_all3      = 1 THEN 'fan'
        WHEN window_size >= 3 AND proactive_all3 = 1 THEN 'proactive'
        ELSE                                             'passive'
    END AS integration_tier,
    CASE
        WHEN total_score >= 5 THEN 'good'
        WHEN total_score >= 3 THEN 'normal'
        ELSE                       'bad'
    END AS usage_freq
FROM rolling
ORDER BY usage_month, company_name
"""

# 月次集計（Notion 用）は Python 側で company テーブルから GROUP BY する

# ── 週次 KPI ─────────────────────────────────────────────────────────────────

_WEEKLY_SQL = """
WITH active_companies AS (
    -- 最新月にアクティブな企業（母数）
    SELECT DISTINCT company_uuid
    FROM customer_lifecycle
    WHERE plan_type IN ({plan_filter})
      AND lifecycle_stage != 'retired'
      AND month = (SELECT MAX(month) FROM customer_lifecycle)
),
all_week_company AS (
    -- 全アクティブ企業 × 全週のマトリクス（利用ゼロを bad として含めるため）
    SELECT wd.week_start, ac.company_uuid
    FROM _wd_weekly wd
    CROSS JOIN active_companies ac
),
work_weekly AS (
    SELECT
        DATE_TRUNC('week', h.content_date::DATE) AS week_start,
        p.company_uuid,
        CASE WHEN h.content IN ('大工程', '小工程') THEN '工程作成' ELSE h.content END AS feature,
        COUNT(*) AS usage_count
    FROM work_user_history h
    JOIN work_process_id_generator p ON h.pid = p.pid
    WHERE h.content IN ('大工程', '小工程', '出面', '出来高', 'ホワイトボード', '日報', '報告書')
      AND h.content_date >= CURRENT_DATE - INTERVAL '84 days'
      AND p.company_uuid IN (SELECT company_uuid FROM active_companies)
    GROUP BY week_start, p.company_uuid, feature
),
keiei_weekly AS (
    SELECT
        DATE_TRUNC('week', h.content_date::DATE) AS week_start,
        h.company_uuid,
        h.content AS feature,
        COUNT(*) AS usage_count
    FROM keiei_user_history h
    WHERE h.content IN (SELECT feature FROM _keiei_thr)
      AND h.content_date >= CURRENT_DATE - INTERVAL '84 days'
      AND h.company_uuid IN (SELECT company_uuid FROM active_companies)
    GROUP BY week_start, h.company_uuid, h.content
),
work_scores_w AS (
    SELECT
        awc.week_start,
        awc.company_uuid,
        COALESCE(SUM(CASE
            WHEN r.usage_count::DOUBLE / wd.working_days >= wt.daily_good   THEN 2
            WHEN r.usage_count::DOUBLE / wd.working_days >= wt.daily_normal THEN 1
            ELSE 0
        END), 0) AS work_score
    FROM all_week_company awc
    JOIN _wd_weekly wd ON awc.week_start = wd.week_start
    LEFT JOIN work_weekly r
        ON awc.company_uuid = r.company_uuid AND awc.week_start = r.week_start
    LEFT JOIN _work_thr wt ON r.feature = wt.feature
    GROUP BY awc.week_start, awc.company_uuid
),
keiei_scores_w AS (
    SELECT
        awc.week_start,
        awc.company_uuid,
        COALESCE(SUM(CASE
            WHEN r.usage_count::DOUBLE / wd.working_days >= kt.daily_good   THEN 2
            WHEN r.usage_count::DOUBLE / wd.working_days >= kt.daily_normal THEN 1
            ELSE 0
        END), 0) AS keiei_score
    FROM all_week_company awc
    JOIN _wd_weekly wd ON awc.week_start = wd.week_start
    LEFT JOIN keiei_weekly r
        ON awc.company_uuid = r.company_uuid AND awc.week_start = r.week_start
    LEFT JOIN _keiei_thr kt ON r.feature = kt.feature
    GROUP BY awc.week_start, awc.company_uuid
),
combined_w AS (
    SELECT
        w.week_start,
        w.company_uuid,
        w.work_score,
        k.keiei_score,
        w.work_score + k.keiei_score AS total_score
    FROM work_scores_w w
    JOIN keiei_scores_w k
        ON w.company_uuid = k.company_uuid
       AND w.week_start   = k.week_start
),
-- integration_tier: 当月の月次ティアと一致させる
month_tier AS (
    SELECT company_uuid, company_name, integration_tier,
           usage_month AS apply_month
    FROM _monthly_company
)
SELECT
    cw.week_start,
    cw.company_uuid,
    COALESCE(mt.company_name, cw.company_uuid) AS company_name,
    cw.work_score,
    cw.keiei_score,
    cw.total_score,
    CASE
        WHEN cw.total_score >= 5 THEN 'good'
        WHEN cw.total_score >= 3 THEN 'normal'
        ELSE                          'bad'
    END AS usage_freq,
    COALESCE(mt.integration_tier, 'passive') AS integration_tier
FROM combined_w cw
LEFT JOIN month_tier mt
    ON  cw.company_uuid = mt.company_uuid
    AND STRFTIME(
        DATE_TRUNC('month', cw.week_start + INTERVAL '6 days'), '%Y-%m'
    ) = mt.apply_month
ORDER BY cw.week_start, cw.company_uuid
"""


# ── メイン ────────────────────────────────────────────────────────────────────


def main() -> None:
    conn = db.load()

    all_months: list[str] = conn.sql(
        "SELECT DISTINCT month FROM feature_health ORDER BY month"
    ).df()["month"].tolist()

    today = date.today()
    current_ym = today.strftime("%Y-%m")

    # 基準稼働日 = 直近12か月（完結済み月）の平均
    complete_months = [m for m in all_months if m < current_ym][-12:]
    avg_days = sum(
        _working_days_between(*_month_bounds(m)) for m in complete_months
    ) / len(complete_months)
    print(f"基準稼働日/月: {avg_days:.1f} (対象: {complete_months[0]} 〜 {complete_months[-1]})")

    work_thr, keiei_thr = build_daily_thresholds(avg_days)
    wd_monthly = build_wd_monthly(all_months)

    # 月次閾値の確認
    print("\n[日次閾値 - 施工管理]")
    print(work_thr.assign(
        daily_good=work_thr["daily_good"].round(3),
        daily_normal=work_thr["daily_normal"].round(3),
    ).to_string(index=False))
    print("\n[日次閾値 - 経営管理]")
    print(keiei_thr.assign(
        daily_good=keiei_thr["daily_good"].round(3),
        daily_normal=keiei_thr["daily_normal"].round(3),
    ).to_string(index=False))

    conn.register("_work_thr", work_thr)
    conn.register("_keiei_thr", keiei_thr)
    conn.register("_wd_monthly", wd_monthly)

    # ── 月次 per-company ──────────────────────────────────────────────────────
    print("\n月次 KPI を計算中...")
    monthly_company_df = conn.sql(_MONTHLY_COMPANY_SQL).df()
    conn.register("_monthly_company", monthly_company_df)

    # 集計版（Notion 用）は Python で GROUP BY
    monthly_summary_df = (
        monthly_company_df
        .groupby(["usage_month", "integration_tier", "usage_freq"], as_index=False)
        .agg(num_company=("company_uuid", "nunique"))
        .sort_values(["usage_month", "integration_tier", "usage_freq"])
    )

    out_m = OUTPUT_DIR / "trial_cp_monthly.csv"
    monthly_summary_df.to_csv(out_m, index=False, encoding="utf-8-sig")
    print(f"→ {out_m}  ({len(monthly_summary_df)} rows, 集計)")

    recent = monthly_summary_df[monthly_summary_df["usage_month"] >= complete_months[-3]]
    print(recent.to_string(index=False))

    # ── 週次 ──────────────────────────────────────────────────────────────────
    print("\n週次 KPI を計算中...")
    this_monday = today - timedelta(days=today.weekday())
    weeks = [this_monday - timedelta(weeks=i) for i in range(12)][::-1]
    wd_weekly = build_wd_weekly(weeks)
    conn.register("_wd_weekly", wd_weekly)

    plan_filter = ", ".join(f"'{p}'" for p in ACTIVE_PLAN_TYPES)
    weekly_df = conn.sql(_WEEKLY_SQL.format(plan_filter=plan_filter)).df()

    out_w = OUTPUT_DIR / "trial_cp_weekly.csv"
    weekly_df.to_csv(out_w, index=False, encoding="utf-8-sig")
    print(f"→ {out_w}  ({len(weekly_df)} rows, per-company)")

    # 確認用: 週 × usage_freq × integration_tier の集計
    weekly_summary = (
        weekly_df
        .groupby(["week_start", "integration_tier", "usage_freq"], as_index=False)
        .agg(num_company=("company_uuid", "nunique"))
        .sort_values(["week_start", "integration_tier", "usage_freq"])
    )
    recent_weeks = weekly_summary[weekly_summary["week_start"] >= pd.Timestamp(weeks[-4])]
    print(recent_weeks.to_string(index=False))

    conn.close()


if __name__ == "__main__":
    main()
