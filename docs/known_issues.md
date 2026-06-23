# 既知の運用課題

## 課題1: アクティブ企業数の過大計上（CAS 契約データの混入）

**現象**  
KPI の月次・週次レポートで plus active 企業が **836社**（2026-06時点）と表示されるが、実態は **266社前後**（実運用チーム管理リスト）。

**根本原因**  
CAS の `contracts` テーブルには free trial・未導入・名義登録のみの企業が大量に含まれており、`status = 'active'` かつ `end_date` が未来でも、実際に製品を使っていない会社が 600社以上混入している。  
Salesforce の `CAREECON_Plus__c = true AND CAREECON_Plus_Cancel__c = false` が真のアクティブ Plus 顧客のソース・オブ・トゥルースであり、CAS の契約数とは乖離がある。

**暫定対応**  
- `kpi/customer_lifecycle.py` の `active_ranked` CTE に `AND con.status = 'active'` を追加済み（finished 契約の混入を防ぐ）
- 実運用チームから提供された 266社リスト（`docs/benchmark_custormer.csv`）の突合により、203社の UUID を確定済み

**恒久対応（未実施）**  
Salesforce の `Account.CAREECON_CID__c` をキーに、`CAREECON_Plus__c = true AND CAREECON_Plus_Cancel__c = false` のホワイトリストを取得し、`contracts` または `customer_lifecycle` のフィルタに使う仕組みが必要。

---

## 課題2: Salesforce の CAREECON_CID__c 未設定（130社がKPIから消える）

**現象**  
Salesforce でアクティブ Plus と認識されている企業 270社のうち、**130社は `CAREECON_CID__c`（施工管理用CID）が未設定**。  
CID がないと CAS の `accounts.cid` → DS7 の `companies.cid` への UUID 解決ができず、KPI に一切出てこない。

**影響**  
実態の約半数の顧客が KPI の集計対象外になっている。

**対応依頼先**  
Salesforce 担当者に、受注済み Plus 顧客の `Account.CAREECON_CID__c` 入力を依頼する。  
優先度の高い 130社：`CAREECON_Plus__c = true AND CAREECON_Plus_Cancel__c = false AND CAREECON_CID__c = null`（2026-06-22時点）

---

## 課題3: Salesforce の CAREECON_CID__c が「ID」として機能していない

**現象**  
`CAREECON_CID__c`（施工管理用CID）という名のフィールドが、アクティブ Plus 顧客 270社のうち **130社（約半数）で空欄**。ID という名前なのに識別子として成立していない。

**推定原因**  
運用フローが分断されている可能性：
1. 営業が受注時に Salesforce で `CAREECON_Plus__c = true` を立てる
2. 製品の初期設定完了後に担当者が CID を別途 Salesforce に転記する

この転記ステップが **義務化・自動化されておらず**、130社分が入力漏れのまま放置されている。

**影響**  
- CID がない = パイプラインが UUID を解決できない = KPI に企業が一切出てこない
- 実態として初期設定済みで使っている企業が含まれる可能性があり、その場合 KPI の欠損が深刻

**対応依頼先**  
- **短期:** 130社の CID を手動で Salesforce に入力（CS・実装担当）
- **中長期:** 初期設定完了フロー内で CID を Salesforce に自動登録する仕組みを構築

---

## 課題4: DS7 未登録の Plus 顧客（13社が原理的に追えない）

**現象**  
実運用チームの 266社リストのうち **13社は DS7（careecon_work）の `companies` テーブルに存在しない**。  
コア名称での部分一致検索でもヒットなし。

**推定原因**  
- 契約したが製品（careecon_work）を一度も起動していない
- DS7 とは別の経路・環境で運用されている

**対応**  
このパイプラインからは原理的に観測不可能。Salesforce の CID 整備（課題2）で CID が付与されれば、製品起動時に自動的に追跡可能になる見込み。現時点では許容誤差として管理。

---

## 参考: 調査で確定した数字（2026-06-22 時点）

| 指標 | 数値 |
|------|------|
| 実運用チーム管理リスト（benchmark） | 266社（誤差±5） |
| Salesforce CAREECON_Plus__c = true（Cancel=false） | 270社 |
| &emsp;└ CAREECON_CID__c 設定済み | 140社 |
| &emsp;└ CAREECON_CID__c 未設定 | 130社 |
| benchmark → UUID 確定済み（名前+plus active契約） | 203社 |
| CAS contracts active plus（現状の KPI 母集団） | 836社（fix B後） |
| DS7 未登録（KPI から原理的に見えない） | 13社 |
