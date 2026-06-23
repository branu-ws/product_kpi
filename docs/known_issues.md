# 既知の運用課題

## 現状の顧客母集団（2026-06 時点）

| 指標 | 数値 | 備考 |
|------|------|------|
| SF Plus アクティブ（真のソース・オブ・トゥルース） | 270社 | `CAREECON_Plus__c=true AND CAREECON_Plus_Cancel__c=false` |
| sf_customers ホワイトリスト（kpi-update ごとに自動更新） | 268社 | CID補填後。EXCEL管理 266社に近傍 |
| KPI で観測可能（feature_health 2026-06） | 197社 | 下記の理由で 71社が欠落 |
| **欠落内訳① 経営管理のみで施工管理未使用** | 35社 | keiei_feature_health には存在する |
| **欠落内訳② UUID 不一致（下記課題3・4）** | 26社 | 誤マッチまたは CAS 契約未反映 |

---

## 課題1: CAS 契約データのノイズ（解決済み）

**現象**  
CAS の `contracts` には free trial・未導入・名義登録のみの企業が混入しており、
`status = 'active'` だけでフィルタすると **953社**（実態は約 266社）になる。

**対応（実施済み）**  
Salesforce `CAREECON_Plus__c = true AND CAREECON_Plus_Cancel__c = false` を
ソース・オブ・トゥルースとした sf_customers ホワイトリストを導入。
`customer_lifecycle.py` が sf_customers に INNER JOIN することで母集団を正規化済み。

---

## 課題2: 経営管理のみの Plus 顧客が施工管理 KPI に出てこない（構造的制約）

**現象**  
sf_customers 268社のうち **35社は DS7（careecon_work）に未登録**。
これらは施工管理を使わず経営管理のみを利用している顧客。
`customer_lifecycle` が `work_user_history` ベースで構築されているため、観測できない。

**影響**  
- 施工管理 KPI（feature_health / company_loyalty）からは原理的に見えない
- 経営管理 KPI（keiei_feature_health）には出てくる
- クロスプロダクト KPI でも欠落（work_user_history がないため）

**今後の対応**  
`customer_lifecycle` の `all_months` を `work_user_history UNION keiei_user_history`
に変更することで、経営管理のみの顧客も含めた統合ライフサイクルが構築できる（対応予定）。

---

## 課題3: 名前マッチングによる UUID 誤マッチ（18社）

**現象**  
SF の `CAREECON_CID__c` が未設定の会社を DS1 の社名+住所で UUID 補填する際、
DS7 にのみ存在する（CAS accounts に存在しない）別会社の UUID を誤って取得してしまう。

**根本原因**  
DS1（careecon_db）の `companies` テーブルには CAS と紐付かない会社も含まれている。
同名・同都道府県の会社が複数あった場合 take-first で選択するが、
選んだ UUID が CAS に存在しなければ契約情報が紐付かず customer_lifecycle に出てこない。

**対応（実施済み）**  
`sf_customers.py` の DS1 参照を「CAS accounts に存在する UUID のみ」に絞り込むよう修正。
これで DS7 専用会社への誤マッチを防止。

**残存リスク**  
CAS accounts に存在するが active plus 契約がない UUID を take-first で選んでしまう可能性は残る。
根本解決は SF チームに `CAREECON_CID__c` を正しく入力してもらうこと。

---

## 課題4: SF と CAS の契約情報乖離（8社）

**現象**  
UUID は正しく CAS accounts に存在するが、CAS の `contracts` に
active な plus 契約レコードが入っていない会社が **8社**ある。
SF は Plus アクティブと認識しているが CAS 側が追いついていない。

**推定原因**  
- 営業が SF で `CAREECON_Plus__c = true` を立てた後、CAS の contracts が更新されていない
- 契約書の締結タイミングと CAS への反映タイミングのズレ

**影響**  
これら 8社は customer_lifecycle に出てこず、KPI で観測されない。

**対応依頼先**  
CS・実装担当に CAS 契約データの入力・修正を依頼。
8社のリストは sf_customers にあるが contracts に存在しない UUID で確認可能。

---

## 課題5: SF の CAREECON_CID__c 未設定（約 130社）

**現象**  
Salesforce Plus アクティブ 270社のうち **約 130社は `CAREECON_CID__c` が空欄**。
CID がないと社名+住所マッチングで補填を試みるが、マッチング精度には限界がある。

**対応（実施済み）**  
社名 + 都道府県 + 市区前方一致の3段階マッチングで約 130社のうち大半を補填済み。
CAS accounts に存在する UUID のみを候補にすることで誤マッチも低減。

**対応依頼先（推奨）**  
SF 担当者に受注済み Plus 顧客の `CAREECON_CID__c` 入力を依頼。
自動補填の誤りがゼロにならないため、手動入力が最も確実。
