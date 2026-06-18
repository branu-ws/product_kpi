#!/bin/bash
# Cloud Run Job の環境変数・シークレット・BigQuery データセットをまとめてセットアップする
# 初回だけ実行すればいい

set -e

PROJECT="product-department-496703"
REGION="asia-northeast1"
JOB_NAME="kpi-pipeline-job"
DATASET="kpi"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/kpi-repo/pipeline:latest"
SA="kpi-pipeline@${PROJECT}.iam.gserviceaccount.com"

echo "=== ① BigQuery データセットを作成 (既存なら何もしない) ==="
bq --project_id="${PROJECT}" mk --dataset --location="asia-northeast1" "${PROJECT}:${DATASET}" 2>/dev/null \
  && echo "✅ データセット ${DATASET} を作成しました" \
  || echo "ℹ️  データセット ${DATASET} は既に存在します"

echo ""
echo "=== ② Secret Manager にAPIキーを登録 ==="

read -p "REDASH_API_KEY を入力してください: " REDASH_KEY
echo -n "${REDASH_KEY}" | gcloud secrets create REDASH_API_KEY \
  --data-file=- --project="${PROJECT}" 2>/dev/null \
  || echo -n "${REDASH_KEY}" | gcloud secrets versions add REDASH_API_KEY \
     --data-file=- --project="${PROJECT}"
echo "✅ REDASH_API_KEY を登録しました"

read -p "NOTION_API_KEY を入力してください: " NOTION_KEY
echo -n "${NOTION_KEY}" | gcloud secrets create NOTION_API_KEY \
  --data-file=- --project="${PROJECT}" 2>/dev/null \
  || echo -n "${NOTION_KEY}" | gcloud secrets versions add NOTION_API_KEY \
     --data-file=- --project="${PROJECT}"
echo "✅ NOTION_API_KEY を登録しました"

echo ""
echo "=== ③ サービスアカウントに Secret Manager の読み取り権限を付与 ==="
gcloud projects add-iam-policy-binding "${PROJECT}" \
  --member="serviceAccount:${SA}" \
  --role="roles/secretmanager.secretAccessor" \
  --condition=None > /dev/null
echo "✅ 権限を付与しました"

echo ""
echo "=== ④ Cloud Run Job を作成 / 更新 (環境変数 + シークレットを設定) ==="
gcloud run jobs deploy "${JOB_NAME}" \
  --image="${IMAGE}" \
  --region="${REGION}" \
  --service-account="${SA}" \
  --set-env-vars="USE_BIGQUERY=1,GCP_PROJECT_ID=${PROJECT}" \
  --set-secrets="REDASH_API_KEY=REDASH_API_KEY:latest,NOTION_API_KEY=NOTION_API_KEY:latest" \
  --task-timeout=900 \
  --max-retries=1

echo ""
echo "✅ セットアップ完了！"
echo "手動で今すぐ実行する場合:"
echo "  gcloud run jobs execute ${JOB_NAME} --region=${REGION} --wait"
