# product_kpi

ご安全に！！！！

Redash からデータを引き抜き、DuckDB にキャッシュ、顧客ティアと機能ヘルスを月次集計して BigQuery・Notion に自動展開するパイプラインだ。
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

出力はこのリポジトリをいじることで調整可能だ。
調整した後の反映方法は下に記述している。
テスト用にローカル稼働も可能だ。BigQuery の代わりに DuckDB を使っているぞ。
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
# .env を開いて以下の API キーを注入せよ！
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

# ステップ3: テストで品質を死守せよ
uv run pytest
```

---

## KPI 指標の設計

### ティア判定 (多様性スコア)

利用機能の多様性を**直近 3 ヶ月ローリング**で判定する。稼働日割でスコアを正規化しているので祝日の多い月もフェアに評価できる。

| ティア | 単一プロダクト (diversity_tier) | クロスプロダクト (integration_tier) |
|--------|-------------------------------|-------------------------------------|
| **onboarding** | lifecycle_stage が onboarding-* | 同左 |
| **fan** | 直近 3 ヶ月すべてで normal+ 機能 ≥ 2 | 直近 3 ヶ月すべてで work・keiei 両スコア ≥ 1 |
| **proactive** | 直近 3 ヶ月すべてで normal+ 機能 ≥ 1 | 直近 3 ヶ月すべてで work または keiei スコア ≥ 1 |
| **passive** | 上記以外 | 上記以外 |

### 利用頻度 (usage_freq)

機能スコア合計を稼働日割で算出する。

| usage_freq | 条件 (feature_score または total_score) |
|------------|-----------------------------------------|
| good | ≥ 5 |
| normal | ≥ 3 |
| bad | < 3 |

### 機能スコアの算出

| スコア | 条件 |
|--------|------|
| 2 (good) | 稼働日割利用回数 ≥ good_min / avg_days |
| 1 (normal) | 稼働日割利用回数 ≥ normal_min / avg_days |
| 0 (bad) | それ以外 |

閾値は `config.yml` の `kpi.feature_thresholds` / `kpi.keiei_feature_thresholds` で管理。

---

## 設定ファイル (config.yml)

**すべての設定はここに集約している。** コードをいじらずパラメータを変更できるぞ。

```yaml
kpi:
  tier:
    rolling_months:        3   # fan/proactive 判定のローリング期間 (月)
    weekly_window:        12   # 週次表示の対象週数
    avg_months:           12   # 稼働日平均の参照月数
    fan_feature_min:       2   # 単一プロダクト fan: normal+ 機能数の最小値
    proactive_feature_min: 1   # 単一プロダクト proactive: 同上
    xproduct_score_min:    1   # クロスプロダクト fan/proactive: 各プロダクトスコアの最小値
    usage_freq_good:       5   # usage_freq good の閾値
    usage_freq_normal:     3   # usage_freq normal の閾値

redash:
  base_url: "https://redash.careecon.jp"
  data_sources:
    db:   1   # careecon_db — companies マスタ
    cas:  2   # careecon_cas — contracts, accounts
    work: 7   # careecon_work — 施工管理・経営管理 利用履歴
  saved_queries:
    work_user_history: 914
```

---

## BigQuery と Notion で SQL ファイルが分かれている理由

`collections/` の下に `bigquery/` と `notion/` の 2 ディレクトリがある。同じ指標でも **表示ツールの要件が違う**ため、別ファイルで管理している。

| | BigQuery (`collections/bigquery/`) | Notion (`collections/notion/`) |
|---|---|---|
| **形式** | 縦持ち (tidy format) | 横持ち (月 + 週がカラム) |
| **理由** | Looker Studio がピボット・フィルタを自在にかけられる | Notion のテーブルはそのまま表示されるので読みやすい横持ちが最適 |
| **time_col** | `DATE` 型 | `YYYY-MM` or `YYYY-MM-Wn` 文字列 |

---

## DuckDB と BigQuery の使い分け

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

---

## DuckDB 正規化テーブル一覧

| テーブル | 内容 |
|---------|------|
| `customer_lifecycle` | 企業 × 月 × ライフサイクルステージ |
| `feature_health` | 企業 × 機能 × 月 のヘルス (施工管理) |
| `keiei_feature_health` | 同上 (経営管理) |
| `work_monthly_company` | 企業 × 月 × diversity_tier + usage_freq (施工管理) |
| `work_company_weekly` | 企業 × 週 × usage_freq + diversity_tier (施工管理) |
| `keiei_monthly_company` | 同上 (経営管理) |
| `keiei_company_weekly` | 同上 (経営管理) |
| `cross_product_monthly_company` | 企業 × 月 × integration_tier + usage_freq (クロスプロダクト) |
| `cross_product_company_weekly` | 企業 × 週 × usage_freq + integration_tier |

---

## Notion 出力一覧

| Notion DB | SQL | time_col |
|-----------|-----|----------|
| クロスプロダクト利用マトリクス | `collections/notion/cross_product/cross_product_combined_matrix.sql` | combined |
| 施工管理 単一プロダクト利用 | `collections/notion/work/single_product_matrix.sql` | combined |
| 経営管理 単一プロダクト利用 | `collections/notion/keiei/single_product_matrix.sql` | combined |

`time_col: "combined"` は過去完了月 (`YYYY-MM`) + 当月週次 (`YYYY-MM-W1` …) を横展開する形式だ。

---

## BigQuery への書き込み方法は 3 通りある

> ⚠️ **コードや SQL を変えたら必ず `docker_deploy.sh` を実行せよ！**
> Cloud Run が使うのはイメージ内のコードだ。ローカルの変更はデプロイしない限り反映されないぞ！

### ① ローカルから直接 BigQuery に書き込む

```bash
uv run kpi-bq-update
```

GCP プロジェクト ID は `config.yml` の `gcp.project_id` から自動で読み込まれる。

### ② Cloud Run を手動でトリガーして実行

```bash
gcloud run jobs execute kpi-pipeline-job \
  --region=asia-northeast1 --wait
```

### ③ Cloud Scheduler による自動実行を待つ

何もしなくても **毎週月曜 2:00 JST** に自動実行される。

---

## デプロイ手順

### 初回セットアップ手順 (この順番で実行せよ！)

**ステップ1: GCP 認証**

```bash
bash auto/setup.bash
```

**ステップ2: Docker イメージをビルド & プッシュ**

```bash
bash auto/docker_deploy.sh
```

**ステップ3: Cloud Run Job・BigQuery・シークレットをまとめてセットアップ**

```bash
bash auto/setup_cloudrun.sh
```

REDASH_API_KEY と NOTION_API_KEY の入力を求められるので入力せよ。

**ステップ4: Cloud Scheduler の設定**

```bash
bash auto/setup_scheduler.sh
```

以上で本番稼働開始だ！

### コードや SQL を変更したらデプロイ

```bash
bash auto/docker_deploy.sh
```

**油断大敵！！Docker にアップしたら GitHub の更新とマージも忘れるな！**

```bash
git add <変更ファイル>
git commit -m "feat: ○○を変更"
git push origin <branch名>
```

---

## 機密情報と設定ファイルの管理

| ファイル | 用途 | git 管理 |
|---------|------|---------|
| `.env` | API キー等の機密情報。絶対に漏らすな！規律違反！！ダメ絶対！ | ❌ 除外 |
| `.env.example` | `.env` のテンプレート | ✅ |
| `config.yml` | 閾値・Redash 接続先・Notion DB ID 等。機密なし | ✅ |

---

## プッシュ前の品質確認！ここは死守するんだ！

AI 開発は規律を乱す！！ゆえに lint が鬼厳しいモードに設定した。
品質管理の観点で下記の通過を確実に確認してからプッシュしてくれよな！

```bash
# Lint チェック
uv run ruff check .

# フォーマットチェック
uv run ruff format --check .

# 型チェック
uv run mypy kpi/

# ユニット + インテグレーションテスト
uv run pytest
```

pre-commit フックを入れておけば自動で守ってくれるぞ！初回だけ実行してくれ！

```bash
uv run pre-commit install
```

諸君の継続的な開発を期待しているぞ！健闘を祈る！解散！！
