"""Tests for runs_store and results API endpoints.

Integration tests (test_runs_store_*) hit the real Supabase DB via the
db_session fixture (transaction-rollback isolation).

Endpoint tests mock GeEngine and all store helpers so no live DB or GE
calls are made.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.rules import RuleRecord
from app.schemas.runs import RunDetail, RunResult, RunSummary
from app.services.runs_store import (
    create_run,
    finalize_run,
    get_run,
    list_runs,
    write_result,
)

client = TestClient(app)

# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2024, 1, 1, 12, 0, 0)

SAMPLE_RULE = RuleRecord(
    id=1,
    table_name="policyholders",
    expectation_type="expect_column_values_to_not_be_null",
    kwargs={"column": "national_id"},
    description="National ID must never be null.",
    source="user",
    created_at=_NOW,
    updated_at=_NOW,
)

SAMPLE_RUN_RESULT = RunResult(
    id=1,
    rule_id=1,
    expectation_type="expect_column_values_to_not_be_null",
    status="pass",
    success=True,
    unexpected_count=0,
    unexpected_sample=None,
    observed_value=None,
    error_message=None,
)

SAMPLE_RUN_DETAIL = RunDetail(
    id=1,
    table_name="policyholders",
    status="success",
    started_at=_NOW,
    completed_at=_NOW,
    error_message=None,
    pass_count=1,
    fail_count=0,
    error_count=0,
    results=[SAMPLE_RUN_RESULT],
)

SAMPLE_RUN_SUMMARY = RunSummary(
    id=1,
    table_name="policyholders",
    status="success",
    started_at=_NOW,
    completed_at=_NOW,
    error_message=None,
    pass_count=1,
    fail_count=0,
    error_count=0,
)

# Patch paths — names as imported inside app.api.results
_P_LIST_RULES = "app.api.results.list_rules"
_P_CREATE_RUN = "app.api.results.create_run"
_P_WRITE_RESULT = "app.api.results.write_result"
_P_FINALIZE_RUN = "app.api.results.finalize_run"
_P_GET_RUN = "app.api.results.get_run"
_P_LIST_RUNS = "app.api.results.list_runs"
_P_GE_ENGINE = "app.api.results.GeEngine"
_P_EXECUTE_RUN = "app.api.results._execute_run"

SAMPLE_RUNNING_DETAIL = RunDetail(
    id=1,
    table_name="policyholders",
    status="running",
    started_at=_NOW,
    completed_at=None,
    error_message=None,
    pass_count=0,
    fail_count=0,
    error_count=0,
    results=[],
)


# ---------------------------------------------------------------------------
# runs_store integration tests (real DB, transaction-rollback isolation)
# ---------------------------------------------------------------------------


def test_runs_store_lifecycle(db_session):
    """Full create → write_result → get_run → list_runs cycle."""
    # CREATE RUN
    run_id = create_run(db_session, table_name="policyholders")
    assert isinstance(run_id, int)

    # WRITE RESULT (pass) — rule_id=None simulates a deleted rule (FK allows NULL)
    result_pass = RunResult(
        id=0,
        rule_id=None,
        expectation_type="expect_column_values_to_not_be_null",
        status="pass",
        success=True,
        unexpected_count=0,
        unexpected_sample=None,
        observed_value=None,
        error_message=None,
    )
    write_result(db_session, run_id=run_id, rule_id=None, result=result_pass)

    # WRITE RESULT (error with error_message)
    result_err = RunResult(
        id=0,
        rule_id=None,
        expectation_type="expect_column_values_to_be_in_set",
        status="error",
        success=False,
        unexpected_count=None,
        unexpected_sample=None,
        observed_value=None,
        error_message="column does not exist",
    )
    write_result(db_session, run_id=run_id, rule_id=None, result=result_err)

    # FINALIZE
    finalize_run(db_session, run_id=run_id, status="success", error_message=None)

    # GET RUN — full detail
    run = get_run(db_session, run_id)
    assert run is not None
    assert run.id == run_id
    assert run.table_name == "policyholders"
    assert run.status == "success"
    assert run.pass_count == 1
    assert run.error_count == 1
    assert run.fail_count == 0
    assert len(run.results) == 2

    # error_message round-trips through raw_result JSONB
    err_result = next(r for r in run.results if r.status == "error")
    assert err_result.error_message == "column does not exist"

    # LIST RUNS — appears in list
    summaries = list_runs(db_session, table_name="policyholders")
    ids = [s.id for s in summaries]
    assert run_id in ids

    # GET RUN — non-existent returns None
    assert get_run(db_session, run_id=999999) is None


def test_runs_store_failed_run(db_session):
    """A failed run shows status='failed' in the list."""
    run_id = create_run(db_session, table_name="policyholders")
    finalize_run(db_session, run_id=run_id, status="failed", error_message="crash")

    run = get_run(db_session, run_id)
    assert run is not None
    assert run.status == "failed"
    assert run.error_message == "crash"
    assert run.results == []


# ---------------------------------------------------------------------------
# Results API endpoint tests (mocked GeEngine + mocked store)
# ---------------------------------------------------------------------------


def test_trigger_run_returns_202():
    """POST /runs immediately returns 202 with status='running' (D#23 async)."""
    with (
        patch(_P_CREATE_RUN, return_value=1),
        patch(_P_GET_RUN, return_value=SAMPLE_RUNNING_DETAIL),
        patch(_P_EXECUTE_RUN),  # prevent background task from running
    ):
        resp = client.post("/runs", json={"table_name": "policyholders"})

    assert resp.status_code == 202
    data = resp.json()
    assert data["id"] == 1
    assert data["status"] == "running"
    assert data["pass_count"] == 0
    assert "results" not in data  # RunSummary serialization omits results


def test_trigger_run_no_rules_returns_202():
    """POST /runs with no rules still creates a run and returns 202."""
    empty_running = RunDetail(
        id=2,
        table_name="policyholders",
        status="running",
        started_at=_NOW,
        completed_at=None,
        error_message=None,
        pass_count=0,
        fail_count=0,
        error_count=0,
        results=[],
    )

    with (
        patch(_P_CREATE_RUN, return_value=2),
        patch(_P_GET_RUN, return_value=empty_running),
        patch(_P_EXECUTE_RUN),
    ):
        resp = client.post("/runs", json={"table_name": "policyholders"})

    assert resp.status_code == 202
    assert resp.json()["status"] == "running"


def test_trigger_run_invalid_rule_ids():
    """POST /runs with rule_ids not belonging to the table returns INVALID_RULE_IDS."""
    with (
        patch(_P_LIST_RULES, return_value=[]),  # 0 matched vs 1 requested
        patch(_P_CREATE_RUN, return_value=1),
        patch(_P_EXECUTE_RUN),
    ):
        resp = client.post("/runs", json={"table_name": "policyholders", "rule_ids": [999]})

    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_RULE_IDS"


def test_fetch_run():
    """GET /runs/{id} returns RunDetail."""
    with patch(_P_GET_RUN, return_value=SAMPLE_RUN_DETAIL):
        resp = client.get("/runs/1")

    assert resp.status_code == 200
    assert resp.json()["id"] == 1
    assert resp.json()["table_name"] == "policyholders"


def test_fetch_run_not_found():
    """GET /runs/{id} returns RUN_NOT_FOUND for missing id."""
    with patch(_P_GET_RUN, return_value=None):
        resp = client.get("/runs/999")

    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "RUN_NOT_FOUND"


def test_fetch_runs_list():
    """GET /runs?table_name=X returns list of RunSummary."""
    with patch(_P_LIST_RUNS, return_value=[SAMPLE_RUN_SUMMARY]):
        resp = client.get("/runs?table_name=policyholders")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == 1
    assert data[0]["pass_count"] == 1


def test_fetch_runs_list_empty():
    """GET /runs returns empty list when no runs exist."""
    with patch(_P_LIST_RUNS, return_value=[]):
        resp = client.get("/runs")

    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# GeEngine SQLite smoke tests (real GE execution, no Postgres required)
# ---------------------------------------------------------------------------
#
# These tests bypass GeEngine.__init__ (which connects to Postgres) by using
# object.__new__ to skip __init__, then manually set .context and .datasource.
# A file-based SQLite DB is used because GE 1.x SQL datasources require a
# real file path, not sqlite:///:memory:.


import os
import sqlite3
import tempfile

import great_expectations as gx

from app.services.ge_engine import GeEngine


def _make_sqlite_engine(path: str) -> GeEngine:
    """Construct a GeEngine pointed at a SQLite file, bypassing Postgres init."""
    ge = object.__new__(GeEngine)
    ge.context = gx.get_context(mode="ephemeral")
    ge.datasource = ge.context.data_sources.add_sqlite(
        name="test_sqlite",
        connection_string=f"sqlite:///{path}",
    )
    return ge


def _setup_sqlite_db() -> str:
    """Create a temp SQLite DB with 3 rows (one NULL name). Returns file path."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE smoke_tbl (id INTEGER, name TEXT)")
    conn.execute("INSERT INTO smoke_tbl VALUES (1, 'Alice')")
    conn.execute("INSERT INTO smoke_tbl VALUES (2, 'Bob')")
    conn.execute("INSERT INTO smoke_tbl VALUES (3, NULL)")
    conn.commit()
    conn.close()
    return path


def _make_rule(expectation_type: str, column: str) -> RuleRecord:
    return RuleRecord(
        id=99,
        table_name="smoke_tbl",
        expectation_type=expectation_type,
        kwargs={"column": column},
        description="smoke test rule",
        source="user",
        created_at=datetime(2024, 1, 1),
        updated_at=datetime(2024, 1, 1),
    )


class TestGeEngineSQLiteSmokeTests:
    """Real GE execution against SQLite — no mocking of GE internals."""

    def setup_method(self):
        self.db_path = _setup_sqlite_db()
        self.ge = _make_sqlite_engine(self.db_path)

    def teardown_method(self):
        os.unlink(self.db_path)

    def test_pass_no_nulls(self):
        """expect_column_values_to_not_be_null passes when all values are non-null."""
        # Only rows 1 and 2 (id column never has NULLs in our dataset)
        rule = _make_rule("expect_column_values_to_not_be_null", "id")
        results = self.ge.run_rules("smoke_tbl", [rule])
        assert len(results) == 1
        assert results[0].status == "pass"
        assert results[0].success is True

    def test_fail_has_nulls(self):
        """expect_column_values_to_not_be_null fails when a NULL is present."""
        rule = _make_rule("expect_column_values_to_not_be_null", "name")
        results = self.ge.run_rules("smoke_tbl", [rule])
        assert len(results) == 1
        assert results[0].status == "fail"
        assert results[0].success is False
        assert results[0].unexpected_count is not None
        assert results[0].unexpected_count >= 1

    def test_error_nonexistent_column(self):
        """expect_column_values_to_not_be_null on a missing column yields status='error'."""
        rule = _make_rule("expect_column_values_to_not_be_null", "nonexistent_col")
        results = self.ge.run_rules("smoke_tbl", [rule])
        assert len(results) == 1
        assert results[0].status == "error"
        assert results[0].success is False
        assert results[0].error_message  # non-empty string
