"""Plotly グラフの生成と GCS へのアップロード。

config.yml の notion.charts に定義された各スクリプトを実行し、
生成された HTML を GCS バケットにアップロードする。
"""

import logging
import subprocess
import sys
from pathlib import Path
from typing import Any

from kpi.config import ChartEntry, GcpSettings

log = logging.getLogger(__name__)

_ROOT = Path(__file__).parent.parent


def generate_and_upload(charts: list[ChartEntry], gcp: GcpSettings) -> None:
    """各グラフスクリプトを実行して GCS にアップロードする。"""
    if not charts:
        return
    if not gcp.charts_bucket:
        log.warning("gcp.charts_bucket が未設定のためグラフ生成をスキップ")
        return

    from google.cloud import storage

    client: Any = storage.Client(project=gcp.project_id)
    bucket: Any = client.bucket(gcp.charts_bucket)

    for chart in charts:
        script = _ROOT / chart.script
        html = _ROOT / chart.html

        log.info("[chart:%s] スクリプト実行中...", chart.name)
        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            cwd=str(_ROOT),
        )
        if result.returncode != 0:
            log.warning("[chart:%s] スクリプト失敗:\n%s", chart.name, result.stderr)
            continue

        if not html.exists():
            log.warning("[chart:%s] HTML が生成されていません: %s", chart.name, html)
            continue

        log.info("[chart:%s] GCS アップロード中...", chart.name)
        blob: Any = bucket.blob(html.name)
        blob.cache_control = "no-cache, no-store, must-revalidate"
        blob.upload_from_filename(str(html), content_type="text/html")
        log.info(
            "[chart:%s] 完了: gs://%s/%s", chart.name, gcp.charts_bucket, html.name
        )

    _cleanup_orphaned(bucket, charts, gcp.charts_bucket)


def _cleanup_orphaned(
    bucket: Any,  # noqa: ANN401
    charts: list[ChartEntry],
    bucket_name: str,
) -> None:
    """config.yml 未登録の HTML を GCS から削除する。"""
    registered = {Path(c.html).name for c in charts}
    for blob in bucket.list_blobs():
        if blob.name.endswith(".html") and blob.name not in registered:
            blob.delete()
            log.info("GCS 削除 (未登録): gs://%s/%s", bucket_name, blob.name)
