# product_kpi

ご安全に！！！！

Redash からデータを引き抜き、DuckDB にキャッシュ、顧客ティアと機能ヘルスを月次集計して Notion に自動展開するパイプラインだ。
最前線の意思決定を支える重要任務と心得てくれ！

## 作戦全体図

```
Cloud Scheduler (毎週月曜 2am JST) ← 定期実行
        │
        ▼
Cloud Run Job (kpi-pipeline-job)
        │
        └─► Notion API (DB 同期 + チャート embed)
```

出力はこのリポジトリをいじることで調整可能だ。
ローカル開発は `uv run python` で動く。`.env` に `REDASH_API_KEY` と `NOTION_API_KEY` を登録するだけだ！

---

## KPI の考え方・指標定義

KPI の設計思想・指標の算出ロジック・config.yml での調整方法は `docs/` に詳細をまとめている。コードを読む前にまずここを参照してくれ！

| ドキュメント | 内容 |
|------------|------|
| [docs/single_product_kpi.md](docs/single_product_kpi.md) | 単一プロダクト KPI（施工管理・経営管理）の指標定義・ティア判定・config 設定 |
| [docs/cross_product_kpi.md](docs/cross_product_kpi.md) | クロスプロダクト KPI（2 プロダクト横断）の指標定義・ティア判定・config 設定 |
| [docs/known_issues.md](docs/known_issues.md) | 顧客母集団の既知の問題（free trial 混入・SF 未設定など）と対応状況 |

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
# ステップ1: Redash からデータを引き抜いて DuckDB に弾薬充填する
uv run kpi-update

# ステップ2: Notion へ速報を送れ
uv run kpi-sync

# ステップ3: テストで品質を死守せよ
uv run pytest
```

---

## データフロー

```
Redash API / Salesforce
        │
        ▼
DuckDB (正規化テーブルを計算・保存) ← cache.duckdb
        │
        ├─► Notion DB (kpi-sync)
        └─► Plotly HTML → GCS → Notion embed (kpi-update)
```

---

## Notion 出力一覧

| Notion DB | SQL | time_col |
|-----------|-----|----------|
| クロスプロダクト利用マトリクス | `collections/notion/cross_product/cross_product_combined_matrix.sql` | combined |
| 施工管理 単一プロダクト利用 | `collections/notion/work/single_product_matrix.sql` | combined |
| 経営管理 単一プロダクト利用 | `collections/notion/keiei/single_product_matrix.sql` | combined |
| 施工管理 Mini 単一プロダクト利用 | `collections/notion/work_mini/single_product_matrix.sql` | combined |

`time_col: "combined"` は過去完了月 (`YYYY-MM`) + 当月週次 (`YYYY-MM-W1` …) を横展開する形式だ。

---

## デプロイ手順

> ⚠️ **コードや SQL を変えたら必ず `docker_deploy.sh` を実行せよ！**
> Cloud Run が使うのはイメージ内のコードだ。ローカルの変更はデプロイしない限り反映されないぞ！

### 初回セットアップ手順 (この順番で実行せよ！)

**ステップ1: GCP 認証**

```bash
bash auto/setup.bash
```

**ステップ2: Docker イメージをビルド & プッシュ**

```bash
bash auto/docker_deploy.sh
```

**ステップ3: Cloud Run Job・シークレットをまとめてセットアップ**

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
