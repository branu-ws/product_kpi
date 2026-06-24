# 調査引き継ぎ: アクティブ企業数が想定より多い問題

## 問題

クロスプロダクト KPI の週次レポート（`output/csv/trial_cp_weekly.csv`）を確認したところ、
6月時点の active 企業が **893社** 表示されている。

しかし plus プランの契約企業は実態 **200社前後** のはずであり、約4倍の乖離がある。

## 現在の数字（2026-06-22 時点）

```
6月 weekly 6/1 週の内訳（trial_cp_weekly.csv）:
  onboarding bad   96社
  passive    bad  765社
  passive    good    2社
  passive  normal    2社
  proactive  bad   14社
  proactive  good  11社
  proactive normal   2社
  fan        good    2社
  fan      normal    1社
  ─────────────────────
  合計       893社
```

`customer_lifecycle` の 6月 active（plan_type = 'plus' AND lifecycle_stage != 'retired'）で絞っても 893社。

## 疑うべき原因（仮説）

1. **`customer_lifecycle` に重複・誤データが混入している**  
   `contracts` の plan_type マッピングが意図通り動いていない可能性。
   `PLAN_TYPE_CODES`（`kpi/config.py`）で `"business"` → `"plus"` に変換しているが、
   変換対象外のプラン（trial・無効等）が plus として混入しているかもしれない。

2. **退会済み企業が retired にならず残っている**  
   `contracts` の `status` や `end_date` の判定ロジックに漏れがある可能性。
   `kpi/contracts.py` の SQL で終了契約を正しく除外できているか要確認。

3. **1企業が複数の company_uuid で重複カウントされている**  
   `cid`（UUID）の名寄せができておらず、同一企業が複数レコードになっている可能性。

## 調査の出発点

```python
# DuckDB で直接確認
import duckdb
conn = duckdb.connect("cache.duckdb")

# 1. 6月 active の内訳を contracts の生データで確認
conn.sql("""
    SELECT plan_type, lifecycle_stage, COUNT(DISTINCT company_uuid) as n
    FROM customer_lifecycle
    WHERE month = '2026-06'
    GROUP BY 1, 2
    ORDER BY 1, 2
""").df()

# 2. contracts テーブルの状態
conn.sql("""
    SELECT plan_type, status, COUNT(*) as n
    FROM contracts
    GROUP BY 1, 2
    ORDER BY 1, 2
""").df()

# 3. companies テーブルとの件数比較
conn.sql("SELECT COUNT(DISTINCT company_uuid) FROM companies").df()
conn.sql("SELECT COUNT(DISTINCT company_uuid) FROM contracts WHERE plan_type = 'plus'").df()
```

## 関連ファイル

| ファイル | 役割 |
|---------|------|
| `kpi/contracts.py` | Redash から contracts/accounts を取得し DuckDB に書き込む |
| `kpi/customer_lifecycle.py` | `customer_lifecycle` テーブルを構築する SQL |
| `kpi/config.py` | `PLAN_TYPE_CODES`・`ACTIVE_PLAN_TYPES` の定義 |
| `cache.duckdb` | ローカルキャッシュ（直接 DuckDB で SELECT 可能） |

## 重要な前提知識（CLAUDE.md より）

- DS1 `companies.id` と CAS `contracts.company_id` は **別の連番**（直接 JOIN 不可）
- 共通キーは **`cid`（UUID）**: `companies.cid` = `accounts.cid` = DS7 `companies.cid`
- `contracts.py` では `accounts.cid` を経由して UUID を解決している

## 期待するゴール

- 6月 active が 893社になっている原因を特定する
- 本来の plus 契約顧客 〜200社 に絞れるようなフィルタを確認・修正する
- 必要なら `kpi/contracts.py` または `kpi/customer_lifecycle.py` を修正する
