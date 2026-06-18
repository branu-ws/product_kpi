#!/bin/bash

# 変数の設定（必要に応じて変更してください）
PROJECT="product-department-496703"
REGION="asia-northeast1"
JOB_NAME="kpi-pipeline-weekly-job"
SA="kpi-pipeline@${PROJECT}.iam.gserviceaccount.com"
SCHEDULE="0 2 * * 1"   # 毎週月曜 02:00
TIME_ZONE="Asia/Tokyo"
URI="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT}/jobs/kpi-pipeline-job:run"

echo "🚀 Cloud Scheduler の設定を開始します (存在すれば更新、なければ作成)..."

# まず update を実行。エラー出力(2>)は /dev/null に捨てて画面に出さないようにする
if gcloud scheduler jobs update http "${JOB_NAME}" \
  --location="${REGION}" \
  --schedule="${SCHEDULE}" \
  --time-zone="${TIME_ZONE}" \
  --uri="${URI}" \
  --http-method=POST \
  --oauth-service-account-email="${SA}" 2>/dev/null; then
    
    echo "✅ 既存のジョブ '${JOB_NAME}' を更新 (update) しました！"

else
    echo "⚠️ 既存ジョブが見つかりませんでした。新規作成 (create) します..."
    
    gcloud scheduler jobs create http "${JOB_NAME}" \
      --location="${REGION}" \
      --schedule="${SCHEDULE}" \
      --time-zone="${TIME_ZONE}" \
      --uri="${URI}" \
      --http-method=POST \
      --oauth-service-account-email="${SA}"
      
    echo "✅ 新規ジョブ '${JOB_NAME}' を作成しました！"
fi