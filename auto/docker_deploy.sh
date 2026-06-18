#!/bin/bash

# 変数の設定
PROJECT="product-department-496703"
REGION="asia-northeast1"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/kpi-repo/pipeline:latest"
JOB_NAME="kpi-pipeline-job"

echo "🔨 1. 最新のコードでDockerイメージをビルドします..."
docker build -t "${IMAGE}" .

echo "☁️  2. Artifact Registry にイメージをプッシュ（上書き）します..."
docker push "${IMAGE}"

echo "✅ デプロイ完了！次回のジョブ実行から最新のコードが反映されます。"

# （おまけ）もし今すぐ手動でテスト実行したい場合は以下のコマンドを叩いてください、という案内
echo "---------------------------------------------------"
echo "💡 今すぐ手動で動かしてテストしたい場合は以下のコマンドを実行してください："
echo "gcloud run jobs execute ${JOB_NAME} --region=${REGION} --wait"