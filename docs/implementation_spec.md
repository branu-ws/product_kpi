# KPI パイプライン 実装仕様書

## 確定事項サマリー

| 項目 | 決定内容 |
|------|---------|
| 実行タイミング | **毎週日曜 夜 (JST)** — 将来の週次KPI拡張を見越した設計 |
| GCP プロジェクト | **新規作成** |
| BigQuery | **採用** — Looker Studio バックエンド + チームSQL分析 |
| Looker Studio | グラフ可視化の場所 |
| Notion | 実数字を見る場所 — 既存DBにレコードを追加していく |
| Cloud 監視 | 軽量運用。失敗時はメール通知 (yml に宛先登録) |
| テスト | unit test を一定やる。E2E は後回し |

---

## アーキテクチャ

```
Cloud Scheduler (毎週日曜 22:00 JST)
        │
        ▼
Cloud Run (Python pipeline)
        │
        ├─► BigQuery (永続ストレージ / チームSQL分析)
        │         │
        │         ├─► Looker Studio (グラフ可視化)
        │         │
        │         └─► Google Sheets (BigQuery Export or GAS読み込み)
        │                   │
        │                   ▼
        │             GAS (UrlFetchApp)
        │                   │
        │                   ▼
        │             Notion API (既存DBのレコード upsert)
        │
        └─► Cloud Logging + Email 通知 (失敗時)
```

---

## 実装ロードマップ

### Phase 0: keiei 実装完了 【優先度: 最高】

- [x] `keiei_user_history.py` の DS_ID 確定 → DS7 (careecon_work) で `keiei_plus_production.*` クロスDB参照が動作確認済み
- [x] `keiei_user_history.fetch()` の動作確認 → 8,933件取得成功 (2026-06-17)
- [ ] `uv run python update_duckdb.py` でパイプライン全体が通ることを確認
- [ ] `feature_health.build_keiei()` の出力を手動検証
- [ ] `company_loyalty.build_keiei()` の出力を手動検証

**確認方法:**
```bash
uv run python -c "
import httpx
from kpi import keiei_user_history
with httpx.Client() as c:
    df = keiei_user_history.fetch(c)
    print(df.head())
    print(df.dtypes)
"
```

---

### Phase 1: Unit Test 整備

**対象モジュール (ロジックが複雑でリグレッションリスクが高い順):**

| モジュール | テスト内容 |
|-----------|-----------|
| `kpi/company_loyalty.py` | 各ティア境界値 (神/ファン/自走/離反状態 etc.) |
| `kpi/customer_lifecycle.py` | onboarding 3か月判定、plus優先ルール、retired判定 |
| `kpi/feature_health.py` | good/normal/bad の閾値判定、利用なし補完 (usage=0) |
| `kpi/config.py` | パラメータ変更が閾値に反映されることの確認 |

**方針:**
- テストデータは DuckDB in-memory で作るか pandas DataFrame をそのまま使う
- Redash API は mock しない (unit test スコープ外)
- `pytest` + `uv run pytest`

---

### Phase 2: コンテナ化 + Cloud Run デプロイ

- [ ] `Dockerfile` 作成 (uv ベース)
- [ ] 環境変数設計 (`REDASH_API_KEY`, `REDASH_BASE_URL`, `GCP_PROJECT_ID` etc.)
- [ ] GCP プロジェクト新規作成
- [ ] Service Account 作成 + 権限設定 (BigQuery 書き込み, Cloud Run 実行)
- [ ] Cloud Run へのデプロイ確認

**秘密情報の管理:**
```yaml
# config.yml (リポジトリに含める — API KEY 等は含めない)
notification:
  email:
    - t.tsuyama@branu.jp
schedule:
  cron: "0 22 * * 0"   # 毎週日曜 22:00 JST (= 13:00 UTC)
gcp:
  project_id: ""        # 新規作成後に記入
  bq_dataset: "kpi"
```

---

### Phase 3: BigQuery 統合

**設計方針: pandas DataFrame が DuckDB/BigQuery の共通レイヤー**

```
kpi/ モジュール (DataFrame を返す)
        │
        ├─► DuckDB  (常にローカル保存)
        └─► BigQuery (USE_BIGQUERY=1 のときだけ追加で書く)
```

`update_duckdb.py` のコードは変更不要。環境変数だけで切り替わる。

**環境変数:**

```bash
# ローカル開発 (未設定 → DuckDB のみ)
uv run python update_duckdb.py

# Cloud Run 本番 (設定あり → DuckDB + BigQuery)
USE_BIGQUERY=1
GCP_PROJECT_ID=your-project-id
BQ_DATASET=kpi          # デフォルト値。変更不要なら省略可
```

**BigQuery テーブル設計:**

| テーブル名 | 内容 | 更新方式 |
|-----------|------|---------|
| `kpi.feature_health` | 企業×機能×月 のヘルス | WRITE_TRUNCATE (全書き換え) |
| `kpi.company_loyalty` | 企業×月 のロイヤリティ | WRITE_TRUNCATE |
| `kpi.customer_lifecycle` | 企業×月 のライフサイクル | WRITE_TRUNCATE |
| `kpi.keiei_feature_health` | 経営管理 ヘルス | WRITE_TRUNCATE |
| `kpi.keiei_company_loyalty` | 経営管理 ロイヤリティ | WRITE_TRUNCATE |

スキーマは pandas DataFrame から自動推論 (`autodetect=True`)。定義ファイル不要。

- [x] `kpi/db.py` に BigQuery 書き込みを追加 (`_save_bigquery()`)
- [ ] GCP プロジェクト新規作成 + `kpi` データセット作成
- [ ] `google-cloud-bigquery` を依存関係に追加 (`uv add google-cloud-bigquery`)
- [ ] Service Account 作成 + BigQuery 書き込み権限付与
- [ ] Cloud Run に環境変数 `USE_BIGQUERY`, `GCP_PROJECT_ID` を設定
- [ ] Looker Studio から BigQuery `kpi` データセットに接続して表示確認

---

### Phase 4: Notion 統合

**依存関係: SQL出力の設計が確定してから着手する**

SQL 出力 (`collections/*.sql` → CSV) が確定した後、以下の手順で進める:

1. **Notion DB スキーマ設計**
   - CSV の各カラム → Notion プロパティのマッピングを決定
   - 主キー (upsert キー) の決定: `company_uuid` + `usage_month` の組み合わせを推奨

2. **Notion 既存 DB 確認**
   - 対象の Notion DB の URL / ID を確認
   - 既存プロパティと追加が必要なプロパティをリストアップ

3. **GAS スクリプト作成**

```javascript
// upsert パターン
function syncToNotion(rows) {
  const NOTION_TOKEN = PropertiesService.getScriptProperties().getProperty('NOTION_TOKEN');
  const DB_ID = PropertiesService.getScriptProperties().getProperty('NOTION_DB_ID');

  rows.forEach(row => {
    // ① company_uuid + usage_month で既存レコードを検索
    const existing = queryNotionDB(DB_ID, NOTION_TOKEN, row.company_uuid, row.usage_month);

    if (existing) {
      // ② 見つかれば PATCH で更新
      updateNotionPage(existing.id, NOTION_TOKEN, row);
    } else {
      // ③ なければ POST で新規作成
      createNotionPage(DB_ID, NOTION_TOKEN, row);
    }
  });
}
```

4. **Sheets → GAS → Notion の結合テスト**

---

### Phase 5: Cloud Scheduler + アラート設定

- [ ] Cloud Scheduler ジョブ作成 (毎週日曜 22:00 JST)
- [ ] Cloud Run 失敗時の Email 通知設定 (Cloud Monitoring アラート)
- [ ] `config.yml` に通知先メアドを登録

---

## 未決事項トラッカー

| # | 項目 | ステータス | アクション |
|---|------|-----------|-----------|
| 1 | keiei Redash クエリID | **解決済み** | DS7で動作確認済み (2026-06-17) |
| 2 | SQL 出力設計の確定 | 流動的 | keiei 実装完了後に確定 |
| 3 | Notion 対象 DB | SQL確定後 | SQL確定後に URL 共有 → スキーマ設計 |
| 4 | GCP プロジェクト名 | 未作成 | Phase 2 着手時に作成 |
| 5 | 週次KPI 指標の定義 | 未決 | 将来セッションで議論 |

---

## ローカル開発フロー (現状維持)

```bash
# データ取得 + DuckDB 再構築
uv run python update_duckdb.py

# SQL → CSV 出力
uv run python main.py collections/*.sql

# テスト
uv run pytest
```

Cloud Run でも同じコマンドを実行するイメージ。`REDASH_API_KEY` 等を環境変数で注入するだけ。
