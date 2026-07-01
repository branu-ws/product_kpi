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

### イベントログ (Redash fetch)

```
work_user_history         : 機能別利用イベント
                            (pid, content, content_date, source_id, user_id)
                            ※ user_id は日報・出面・報告書のみ非 NULL
work_process_id_generator : pid → company_uuid のブリッジ
companies                 : company_uuid, company_name  ← DS7 (住所なし)
contracts                 : company_uuid, plan_type, status, start_date, end_date
users                     : user_id, user_uuid, user_name, company_uuid
sf_customers              : company_uuid のホワイトリスト (SF Plus 確認済み) [毎回自動更新]
ai_user_history           : AIアシスタント利用イベント (company_uuid, content, content_date)
                            ← ai_logs.cid を直接使用 (pid なし)
contents_user_history     : 写真アップロード・フォルダ作成イベント (company_uuid, content, content_date)
                            ← contents テーブルから company_uuid 変換済み
```

### イベント属性テーブル (ファネル分析の基礎DB)

```
daily_report_photo        : 日報ごとの写真情報
                            (source_id, has_photo, photo_count, has_ai, lag_days)
                            ← daily_reports_contents から集計
                            has_ai: ai_logs.tag='save_report' × users 経由の fuzzy join
                              JOIN キー: ai_logs.uid=users.id(整数) / daily_reports.uid=users.uid(UUID)
                              比較日付: DATE(ai_logs.created_at) = DATE(daily_reports.created_at)
                              ※ construction_date(施工日) ではなく created_at(登録日) で照合するのが正しい
                                 遡り書きでも「書いた日 == AI使った日」で一致するため
                            lag_days: DATEDIFF(created_at, construction_date)
                              = 施工日から何日後に日報を登録したか（0=当日、正=遡り）
                              例: 34日後に登録するケースあり → 遡りパターンの行動分析に使える
report_attrs              : 報告書ごとのAI生成フラグ
                            (source_id, has_ai)
                            ← reports.report_type = 1 が AI 生成
```

属性テーブルは `work_user_history.source_id` で JOIN する。行を増やさないのでダブルカウントなし。

### 派生テーブル (KPI 計算結果)

```
customer_lifecycle        : company_uuid × usage_month × lifecycle_stage
feature_health            : company_uuid × feature × usage_month × health
company_loyalty           : company_uuid × usage_month × loyalty_tier
```

### ⚠️ company_uuid ベーステーブルの UNION パターン

`ai_user_history` と `contents_user_history` は pid を持たず company_uuid が直接入る。
`feature_health._build_work()` の `_company_uuid_union()` ヘルパーで UNION ALL している。
テーブルが DuckDB に存在しない場合（テスト等）は自動でスキップされる。

### `sf_customers` テーブル (重要)

- **ソース**: Salesforce `CAREECON_Plus__c = true AND CAREECON_Plus_Cancel__c = false` の全アカウント
- **生成**: `kpi/sf_customers.py` が `kpi-update` のたびに自動実行して最新化
- **目的**: CAS の `contracts` には free trial・未導入企業が多数混入（953社 → 実態 ~250社）するため、SF を真の Plus 顧客のソース・オブ・トゥルースとして使う
- **補填ロジック**: SF で `CAREECON_CID__c` が未設定の約130社は、DS1 `companies` テーブルと社名＋都道府県＋市区の段階的マッチングで UUID を補填（高→中→低の3段階）
- **適用**: `customer_lifecycle.py` の `active_ranked` / `retired_ranked` CTE が `sf_all_plus_customers` に INNER JOIN → テーブルが未登録の環境 (テスト等) では JOIN を省略して動く
- **`sf_customers`** (現在アクティブのみ) と **`sf_all_plus_customers`** (解約済み含む) の2テーブルを生成。`customer_lifecycle` は後者を使うことで解約済み顧客の過去月が正しく復元される

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
- `feature_health`、`single_product`、`cross_product` はこのテーブルから lifecycle_stage を取得

---

## 計測対象機能と閾値

⚠️ **閾値の正値は `config.yml` の `kpi.feature_thresholds` が唯一のソース。CLAUDE.md に数値を書かない。**

| 機能 | データソース |
|------|------------|
| 工程作成 | large_processes + small_processes (合算) |
| 出面 | attendances |
| 出来高 | progress_updated_on |
| 掲示板 | board_posts |
| 日報 | daily_reports (全件、写真有無問わず) |
| 報告書 | reports (99% が写真付き) |
| AIアシスタント | ai_logs WHERE tag='start_session' → `ai_user_history` |
| 写真アップロード | contents WHERE type='Content::Image' → `contents_user_history` |
| フォルダ作成 | contents WHERE type='Content::Directory' AND root_model IS NULL → `contents_user_history` |

### ⚠️ 掲示板 (旧: ホワイトボード)

`board_posts` テーブルが掲示板。ホワイトボード（ガントチャート操作）はアクセスログが存在しないため計測不可。

### ⚠️ 工程作成の注意点

`work_user_history` の 大工程/小工程 は **新規作成イベント**をカウントしている。
オンボーディング時にテンプレート (大工程8 + 小工程24 = 32件) を一括作成するため、
契約開始月だけ件数が膨らみ翌月ゼロになるケースがある。
→ 将来的に `small_processes.progress_updated_on` (進捗更新数) への切り替えを検討中。

### ⚠️ フォルダ作成 と 写真アップロード はダブルカウントしない

- 写真アップロード = `Content::Image` 作成イベント
- フォルダ作成 = `Content::Directory` かつ `root_model IS NULL`（ユーザー手動作成のみ）
- 写真をアップロードしても `root_model IS NULL` のフォルダは自動生成されない → 独立した指標

---

## 顧客ティア階層

単一プロダクト (`diversity_tier` in `kpi/single_product.py`) と
クロスプロダクト (`integration_tier` in `kpi/cross_product.py`) が Notion の実画面。

| ティア | 表示名 | 条件 |
|--------|--------|------|
| fan | ファン | normal 以上の機能数 ≥2 × 直近3か月連続 (`fan_feature_min`) |
| proactive | 自走 | normal 以上の機能数 ≥1 × 直近3か月連続 (`proactive_feature_min`) |
| onboarding | オンボーディング | lifecycle_stage = onboarding-* (上記より優先) |
| passive | 放置 | 上記いずれにも該当しない |

クロスプロダクトの fan/proactive は work と keiei 両方のスコアで判定（詳細は `kpi/cross_product.py`）。
閾値は `config.yml` の `tier:` セクションで変更可能（コード修正不要）。

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

---

## 未着手・次のステップ

### 短期
- [ ] `kpi-update` を実行して新機能（AIアシスタント・写真アップロード・フォルダ作成）を DuckDB に反映し、GCS チャートを再生成・アップロード
- [ ] `工程作成` の指標を「新規作成数」→「進捗更新数 (progress_updated_on)」に切り替え
- [ ] SF の CAREECON_CID__c 未設定 130社への入力依頼 (CS/実装担当) → 補填精度の向上

### 中期 (別 User Story)
- [ ] **ファネル分析**: `daily_report_photo` + `report_attrs` で「日報→写真付き→AI使用」のファネルを可視化（基礎DB構築済み）
- [ ] **エース級個人の特定**: `work_user_history.user_id` × `users` テーブルで個人別集計
- [ ] `ACTIVE_PLAN_TYPES` に `"mini"` を追加して mini 分析を開始
- [ ] 経営企画プロダクト (DS? 未確認) の指標化

---

## 拡張時の注意点

### 新しいプロダクトを追加する場合

1. Redash でデータソース ID を確認 (DS1/DS7 相当を特定)
2. `kpi/work_user_history.py` に相当するフェッチモジュールを作成
3. `kpi/config.py` に `FEATURE_THRESHOLDS` を追加
4. `kpi/cli.py` の `fetch_tasks` とビルド処理に追加
5. `customer_lifecycle` は `contracts` ベースなので共用可能

### Mini 分析（稼働中）

Mini 向けの Tier Health / ヒートマップチャートは既に稼働している。

**Mini 顧客フィルタ設計 (`mini_only` CTE)**

```sql
WITH mini_only AS (
    SELECT DISTINCT company_uuid FROM mini_customer_lifecycle
    EXCEPT
    SELECT company_uuid FROM sf_customers  -- Plus 確認済みを除外
)
```

`mini_customer_lifecycle` は `build_work_mini()` が `plan_types=["plus","mini"]` で構築するため、
plan_type='plus' のレコードも含む。そのため `WHERE plan_type='mini'` は**使わない**。
`sf_customers`（Salesforce Plus 確認済み）に含まれる企業を除外することで
「CAS上はplus/miniいずれかだが、SF では Plus 登録されていない = 実質 Mini」を抽出する。

`mini_sf_customers` テーブルは使わない（範囲が広すぎるため）。

DuckDB テーブル: `mini_customer_lifecycle`, `mini_work_monthly_company`, `mini_work_company_weekly`,
`mini_feature_health` が `build_work_mini()` によって生成される。

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

SOQL の制約: `UNION` 非対応 / `GROUP BY` でエイリアス使用不可 / `COUNT(DISTINCT ...)` を `GROUP BY` と組み合わせ不可（Python 側で処理）。

---

## Notion グラフ注入ワークフロー

DuckDB → Plotly HTML → GCS → Notion embed の流れ。

| リソース | 値 |
|---------|-----|
| GCS バケット | `gs://product-kpi-charts-branu` (公開、asia-northeast1) |
| 公開 URL パターン | `https://storage.googleapis.com/product-kpi-charts-branu/{filename}.html` |
| Notion API Key | `.env` の `NOTION_API_KEY` |

グラフスクリプトは `charts/plot_*.py` → `output/html/` に HTML 出力。GCS 上書きで Notion 側は自動反映（embed ブロックを削除→再作成するとリサイズがリセットされるので注意）。

### 共有ヒートマップモジュール (`kpi/heatmap.py`)

顧客別機能ヒートマップの共通ロジック。薄いラッパーを `charts/plot_*_heatmap.py` に置く構成。
カラースケール: bad=水色 / normal=ビビッドブルー / good=ロイヤルブルー。
