# [TEMP] Notion × Plotly 可視化 開発ステップ

> **このファイルは開発完了後に削除すること。**
> 完了条件: Notion ページが本番運用に入り、GCP 自動更新が安定稼働したとき。

---

## 開発ステップ

### Step 1: ローカルで Plotly HTML 出力 ✅
- `scripts/plot_xproduct_segment_trend.py` で X-PRODUCT セグメント時系列グラフを作成
- 出力: `output/html/xproduct_segment_trend.html`

### Step 2: Notion 埋め込みテスト ✅
- GCS バケット `gs://product-kpi-charts-branu` を作成（公開バケット、asia-northeast1）
- HTML を GCS にアップロード → Notion に embed ブロックとして注入
- Plotly のインタラクティブ操作（ホバー・ズーム）が Notion iframe 内で動作確認済み
- GCS ファイルを上書きしても Notion 側のリサイズ設定は保たれることを確認済み

### Step 3: kpi-update への自動組み込み 🔲
- `kpi-update` 完了時に Plotly スクリプトを自動実行
- `gcloud storage cp` で GCS へアップロード（Notion 側変更不要）
- `kpi/cli.py` の末尾に処理を追加する

### Step 4: グラフを増やす 🔲
- X-PRODUCT セグメント時系列（完了）
- 追加候補: feature_health 推移、company_loyalty 推移、週次トレンド など
- グラフごとに `scripts/plot_*.py` を作成し、対応する GCS パスに出力

### Step 5: Notion ページを完成させる 🔲
- グラフ配置・テキスト説明・更新日表示などページとして整える
- 更新日は `kpi-update` 実行時に Notion API でテキストブロックを更新する

---

## 【要対応】BQ カラム名の日本語化検討

**背景**:
現在 BigQuery 向けのカラム名は英語に統一されている。
理由は Looker Studio が日本語カラム名を表示できないため。

**Notion + Plotly が成功した場合**:
- Looker Studio への依存が下がる
- Plotly は Python 側でラベルを自由に設定できるため、DuckDB / BQ のカラム名が日本語でも問題ない
- → BQ テーブルのカラム名を日本語（または読みやすい表現）に戻せるか検討する

**対応タイミング**: Step 3 完了後、Looker Studio 廃止判断と合わせて実施。
