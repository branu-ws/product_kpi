# product_kpi

ご安全に！！！！

Redash からデータを引き抜き、DuckDBにデータ格納、顧客ロイヤリティと機能ヘルスを月次集計して BigQuery・Notion に自動展開するパイプラインだ。
最前線の意思決定を支える重要任務と心得てくれ！

## 作戦全体図

```
Cloud Scheduler (毎週月曜 2am JST) ← 定期実行
        │
        ▼
Cloud Run Job (kpi-pipeline-job)
        │
        ├─► BigQuery (kpi dataset) ─► Looker Studio
        │
        └─► Notion API
```
出力はこのレポジトリをいじることで調整可能だ。
調整した後の反映方法は下に記述している。
テスト用にローカル稼働も可能だ。BigQueryの代わりにduckDBを使っているぞ。
ローカル開発は `uv run python` で動く。`.env` に `REDASH_API_KEY` と `NOTION_API_KEY` を登録するだけだ！

---

## 準備

### 必要な装備

- Python 3.12 以上
- [uv](https://docs.astral.sh/uv/)

### セットアップ手順

```bash
# まずセットアップ
uv sync

# .env に API キーを登録してくれ！これがないと作戦は始まらんぞ！
cp .env.example .env
# .env を開いて以下のAPIキーを注入せよ！
# REDASH_API_KEY=...
# NOTION_API_KEY=...
```

---

## ローカル実行

```bash
# ステップ1: Redash からデータを引き抜いて DuckDB に弾薬充填する（BigQuery なし・高速）
uv run kpi-update

# ステップ1b: DuckDB + BigQuery に同時書き込む（GCP_PROJECT_ID は config.yml から自動読込）
uv run kpi-bq-update

# ステップ2: Notion へ速報を送れ
uv run kpi-sync

# ステップ3: CSV に出力して手元で確認したいときはこちら
uv run kpi-export collections/bigquery/kpi/output1_loyalty_distribution.sql

# ステップ4: テストで品質を死守せよ
uv run pytest
```

---

## 新しい指標を Looker Studio に追加する方法

**`collections/` に SQL ファイルを置くだけだ！** 次回の `kpi-update` で自動的に BigQuery に反映されるぞ。

```
collections/
  output1_loyalty_distribution.sql    → BigQuery: kpi.output1_loyalty_distribution
  output6_cross_product_matrix.sql    → BigQuery: kpi.output6_cross_product_matrix
  keiei/
    output1_loyalty_distribution.sql  → BigQuery: keiei.output1_loyalty_distribution
  新プロダクト/
    output1.sql                       → BigQuery: 新プロダクト.output1  ← 自動でデータセット作成
```

**サブディレクトリ = BigQuery データセット**になる。プロダクトごとに分けておけば Looker Studio のアクセス権限もデータセット単位で管理できるぞ。

Looker Studio は**1つのレポートで複数テーブルを参照できる**。グラフごとに別テーブルを指定したり、「データブレンド」で複数テーブルを結合したりすることも可能だ。

---

## DuckDB と BigQuery の使い分け

役割が明確に分かれているぞ！

```
Redash API
    │
    ▼
DuckDB (正規化テーブルを計算・保存)
    │
    ├─► cache.duckdb  ← ローカル開発・Notion 同期用
    │
    └─► collections/**/*.sql を実行
            │
            └─► BigQuery (集計済みテーブルのみ) ← Looker Studio 用
```

| | DuckDB | BigQuery |
|---|---|---|
| **何を保存** | 正規化テーブル (`feature_health` 等) | `collections/*.sql` の集計結果のみ |
| **役割** | 計算エンジン＋ローカルキャッシュ | Looker Studio に食わせる置き場 |
| **更新** | `kpi-update` のたびに全書き換え | Cloud Run 実行時に WRITE_TRUNCATE |
| **必要な設定** | なし（デフォルト） | `USE_BIGQUERY=1` + `GCP_PROJECT_ID` |

---

## BigQuery への書き込み方法は3通りある

> ⚠️ **コードや SQL を変えたら必ず `docker_deploy.sh` を実行せよ！**
> Cloud Run が使うのはイメージ内のコードだ。ローカルの変更はデプロイしない限り反映されないぞ！

### ① ローカルから直接 BigQuery に書き込む

ローカルで最新データを確認したいときに使え。

```bash
uv run kpi-bq-update
```

GCP プロジェクト ID は `config.yml` の `gcp.project_id` から自動で読み込まれる。環境変数の手入力は不要だ。

### ② Cloud Run を手動でトリガーして実行

GCP コンソール or gcloud から手動でジョブを発火させる。

```bash
gcloud run jobs execute kpi-pipeline-job \
  --region=asia-northeast1 --wait
```

または [GCP コンソール](https://console.cloud.google.com/run/jobs?project=product-department-496703) からジョブを選択して「実行」ボタンでもいい。

### ③ Cloud Scheduler による自動実行を待つ

何もしなくても **毎週月曜 2:00 JST** に自動実行される。

---

## デプロイ手順

### 初回セットアップ手順 (この順番で実行せよ！)

**ステップ1: GCP 認証**

```bash
bash auto/setup.bash
```

gcloud へのログインと、Python から GCP を触るための認証を設定する。

**ステップ2: Docker イメージをビルド & プッシュ**

```bash
bash auto/docker_deploy.sh
```

**ステップ3: Cloud Run Job・BigQuery・シークレットをまとめてセットアップ**

```bash
bash auto/setup_cloudrun.sh
```

REDASH_API_KEY と NOTION_API_KEY の入力を求められるので入力せよ。
以下を一括でやってくれるぞ：
- BigQuery データセット (`kpi`) の作成
- Secret Manager への API キー登録
- Cloud Run Job の作成 + 環境変数・シークレットの設定

**ステップ4: Cloud Scheduler の設定**

```bash
bash auto/setup_scheduler.sh
```

以上で本番稼働開始だ！

### コードや SQL を変更したらデプロイ

```bash
bash auto/docker_deploy.sh
```

イメージを build → Artifact Registry に push する。②③ の実行に反映されるのは**デプロイ後**からだ。

### スケジュールを変更したいとき

`auto/setup_scheduler.sh` の `SCHEDULE` を書き換えてから再実行せよ。

```bash
bash auto/setup_scheduler.sh
```

**油断大敵！！Docker にアップしたら GitHub の更新とマージも忘れるな！**
他の人がローカルの古いコードで Docker を上書きすると先祖がえりが起きるぞ。

```bash
git add codefiles_to_updates
git commit -m "feat: ○○を変更"
git push origin branch名
```

---

## 機密情報と設定ファイルの管理

| ファイル | 用途 | git 管理 |
|---------|------|---------|
| `.env` | API キー等の機密情報。絶対に漏らすな！規律違反！！ダメ絶対！ | ❌ 除外 |
| `.env.example` | `.env` のテンプレート | ✅ |
| `config.yml` | GCP・Notion・スケジュール設定。機密なし | ✅ |

### config.yml の主要項目

```yaml
gcp:
  project_id: "product-department-496703"
  bq_dataset: "kpi"

notion:
  months_to_show: 18          # Notion に展開する月数
  outputs:
    - name: "cross_product_matrix"
      sql: "collections/output6_cross_product_matrix.sql"
      db_id: "..."
      ds_id: "..."
    # 新しい出力を追加するときはここに追記するだけだ！
```

---

## 戦況レポート一覧

### BigQuery (`kpi` dataset)

| テーブル | 内容 |
|---------|------|
| `feature_health` | 企業 × 機能 × 月 のヘルス (good/normal/bad) |
| `company_loyalty` | 企業 × 月 のロイヤリティ階層 |
| `customer_lifecycle` | 企業 × 月 のライフサイクルステージ |
| `keiei_feature_health` | 経営管理プロダクト ヘルス |
| `keiei_company_loyalty` | 経営管理プロダクト ロイヤリティ |

### Notion

| DB 名 | SQL | 構造 |
|------|-----|------|
| クロスプロダクト月別マトリクス | `output6_cross_product_matrix.sql` | 指標が行・月が列（最新18ヶ月） |

### CSV (`output/csv/`)

```bash
uv run kpi-export collections/*.sql
```

| ファイル | 内容 |
|---------|------|
| `output1_loyalty_distribution.csv` | 月別ロイヤリティ分布 |
| `output2_feature_health_summary.csv` | 月別機能ヘルス分布 |
| `output3_loyalty_trend.csv` | 企業別ロイヤリティ推移 |
| `output4_feature_health_trend.csv` | 機能別ヘルス推移 |

---

## プッシュ前の品質確認！ここは死守するんだ！

AI開発は規律を乱す！！ ゆえにlint が鬼厳しいモードに設定した。
品質管理の観点で下記の通過を確実に確認してからプッシュしてくれよな！

```bash
# Lint チェック
uv run ruff check .

# フォーマットチェック
uv run ruff format --check .

# 型チェック
uv run mypy .

# ユニットテスト
uv run pytest
```

pre-commit フックを入れておけば自動で守ってくれるぞ！初回だけ実行してくれ！

```bash
uv run pre-commit install
```

諸君の継続的な開発を期待しているぞ！健闘を祈る！解散！！
