# get_kpi — KPI パイプライン 設計ドキュメント

## プロジェクト概要

Redash API からデータを取得し DuckDB にキャッシュ、顧客ロイヤリティ・機能ヘルスを月次集計して CSV 出力するパイプライン。

```
uv run python update_duckdb.py          # データ取得 + DuckDB 再構築
uv run python main.py collections/*.sql # SQL → CSV 出力
```

---

## データソース (Redash)

| ID | DB名 | 用途 |
|----|------|------|
| DS1 | careecon_db (MySQL) | 会社マスタ (`companies.id`, `companies.cid`) |
| DS2 | careecon_cas (MySQL) | 契約・請求 (`contracts`, `items`, `accounts`) |
| DS7 | careecon_work (MySQL) | 施工管理プロダクト利用履歴 |
| DS11 | Query Results | Redash 保存クエリキャッシュ |

### ⚠️ 重要: company_id の番号体系が DB ごとに異なる

- DS1 `companies.id` と CAS `contracts.company_id` は **別の連番**（直接 JOIN 不可）
- 共通キーは **`cid` (UUID)**: DS1 `companies.cid` = CAS `accounts.cid` = DS7 `companies.cid`
- `contracts.py` では CAS `accounts.cid` を経由して UUID を解決している

```python
# ❌ これはバグ（DS1 id と CAS company_id は別物）
SELECT id FROM companies WHERE id IN (CAS_company_ids)

# ✅ 正しい方法
SELECT company_id, cid AS company_uuid
FROM accounts WHERE company_id IN (CAS_company_ids)
```

---

## DuckDB テーブル構成

```
work_user_history       : 機能別利用イベント (pid, content, content_date)
work_process_id_generator : pid → company_uuid のブリッジ
companies               : company_uuid, company_name
contracts               : company_uuid, plan_type, status, start_date, end_date
users                   : user情報
customer_lifecycle      : company_uuid × usage_month × lifecycle_stage [派生]
feature_health          : company_uuid × feature × usage_month × health [派生]
company_loyalty         : company_uuid × usage_month × loyalty_tier [派生]
```

### `customer_lifecycle` テーブル (重要)

```
lifecycle_stage の値:
  onboarding-plus   : Plus かつ契約開始から 3 か月以内
  plus              : Plus かつ 3 か月超
  onboarding-mini   : Mini かつ 3 か月以内
  mini              : Mini かつ 3 か月超
  retired           : 全契約終了・当月にアクティブ契約なし
```

- plan_type と onboarding は独立した軸 → MECE
- 同月に mini + plus 重複時は plus 優先 (ROW_NUMBER)
- `feature_health` と `company_loyalty` はこのテーブルから lifecycle_stage を取得

---

## 計測対象機能と閾値 (`kpi/config.py`)

| 機能 | good | normal | bad | content値 |
|------|------|--------|-----|-----------|
| 工程作成 | ≥20 | ≥5 | <5 | 大工程 + 小工程 を合算 |
| 出面 | ≥10 | ≥3 | <3 | 出面 |
| 出来高 | ≥10 | ≥3 | <3 | 出来高 (progress_updated_on) |
| ホワイトボード | ≥10 | ≥3 | <3 | board_posts |
| 日報 | ≥10 | ≥3 | <3 | 日報 |
| 報告書 | ≥10 | ≥3 | <3 | 報告書 |

### ⚠️ 工程作成の注意点

`work_user_history` の 大工程/小工程 は **新規作成イベント**をカウントしている。
オンボーディング時にテンプレート (大工程8 + 小工程24 = 32件) を一括作成するため、
契約開始月だけ件数が膨らみ翌月ゼロになるケースがある。
→ 将来的に `small_processes.progress_updated_on` (進捗更新数) への切り替えを検討中。

---

## ロイヤリティ階層 (`kpi/config.py` LOYALTY パラメータ)

| 階層 | 条件 |
|------|------|
| 神 | good ≥5機能 × 3か月以上 |
| ファン | good ≥2機能 × 3か月以上 |
| 自走 | good ≥1機能 × 2か月以上 |
| 2か月連続活用 | normal ≥1機能 × 2か月以上 |
| 断続的活用 | good or normal ≥1機能 × 1か月 |
| まずい | 全機能 bad (上記未満) |
| 離反状態 | 全機能の利用回数ゼロ × 3か月以上 |

閾値は `kpi/config.py` の `LoyaltyParams` で一元管理。コード変更不要で調整可能。

---

## プラン管理 (`kpi/config.py`)

```python
PLAN_TYPE_CODES = {
    "business":         "plus",
    "business_annual":  "plus",
    "personal_annual":  "mini",
}

# ここに "mini" を追加するだけで mini も分析対象に含まれる
ACTIVE_PLAN_TYPES: list[str] = ["plus"]
```

---

## 出力ファイル

| ファイル | 内容 |
|---------|------|
| `output/csv/output1_loyalty_distribution.csv` | 月別ロイヤリティ分布 (横ピボット) |
| `output/csv/output2_feature_health_summary.csv` | 月別機能ヘルス分布 |
| `output/csv/output3_loyalty_trend.csv` | 企業別ロイヤリティ推移 + 前月比フラグ |
| `output/csv/output4_feature_health_trend.csv` | 機能別ヘルス推移 |

---

## 未着手・次のステップ

- [ ] `工程作成` の指標を「新規作成数」→「進捗更新数 (progress_updated_on)」に切り替え
- [ ] `ACTIVE_PLAN_TYPES` に `"mini"` を追加して mini 分析を開始
- [ ] output1 をオンボーディング除外版 (`lifecycle_stage = 'plus'` フィルタ) に変更
- [ ] 経営企画プロダクト (DS? 未確認) の指標化 → 別セッションで実施

---

## 拡張時の注意点

### 新しいプロダクトを追加する場合

1. Redash でデータソース ID を確認 (DS1/DS7 相当を特定)
2. `kpi/work_user_history.py` に相当するフェッチモジュールを作成
3. `kpi/config.py` に `FEATURE_THRESHOLDS` を追加
4. `update_duckdb.py` にビルド処理を追加
5. `customer_lifecycle` は `contracts` ベースなので共用可能

### Mini 分析を追加する場合

`kpi/config.py` の `ACTIVE_PLAN_TYPES = ["plus", "mini"]` に変更するだけ。
ただし Mini は施工管理の一部機能 (工程作成・出面など) しか使えないため、
閾値や機能リストを Mini 向けに調整する必要がある可能性がある。
