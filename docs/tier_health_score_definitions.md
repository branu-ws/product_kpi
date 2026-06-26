# 顧客ティア・ヘルススコア 定義書

> ソース: `config.yml` / `kpi/single_product.py` / `kpi/cross_product.py` / `kpi/customer_lifecycle.py`
> 最終更新: 2026-06-25

---

## 1. Lifecycle Stage（顧客フェーズ）

ティア判定の前提となる顧客フェーズ分類。`customer_lifecycle` テーブルに格納される。

| `lifecycle_stage` | 表示名 | 条件 |
|---|---|---|
| `onboarding-plus` | Plus オンボーディング | Plus 契約 かつ 契約開始月から **3ヶ月以内** |
| `plus` | Plus | Plus 契約 かつ 3ヶ月超 |
| `onboarding-mini` | Mini オンボーディング | Mini 契約 かつ 3ヶ月以内 |
| `mini` | Mini | Mini 契約 かつ 3ヶ月超 |
| `retired` | 解約済み | 全契約が終了し、当月にアクティブ契約なし |

**判定ルール:**
- plan_type と onboarding は独立した軸 → MECE
- 同一月に複数契約が重複する場合は **plus を優先** (ROW_NUMBER)
- Plus→Plus 更新はオンボーディングカウントをリセットしない
- Mini→Plus 移行はリセットする（plan_type 別 MIN 取得）

---

## 2. Feature Health Score（機能ヘルス）

各機能の利用頻度を **稼働日で正規化** して 3段階評価する。

### スコア変換

```
feature_score (per feature) =
  2  if  usage_count / working_days >= daily_good   (good)
  1  if  usage_count / working_days >= daily_normal (normal)
  0  otherwise                                       (bad)
```

`daily_good = good_min / avg_days`（過去12ヶ月の月平均稼働日で割る）

### 施工管理（Work）機能閾値

月あたりの利用回数基準（`config.yml: kpi.feature_thresholds`）

| 機能 | good_min | normal_min | 備考 |
|---|---|---|---|
| 工程作成 | 10 | 5 | 大工程＋小工程を合算 |
| 出面 | 10 | 5 | |
| 出来高 | 10 | 5 | |
| 掲示板 | 10 | 5 | |
| 日報 | 10 | 5 | |
| 報告書 | 10 | 5 | |

> ⚠️ 工程作成は「新規作成イベント」のカウント。オンボーディング時にテンプレート一括作成（32件程度）が発生し初月だけ跳ね上がるケースあり。

### 経営管理（Keiei）機能閾値

月あたりの利用回数基準（`config.yml: kpi.keiei_feature_thresholds`）

| 機能 | good_min | normal_min |
|---|---|---|
| 案件ステータス更新 | 2 | 1 |
| 見積原価登録 | 2 | 1 |
| 見積売上登録 | 2 | 1 |
| 実績原価登録 | 2 | 1 |
| 実績売上登録 | 2 | 1 |
| 請求書発行 | 2 | 1 |
| OCR処理 | 2 | 1 |
| 原価ページPV | 2 | 1 |

---

## 3. 単一プロダクト ティア（diversity_tier）

施工管理・経営管理それぞれ独立して判定する。`diversity_tier` カラムに格納。

### スコア集計

```
feature_score (monthly)  = sum of per-feature scores (max 12 for work / max 16 for keiei)
normal_plus_count        = count of features with feature_score >= 1 (normal or good)
```

### ティア判定ロジック（優先度順）

| 優先度 | ティア | 条件 |
|---|---|---|
| 1 | **Onboarding** | `lifecycle_stage` が `onboarding-*` |
| 2 | **Fan（ファン）** | 直近 **3ヶ月すべて**で `normal_plus_count >= 2` |
| 3 | **Proactive（自走）** | 直近 **3ヶ月すべて**で `normal_plus_count >= 1` |
| 4 | **Passive（放置）** | 上記いずれにも該当しない |

**ローリング判定の注意点:**
- ローリング期間 = **3ヶ月**（`config.yml: tier.rolling_months`）
- 判定は「現在月の直前 3ヶ月」が全て条件を満たすこと（AND条件）
- データが3ヶ月に満たない場合（新規契約直後など）は Passive になる

### パラメータ（`config.yml: kpi.tier`）

```yaml
tier:
  rolling_months:        3   # fan/proactive 判定のローリング期間
  fan_feature_min:       2   # fan: normal以上の機能数の最小値
  proactive_feature_min: 1   # proactive: 同上
  usage_freq_good:       4   # usage_freq good の feature_score 閾値
  usage_freq_normal:     2   # usage_freq normal の同上
```

---

## 4. クロスプロダクト ティア（integration_tier）

施工管理（work）と経営管理（keiei）の **両方のスコア**を使って判定する。`integration_tier` カラムに格納。

### スコア集計

```
work_score   = sum of per-feature scores across all work features   (0〜12)
keiei_score  = sum of per-feature scores across all keiei features  (0〜16)
total_score  = work_score + keiei_score
```

各プロダクトの `xproduct_score_min` 閾値（= 1）を超えているかが判定軸。

### ティア判定ロジック（優先度順）

| 優先度 | ティア | 条件 |
|---|---|---|
| 1 | **Onboarding** | `lifecycle_stage` が `onboarding-*` |
| 2 | **Fan（ファン）** | 直近3ヶ月の**各月で** `work_score >= 1` **かつ** `keiei_score >= 1`（両プロダクト継続利用） |
| 3 | **Proactive（自走）** | 直近3ヶ月の**各月で** `work_score >= 1` **または** `keiei_score >= 1`（どちらか一方を継続利用） |
| 4 | **Passive（放置）** | 上記いずれにも該当しない |

**単一プロダクトとの違い:**
- 単一プロダクト: 各プロダクト内の「機能多様性（何種類の機能を使っているか）」で判定
- クロスプロダクト: Work と Keiei **両方**を活用しているかで判定（AND / OR）

### パラメータ

```yaml
tier:
  xproduct_score_min:    1   # X-Product fan/proactive: 各プロダクトスコアの最小値
```

---

## 5. usage_freq（利用頻度ラベル）

月次・週次の両粒度で算出される利用頻度の3段階ラベル。

### 単一プロダクト

| `usage_freq` | 条件（`feature_score` 合計） |
|---|---|
| `good` | feature_score >= **4** |
| `normal` | feature_score >= **2** |
| `bad` | feature_score < 2 |

### クロスプロダクト

| `usage_freq` | 条件（`total_score` = work_score + keiei_score） |
|---|---|
| `good` | total_score >= **4** |
| `normal` | total_score >= **2** |
| `bad` | total_score < 2 |

---

## 6. ティア × スコアの関係まとめ

```
┌──────────────────────────────────────────────────────────────────┐
│ 単一プロダクト                                                    │
│                                                                  │
│  機能A: good(2) + 機能B: normal(1) + 機能C: bad(0) + ...        │
│         ↓                                                        │
│  feature_score (合計) → usage_freq (good/normal/bad)            │
│  normal_plus_count   → diversity_tier (fan/proactive/passive)   │
│                         ※直近3ヶ月ローリング                    │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│ クロスプロダクト                                                  │
│                                                                  │
│  work_score (施工管理全機能の合計)                               │
│  keiei_score (経営管理全機能の合計)                              │
│         ↓                                                        │
│  total_score = work + keiei → usage_freq                        │
│  work>=1 AND/OR keiei>=1    → integration_tier (fan/proactive)  │
│                                ※直近3ヶ月ローリング             │
└──────────────────────────────────────────────────────────────────┘
```

---

## 7. 設定変更方法

閾値はすべて `config.yml` で管理されており、**コード変更不要**。

```yaml
# config.yml 抜粋
kpi:
  feature_thresholds:        # Work 機能閾値（月次絶対値）
    工程作成: {good_min: 10, normal_min: 5}
    ...
  keiei_feature_thresholds:  # Keiei 機能閾値（月次絶対値）
    案件ステータス更新: {good_min: 2, normal_min: 1}
    ...
  tier:
    rolling_months:        3   # ローリング期間（月）
    fan_feature_min:       2   # 単一プロダクト fan 閾値
    proactive_feature_min: 1   # 単一プロダクト proactive 閾値
    xproduct_score_min:    1   # クロスプロダクト fan/proactive 閾値
    usage_freq_good:       4   # usage_freq good 閾値
    usage_freq_normal:     2   # usage_freq normal 閾値
```
