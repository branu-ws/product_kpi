import httpx
import pandas as pd

from kpi import redash

_DATA_SOURCE_ID = 7  # careecon_work (keiei_plus_production にアクセス可能)

# テストアカウントを除外
_EXCLUDE_COMPANY_IDS = "2, 8, 264, 64, 412"

_SQL = f"""
SELECT
    c.cid AS company_uuid,
    '案件ステータス更新' AS content,
    h.changed_at AS content_date
FROM keiei_plus_production.project_progress_histories h
JOIN keiei_plus_production.projects p ON h.project_id = p.id
JOIN keiei_plus_production.companies c ON p.company_id = c.id
WHERE h.deleted_at = '1970-01-01 00:00:00'
  AND p.deleted_at = '1970-01-01 00:00:00'
  AND c.id NOT IN ({_EXCLUDE_COMPANY_IDS})

UNION ALL

SELECT
    c.cid AS company_uuid,
    '案件ステータス更新' AS content,
    h.changed_at AS content_date
FROM keiei_plus_production.lead_status_histories h
JOIN keiei_plus_production.leads l ON h.lead_id = l.id
JOIN keiei_plus_production.companies c ON l.company_id = c.id
WHERE h.deleted_at = '1970-01-01 00:00:00'
  AND l.deleted_at = '1970-01-01 00:00:00'
  AND c.id NOT IN ({_EXCLUDE_COMPANY_IDS})

UNION ALL

SELECT c.cid AS company_uuid, '見積原価登録' AS content, d.created_at AS content_date
FROM keiei_plus_production.documents d
JOIN keiei_plus_production.companies c ON d.company_id = c.id
WHERE d.transaction_type = 3
  AND d.status = 5
  AND d.deleted_at = '1970-01-01 00:00:00'
  AND c.id NOT IN ({_EXCLUDE_COMPANY_IDS})

UNION ALL

SELECT c.cid AS company_uuid, '見積売上登録' AS content, d.created_at AS content_date
FROM keiei_plus_production.documents d
JOIN keiei_plus_production.companies c ON d.company_id = c.id
WHERE d.transaction_type = 2
  AND d.status = 5
  AND d.deleted_at = '1970-01-01 00:00:00'
  AND c.id NOT IN ({_EXCLUDE_COMPANY_IDS})

UNION ALL

SELECT c.cid AS company_uuid, '実績原価登録' AS content, d.created_at AS content_date
FROM keiei_plus_production.documents d
JOIN keiei_plus_production.companies c ON d.company_id = c.id
WHERE d.transaction_type = 1
  AND d.status = 5
  AND d.deleted_at = '1970-01-01 00:00:00'
  AND c.id NOT IN ({_EXCLUDE_COMPANY_IDS})

UNION ALL

SELECT c.cid AS company_uuid, '実績売上登録' AS content, d.created_at AS content_date
FROM keiei_plus_production.documents d
JOIN keiei_plus_production.companies c ON d.company_id = c.id
WHERE d.transaction_type = 4
  AND d.status = 5
  AND d.deleted_at = '1970-01-01 00:00:00'
  AND c.id NOT IN ({_EXCLUDE_COMPANY_IDS})

UNION ALL

SELECT c.cid AS company_uuid, '請求書発行' AS content, ip.confirmed_at AS content_date
FROM keiei_plus_production.invoice_pdfs ip
JOIN keiei_plus_production.companies c ON ip.company_id = c.id
WHERE ip.status = 1
  AND ip.confirmed_at IS NOT NULL
  AND ip.deleted_at = '1970-01-01 00:00:00'
  AND c.id NOT IN ({_EXCLUDE_COMPANY_IDS})

UNION ALL

SELECT c.cid AS company_uuid, '原価ページPV' AS content, pvl.created_at AS content_date
FROM keiei_plus_production.document_pv_logs pvl
JOIN keiei_plus_production.companies c ON pvl.company_id = c.id
WHERE pvl.page_name = 'estimated_cost'
  AND c.id NOT IN ({_EXCLUDE_COMPANY_IDS})

UNION ALL

SELECT c.cid AS company_uuid, 'OCR処理' AS content, od.ocr_completed_at AS content_date
FROM keiei_plus_production.ocr_documents od
JOIN keiei_plus_production.companies c ON od.company_id = c.id
WHERE od.ocr_status = 3
  AND od.ocr_completed_at IS NOT NULL
  AND od.deleted_at = '1970-01-01 00:00:00'
  AND c.id NOT IN ({_EXCLUDE_COMPANY_IDS})
"""


def _to_df(rows: list[dict[str, object]]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["content_date"] = pd.to_datetime(df["content_date"], errors="coerce")
    return df


def fetch(client: httpx.Client) -> pd.DataFrame:
    rows = redash.run_adhoc_query(client, _DATA_SOURCE_ID, _SQL)
    return _to_df(rows)
