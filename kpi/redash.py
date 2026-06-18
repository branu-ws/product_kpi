import os
import time

import httpx
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()

BASE_URL = "https://redash.careecon.jp"
_API_KEY = os.environ["REDASH_API_KEY"]

_POLL_INTERVAL = 5
_POLL_MAX = 240  # 最大 20 分

_JOB_STATUS = {1: "pending", 2: "running", 3: "success", 4: "failure", 5: "cancelled"}


def _headers() -> dict[str, str]:
    return {"Authorization": f"Key {_API_KEY}"}


def get_data_source_id(client: httpx.Client, query_id: int) -> int:
    resp = client.get(f"{BASE_URL}/api/queries/{query_id}", headers=_headers())
    resp.raise_for_status()
    return int(resp.json()["data_source_id"])


def fetch_result(client: httpx.Client, result_id: int) -> list[dict[str, object]]:
    resp = client.get(
        f"{BASE_URL}/api/query_results/{result_id}",
        headers=_headers(),
        timeout=120,
    )
    resp.raise_for_status()
    return list(resp.json()["query_result"]["data"]["rows"])


def poll_job(client: httpx.Client, job_id: str) -> list[dict[str, object]]:
    for i in range(_POLL_MAX):
        resp = client.get(f"{BASE_URL}/api/jobs/{job_id}", headers=_headers())
        resp.raise_for_status()
        job = resp.json()["job"]
        status: int = job["status"]
        tqdm.write(f"  [{_JOB_STATUS.get(status, status)}] {i * _POLL_INTERVAL}s")

        if status == 3:
            return fetch_result(client, int(job["query_result_id"]))
        if status in (4, 5):
            raise RuntimeError(f"Redash job failed: {job.get('error')}")

        time.sleep(_POLL_INTERVAL)

    raise TimeoutError(f"Query did not finish within {_POLL_MAX * _POLL_INTERVAL}s")


def run_saved_query(client: httpx.Client, query_id: int) -> list[dict[str, object]]:
    """保存済みクエリの最新キャッシュ結果を取得する。

    クエリのメタデータから latest_query_data_id を取得し、
    その結果を直接フェッチする。
    """
    meta_resp = client.get(
        f"{BASE_URL}/api/queries/{query_id}",
        headers=_headers(),
        timeout=30,
    )
    meta_resp.raise_for_status()
    meta = meta_resp.json()

    result_id: int | None = meta.get("latest_query_data_id")
    if result_id is None:
        raise RuntimeError(
            f"query {query_id}: no cached result. Run it on Redash first."
        )

    return fetch_result(client, result_id)


def run_adhoc_query(
    client: httpx.Client, data_source_id: int, sql: str
) -> list[dict[str, object]]:
    """SQLをアドホック実行する(遅い)。"""
    resp = client.post(
        f"{BASE_URL}/api/query_results",
        headers=_headers(),
        json={"data_source_id": data_source_id, "query": sql, "max_age": 0},
        timeout=60,
    )
    resp.raise_for_status()
    body = resp.json()

    if "query_result" in body:
        return list(body["query_result"]["data"]["rows"])

    return poll_job(client, body["job"]["id"])
