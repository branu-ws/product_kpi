# get_kpi — KPI パイプライン 設計ドキュメント

## プロジェクト概要

Redash API からデータを取得し DuckDB にキャッシュ、顧客ロイヤリティ・機能ヘルスを月次集計して CSV 出力するパイプライン。

```
uv run kpi-update          # Redash + SF からデータ取得・DuckDB 再構築・BigQuery 保存
uv run kpi-export collections/*.sql  # SQL → CSV 出力
uv run kpi-sync            # DuckDB → Notion 同期
```

---

## データソース (Redash)

| ID | config キー | DB名 | 用途 |
|----|-------------|------|------|
| DS1 | `db` | careecon_db (MySQL) | 会社マスタ (`companies.cid`, `name`, `zip`, `prefecture_id`, `city`, `address`) |
| DS2 | `cas` | careecon_cas (MySQL) | 契約・請求 (`contracts`, `items`, `accounts`) |
| DS7 | `work` | careecon_work (MySQL) | 施工管理プロダクト利用履歴 |
| DS11 | `sf` | Salesforce | `Account` (CAREECON_CID__c, CAREECON_Plus__c など) |

DS11 は SOQL で直接クエリできる（`redash.run_adhoc_query(client, REDASH.data_sources.sf, soql)`）。

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
work_user_history         : 機能別利用イベント (pid, content, content_date)
work_process_id_generator : pid → company_uuid のブリッジ
companies                 : company_uuid, company_name  ← DS7 (住所なし)
contracts                 : company_uuid, plan_type, status, start_date, end_date
users                     : user情報
sf_customers              : company_uuid のホワイトリスト (SF Plus 確認済み) [毎回自動更新]
customer_lifecycle        : company_uuid × usage_month × lifecycle_stage [派生]
feature_health            : company_uuid × feature × usage_month × health [派生]
company_loyalty           : company_uuid × usage_month × loyalty_tier [派生]
```

### `sf_customers` テーブル (重要)

- **ソース**: Salesforce `CAREECON_Plus__c = true AND CAREECON_Plus_Cancel__c = false` の全アカウント
- **生成**: `kpi/sf_customers.py` が `kpi-update` のたびに自動実行して最新化
- **目的**: CAS の `contracts` には free trial・未導入企業が多数混入（953社 → 実態 ~250社）するため、SF を真の Plus 顧客のソース・オブ・トゥルースとして使う
- **補填ロジック**: SF で `CAREECON_CID__c` が未設定の約130社は、DS1 `companies` テーブルと社名＋都道府県＋市区の段階的マッチングで UUID を補填（高→中→低の3段階）
- **適用**: `customer_lifecycle.py` の `active_ranked` CTE が `sf_customers` に INNER JOIN → sf_customers がない環境 (テスト等) では JOIN を省略して動く

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

## 顧客母集団に関する既知の問題

詳細は `docs/known_issues.md` に記載。要点のみ:

| 問題 | 数値 (2026-06 時点) | 対応状況 |
|------|---------------------|---------|
| CAS contracts に free trial 混入 | 953社 (実態 ~250社) | sf_customers で解決済み |
| SF の CAREECON_CID__c 未設定 | 130/270社が空欄 | 名前+住所マッチで補填、~234社をカバー |
| DS7 未登録 Plus 顧客 | ~13社 | 原理的に観測不可 (許容誤差) |
| mini 顧客が cross-product に出てくる | 一部混入 | sf_customers は Plus のみのため除外される |

### ⚠️ CAS の active 判定に注意

`contracts` の `status = 'active'` だけでは不十分。`finished` 契約に将来 `end_date` が設定されているケースがある。
`customer_lifecycle.py` では `AND con.status = 'active'` を明示してフィルタ済み。

### ⚠️ CAS と SF の Plus 顧客数の乖離

```
CAS contracts active plus : ~953社 (free trial 等のノイズ含む)
SF CAREECON_Plus__c=true  :  270社 (真のアクティブ Plus)
sf_customers ホワイトリスト:  ~234社 (CID 補填後、kpi-update ごとに更新)
```

---

## 未着手・次のステップ

- [ ] `工程作成` の指標を「新規作成数」→「進捗更新数 (progress_updated_on)」に切り替え
- [ ] `ACTIVE_PLAN_TYPES` に `"mini"` を追加して mini 分析を開始
- [ ] output1 をオンボーディング除外版 (`lifecycle_stage = 'plus'` フィルタ) に変更
- [ ] 経営企画プロダクト (DS? 未確認) の指標化 → 別セッションで実施
- [ ] SF の CAREECON_CID__c 未設定 130社への入力依頼 (CS/実装担当) → 補填精度の向上

---

## 拡張時の注意点

### 新しいプロダクトを追加する場合

1. Redash でデータソース ID を確認 (DS1/DS7 相当を特定)
2. `kpi/work_user_history.py` に相当するフェッチモジュールを作成
3. `kpi/config.py` に `FEATURE_THRESHOLDS` を追加
4. `kpi/cli.py` の `fetch_tasks` とビルド処理に追加
5. `customer_lifecycle` は `contracts` ベースなので共用可能

### Mini 分析を追加する場合

`config.yml` の `active_plan_types: [plus, mini]` に変更するだけ。
ただし:
- Mini は施工管理の一部機能しか使えないため、閾値を Mini 向けに調整する必要がある
- `sf_customers` は現在 Plus のみ。Mini も含める場合は `sf_customers.py` の SOQL を変更する

### Salesforce フィールドの参照

`schema/salesforce.md` に全フィールド定義あり (21,000行超)。主要フィールド:

```
Account.CAREECON_CID__c         : 施工管理 UUID (= DuckDB の company_uuid)
Account.CAREECON_Plus__c        : Plus 契約フラグ
Account.CAREECON_Plus_Cancel__c : Plus 解約フラグ (true なら解約済み)
Account.CAREECON_mini__c        : mini 契約フラグ (旧)
Account.new_CAREECON_mini__c    : mini 契約フラグ (新)
Account.ContractStatus__c       : 契約中/解約/強制解約/倒産/AB
```

Redash で SOQL を直接実行する場合は DS11 (sf) を使う。SOQL の制約:
- `UNION` 非対応 → Plus と Mini は別クエリで取得
- `GROUP BY` でエイリアス使用不可 → 元の式を繰り返す
- `COUNT(DISTINCT ...)` を `GROUP BY` と組み合わせ不可 → Python 側で処理
