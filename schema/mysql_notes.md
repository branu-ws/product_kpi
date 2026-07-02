# MySQL スキーマノート (careecon_db / careecon_cas / careecon_work / keiei_plus_production)

このパイプラインが実際に依存しているテーブル・カラム・enum値のカタログ。
`schema/salesforce.md` の MySQL 版だが、SF 版と違い全カラム網羅ではなく
**`kpi/*.py` の生SQLが依存している部分だけ**を記載する。

⚠️ **正のソースは `kpi/*.py` の SQL 本体。** ここは検索性のためのインデックス。
実装を変更したら SQL を直接読むこと。カラムの追加・意味変更に気づいたらこのファイルも更新する。

バックエンドリポジトリのコードは読みに行かない — この抽出は `kpi/*.py` の
既存クエリだけから作られている。

---

## DS1: careecon_db (`REDASH.data_sources.db`)

| テーブル | カラム | 用途 |
|---|---|---|
| `companies` | `id`, `cid`(UUID), `name`, `zip`, `prefecture_id`, `city`, `address`, `deleted_at` | 会社マスタ。`id` は DS1 専用連番 (CAS `contracts.company_id` とは別体系)。`prefecture_id` は1-47の都道府県コード ([`sf_customers.py`](../kpi/sf_customers.py) の `_PREF_MAP` 参照) |

参照元: [`kpi/companies.py`](../kpi/companies.py), [`kpi/sf_customers.py`](../kpi/sf_customers.py) (`_DS1_SQL`)

---

## DS2: careecon_cas (`REDASH.data_sources.cas`)

| テーブル | カラム | 用途 |
|---|---|---|
| `contracts` | `company_id`, `item_id`, `status`, `start_date`, `end_date` | 契約。`status` は `'active'` / `'finished'`（`finished` でも将来 `end_date` を持つケースあり、要 `status='active'` 明示フィルタ） |
| `items` | `id`, `code`, `service_id` | 契約明細。`code` が `kpi.config.PLAN_TYPE_CODES` のキー (`business`, `business_annual`, `personal_annual`) |
| `services` | `id`, `code` | `code='careecon_work'` で施工管理プロダクトに絞る |
| `accounts` | `company_id`, `cid`(UUID) | CAS の `company_id` → UUID のブリッジ。DS1 `companies.cid` と同じ UUID 空間 |

参照元: [`kpi/contracts.py`](../kpi/contracts.py), [`kpi/sf_customers.py`](../kpi/sf_customers.py) (`_CAS_ACCOUNTS_SQL`)

---

## DS7: careecon_work (`REDASH.data_sources.work`)

### プロジェクト・ユーザー基盤

| テーブル | カラム | 用途 |
|---|---|---|
| `projects` | `id`(=pid), `company_id`, `created_at` | 案件。`company_id` は `companies.id` (DS1相当、work内で完結) |
| `companies` (work内) | `id`, `cid`(UUID), `deleted_at` | DS7内の会社マスタ。DS1 `companies.cid` と同じ UUID |
| `users` | `id`, `uid`(UUID), `name`, `deleted_at`, `created_at` | `id`=整数連番, `uid`=UUID。両方使われる箇所あり (下記 fuzzy join 参照) |
| `companies_users` | `user_id`, `company_id` | ユーザー×会社の中間テーブル |

### 機能別イベント (work_user_history の元)

| テーブル | 主要カラム | content 値 | 備考 |
|---|---|---|---|
| `schedules` | `id`, `project_id` | — | `large_processes`/`small_processes` から `project_id` を引く中間テーブル |
| `large_processes` | `id`, `schedule_id`, `created_at`, `progress_updated_on` | `大工程` / `出来高` | オンボーディング時にテンプレ一括作成(8件)されるため契約開始月に件数が膨らむ |
| `small_processes` | `id`, `schedule_id`, `created_at`, `progress_updated_on` | `小工程` / `出来高` | 同上(24件)。`progress_updated_on` への切替が今後の検討事項 |
| `daily_reports` | `id`, `project_id`, `uid`(UUID), `construction_date`, `created_at` | `日報` | `uid` で `users.uid` と JOIN。写真有無問わず全件カウント |
| `attendances` | `id`, `project_id`, `user_id`, `work_date`, `check_in_at` | `出面` | `user_id` で `users.id` と JOIN。`check_in_at IS NOT NULL` → `platform='app'` |
| `reports` | `id`, `project_id`, `user_id`, `created_at`, `report_type`, `deleted_at` | `報告書` | `report_type=1` = AI生成(全体の99%が写真付き)。`deleted_at <= '1970-01-01'` が有効行 |
| `board_posts` | `id`, `project_id`, `created_at` | `掲示板` | ホワイトボード(ガントチャート)はログなし＝計測不可 |
| `content_resources` | `resource_id`, `resource_type`, `content_id` | — | `board_posts` の platform 判定用中間テーブル (`resource_type='BoardPost'`) |
| `contents` | `id`, `type`, `company_id`, `root_model`, `device_uuid`, `created_at` | `写真アップロード` / `フォルダ作成` | `type='Content::Image'` = 写真、`type='Content::Directory' AND root_model IS NULL` = ユーザー手動フォルダ作成。`device_uuid` 非空 → `platform='app'` |
| `ai_logs` | `cid`(UUID), `uid`(整数, `users.id` 相当), `tag`, `created_at` | `AIアシスタント` | `tag='start_session'` がアシスタント起動。`tag='save_report'` は日報AI利用の別イベント (`daily_report_photo` で使用) |
| `daily_reports_contents` | `daily_report_id` | — | 日報の添付写真。`daily_report_photo.photo_count` の集計元 |

`platform` の判定ロジックはテーブルごとに異なる（`device_uuid` 系 / `check_in_at` 系 / `content_resources` 経由の image 判定系）。詳細は [`kpi/work_user_history.py`](../kpi/work_user_history.py) の SQL を直接参照。

### ⚠️ has_ai の fuzzy join (daily_report_photo)

```
ai_logs.uid (整数) = users.id (整数)   ← ai_logs.uid は users.uid(UUID) ではなく users.id
users.uid (UUID)   = daily_reports.uid (UUID)
DATE(ai_logs.created_at) = DATE(daily_reports.created_at)  ← construction_date ではない
```

参照元: [`kpi/work_user_history.py`](../kpi/work_user_history.py), [`kpi/work_process_id_generator.py`](../kpi/work_process_id_generator.py), [`kpi/users.py`](../kpi/users.py)

---

## keiei_plus_production (経営管理, DS7 と同一 Redash データソース経由)

| テーブル | 主要カラム | content 値 | 備考 |
|---|---|---|---|
| `companies` | `id`, `cid`(UUID) | — | work版とは別スキーマだが同じ UUID 空間 |
| `projects` / `leads` | `id`, `company_id` | — | `project_progress_histories` / `lead_status_histories` の親 |
| `project_progress_histories` | `project_id`, `changed_at`, `deleted_at` | `案件ステータス更新` | |
| `lead_status_histories` | `lead_id`, `changed_at`, `deleted_at` | `案件ステータス更新` | project版とUNION |
| `documents` | `company_id`, `transaction_type`, `status`, `created_at`, `deleted_at` | `見積原価登録`/`見積売上登録`/`実績原価登録`/`実績売上登録` | `status=5`固定。`transaction_type`: `1`=実績原価 `2`=見積売上 `3`=見積原価 `4`=実績売上 |
| `invoice_pdfs` | `company_id`, `status`, `confirmed_at`, `deleted_at` | `請求書発行` | `status=1` かつ `confirmed_at IS NOT NULL` |
| `document_pv_logs` | `company_id`, `page_name`, `created_at` | `原価ページPV` | `page_name='estimated_cost'` |
| `ocr_documents` | `company_id`, `ocr_status`, `ocr_completed_at`, `deleted_at` | `OCR処理` | `ocr_status=3` = 完了 |

`deleted_at = '1970-01-01 00:00:00'` は「未削除」を表す共通パターン（NULL ではない）。
テストアカウント除外: `company_id NOT IN (2, 8, 264, 64, 412)`（`keiei_user_history.py` の `_EXCLUDE_COMPANY_IDS`）。

参照元: [`kpi/keiei_user_history.py`](../kpi/keiei_user_history.py)

---

## Salesforce (DS11)

`schema/salesforce.md` に全フィールド定義あり。パイプラインが使う主要フィールドは
`CLAUDE.md` の「Salesforce フィールドの参照」節、突合ロジックは [`kpi/sf_customers.py`](../kpi/sf_customers.py) を参照。
