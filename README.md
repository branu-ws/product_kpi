# get_kpi

ご安全に！！！！
Redash から戦場のデータを引き抜き、DuckDB に弾薬重点、顧客ロイヤリティと機能ヘルスを月次で可視化するパイプラインだ。最前線の意思決定を支える重要任務と心得てくれ！

## 出撃前の準備

### 必要な装備

- Python 3.12 以上
- [uv](https://docs.astral.sh/uv/)

### セットアップ手順

```bash
# まず弾薬を補充するんだ
uv sync

# .env に API キーを登録してくれ！これがないと作戦は始まらんぞ！
cp .env.example .env
# .env を開いて以下を注入せよ！
# REDASH_API_KEY=your_api_key_here
```

> **絶対に忘れるな！** `.env` に `REDASH_API_KEY` を登録しないと `update_duckdb.py` が機能しないぞ！真っ先に確認してくれ！いいな！

## 作戦手順

### ステップ1: データ取得 + DuckDB 再構築

```bash
uv run python update_duckdb.py
```

Redash から全データを引き抜いて `kpi_cache.duckdb` を更新する。初回と最新データが必要なときに実行してくれ！

### ステップ2: CSV 出力

```bash
# 全レポートを一斉出力する欲張りプランだ！
uv run python main.py collections/*.sql

# 特定レポートのみの倹約化向けプランだ
uv run python main.py collections/output1_loyalty_distribution.sql

# 出力先を指定したいときはこちらで頼んだぞ
uv run python main.py collections/output1_loyalty_distribution.sql --output result.csv
```

CSV は `output/csv/` に集結する。確認してくれ！

## 出力レポート一覧

| ファイル | 内容 |
|---------|------|
| `output1_loyalty_distribution.csv` | 月別ロイヤリティ分布（横ピボット） |
| `output2_feature_health_summary.csv` | 月別機能ヘルス分布 |
| `output3_loyalty_trend.csv` | 企業別ロイヤリティ推移 + 前月比フラグ |
| `output4_feature_health_trend.csv` | 機能別ヘルス推移 |

## プッシュ前の品質確認！ここは死守するんだ！

AI開発前提で lint が鬼厳しいモードに設定されているんだ。品質管理の観点で下記の通過を確実に確認してからプッシュしてくれよな！

```bash
# Lint チェック
uv run ruff check .

# フォーマットチェック
uv run ruff format --check .

# 型チェック
uv run mypy .
```

pre-commit フックを入れておけば自動で守ってくれるぞ！初回だけ実行してくれ！

```bash
uv run pre-commit install
```
諸君の継続的な開発を期待しているぞ！検討を祈る！解散！！