"""Unit tests for the /tables endpoints.

All database calls are mocked — no live database is required.
Patches target the names as imported in app.api.tables so that
FastAPI dependency injection resolves against the mocked callables.
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.tables import ColumnInfo, TableInfo

client = TestClient(app)

# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

SAMPLE_TABLES = [
    TableInfo(name="policyholders", row_count=30, column_count=8),
    TableInfo(name="policies", row_count=40, column_count=10),
    TableInfo(name="claims", row_count=50, column_count=10),
]

SAMPLE_COLUMNS = [
    ColumnInfo(name="id", data_type="integer", is_nullable=False, column_default="nextval('policyholders_id_seq'::regclass)"),
    ColumnInfo(name="national_id", data_type="character varying", is_nullable=False, column_default=None),
    ColumnInfo(name="full_name", data_type="character varying", is_nullable=False, column_default=None),
    ColumnInfo(name="birth_date", data_type="date", is_nullable=False, column_default=None),
    ColumnInfo(name="gender", data_type="character varying", is_nullable=False, column_default=None),
    ColumnInfo(name="email", data_type="character varying", is_nullable=True, column_default=None),
    ColumnInfo(name="phone", data_type="character varying", is_nullable=True, column_default=None),
    ColumnInfo(name="created_at", data_type="timestamp without time zone", is_nullable=True, column_default="now()"),
]

SAMPLE_ROWS = [
    {"id": 1, "national_id": "A123456789", "full_name": "James Wilson",
     "birth_date": "1978-03-15", "gender": "M", "email": "james.wilson@email.com",
     "phone": "0912-345-001", "created_at": "2020-01-10T09:00:00"},
    {"id": 2, "national_id": "B234567890", "full_name": "Linda Chen",
     "birth_date": "1985-07-22", "gender": "F", "email": "linda.chen@email.com",
     "phone": "0912-345-002", "created_at": "2020-02-14T10:30:00"},
]

# Patch targets: the names as bound in app.api.tables
_PATCH_LIST   = "app.api.tables.list_public_tables"
_PATCH_COLS   = "app.api.tables.get_table_columns"
_PATCH_SAMPLE = "app.api.tables.sample_table"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_list_tables():
    """GET /tables returns a list of TableInfo objects with correct shape."""
    with patch(_PATCH_LIST, return_value=SAMPLE_TABLES):
        response = client.get("/tables")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3

    names = {item["name"] for item in data}
    assert names == {"policyholders", "policies", "claims"}

    # Spot-check shape of first item
    policyholders = next(item for item in data if item["name"] == "policyholders")
    assert policyholders["row_count"] == 30
    assert policyholders["column_count"] == 8


def test_get_table_found():
    """GET /tables/{name} returns 200 with column details when table exists."""
    with (
        patch(_PATCH_LIST, return_value=SAMPLE_TABLES),
        patch(_PATCH_COLS, return_value=SAMPLE_COLUMNS),
    ):
        response = client.get("/tables/policyholders")

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "policyholders"
    assert data["row_count"] == 30
    assert len(data["columns"]) == 8

    # Verify column shape
    first_col = data["columns"][0]
    assert first_col["name"] == "id"
    assert first_col["data_type"] == "integer"
    assert first_col["is_nullable"] is False


def test_get_table_not_found():
    """GET /tables/{name} returns 404 with error code TABLE_NOT_FOUND when table is absent."""
    with patch(_PATCH_LIST, return_value=[]):
        response = client.get("/tables/nonexistent_table")

    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "TABLE_NOT_FOUND"


def test_get_table_sample():
    """GET /tables/{name}/sample returns rows and limit fields."""
    with (
        patch(_PATCH_LIST, return_value=SAMPLE_TABLES),
        patch(_PATCH_SAMPLE, return_value=SAMPLE_ROWS),
    ):
        response = client.get("/tables/policyholders/sample")

    assert response.status_code == 200
    data = response.json()
    assert "rows" in data
    assert "limit" in data
    assert len(data["rows"]) == 2
    assert data["limit"] == 50  # default

    # Spot-check a row value
    assert data["rows"][0]["national_id"] == "A123456789"


def test_get_sample_not_found():
    """GET /tables/{name}/sample returns 404 when the table does not exist."""
    with patch(_PATCH_LIST, return_value=[]):
        response = client.get("/tables/nonexistent_table/sample")

    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "TABLE_NOT_FOUND"
