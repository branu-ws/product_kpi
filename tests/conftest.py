"""pytest 共通フィクスチャ。"""

import duckdb
import pytest


@pytest.fixture()
def conn():
    c = duckdb.connect()
    yield c
    c.close()
