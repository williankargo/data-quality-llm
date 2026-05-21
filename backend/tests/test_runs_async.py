"""Tests for async run execution behavior (D#23) and per-rule filtering (D#28).

Endpoint tests use TestClient with mocks to isolate the HTTP contract.
Integration tests (test_*_integration) hit the real DB via db_session and
verify the full background-task lifecycle.
"""

from datetime import datetime
from unittest.mock import MagicMock, call, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.rules import RuleRecord
from app.schemas.runs import RunDetail, RunResult, RunSummary

client = TestClient(app)

_NOW = datetime(2024, 1, 1, 12, 0, 0)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

RULE_1 = RuleRecord(
    id=1,
    table_name="policyholders",
    expectation_type="expect_column_values_to_not_be_null",
    kwargs={"column": "national_id"},
    description="National ID must not be null.",
    source="user",
    created_at=_NOW,
    updated_at=_NOW,
)

RULE_2 = RuleRecord(
    id=2,
    table_name="policyholders",
    expectation_type="expect_column_values_to_be_between",
    kwargs={"column": "premium", "min_value": 0},
    description="Premium must be non-negative.",
    source="ai_nl",
    created_at=_NOW,
    updated_at=_NOW,
)

RUNNING_DETAIL = RunDetail(
    id=10,
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

SUCCESS_DETAIL = RunDetail(
    id=10,
    table_name="policyholders",
    status="success",
    started_at=_NOW,
    completed_at=_NOW,
    error_message=None,
    pass_count=2,
    fail_count=0,
    error_count=0,
    results=[
        RunResult(
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
    ],
)

_P_LIST_RULES = "app.api.results.list_rules"
_P_CREATE_RUN = "app.api.results.create_run"
_P_GET_RUN = "app.api.results.get_run"
_P_LIST_RUNS = "app.api.results.list_runs"
_P_EXECUTE_RUN = "app.api.results._execute_run"

# ---------------------------------------------------------------------------
# 202 immediate response
# ---------------------------------------------------------------------------


def test_post_runs_returns_202_with_running_status():
    """POST /runs immediately returns 202 and status='running', not the final result."""
    with (
        patch(_P_CREATE_RUN, return_value=10),
        patch(_P_GET_RUN, return_value=RUNNING_DETAIL),
        patch(_P_EXECUTE_RUN),
    ):
        resp = client.post("/runs", json={"table_name": "policyholders"})

    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "running"
    assert data["id"] == 10
    assert data["pass_count"] == 0
    assert data["fail_count"] == 0
    assert "results" not in data  # RunSummary response_model omits results field


def test_post_runs_schedules_background_task():
    """POST /runs calls _execute_run as a BackgroundTask with the correct arguments."""
    with (
        patch(_P_CREATE_RUN, return_value=10),
        patch(_P_GET_RUN, return_value=RUNNING_DETAIL),
        patch(_P_EXECUTE_RUN) as mock_execute,
    ):
        client.post("/runs", json={"table_name": "policyholders"})

    mock_execute.assert_called_once_with(10, "policyholders", None)


def test_post_runs_with_rule_ids_passes_ids_to_background_task():
    """POST /runs with rule_ids passes them to the background task."""
    with (
        patch(_P_LIST_RULES, return_value=[RULE_1, RULE_2]),
        patch(_P_CREATE_RUN, return_value=10),
        patch(_P_GET_RUN, return_value=RUNNING_DETAIL),
        patch(_P_EXECUTE_RUN) as mock_execute,
    ):
        client.post("/runs", json={"table_name": "policyholders", "rule_ids": [1, 2]})

    mock_execute.assert_called_once_with(10, "policyholders", [1, 2])


# ---------------------------------------------------------------------------
# rule_ids validation (D#28)
# ---------------------------------------------------------------------------


def test_invalid_rule_ids_returns_400():
    """POST /runs with rule_ids that don't belong to the table returns INVALID_RULE_IDS."""
    with (
        patch(_P_LIST_RULES, return_value=[]),  # 0 matched, 1 requested
        patch(_P_EXECUTE_RUN),
    ):
        resp = client.post("/runs", json={"table_name": "policyholders", "rule_ids": [999]})

    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_RULE_IDS"


def test_partial_rule_ids_mismatch_returns_400():
    """POST /runs where only some rule_ids belong to the table returns INVALID_RULE_IDS."""
    with (
        # Only 1 rule matched; 2 were requested
        patch(_P_LIST_RULES, return_value=[RULE_1]),
        patch(_P_EXECUTE_RUN),
    ):
        resp = client.post("/runs", json={"table_name": "policyholders", "rule_ids": [1, 999]})

    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_RULE_IDS"


def test_valid_rule_ids_returns_202():
    """POST /runs with all rule_ids belonging to the table returns 202."""
    with (
        patch(_P_LIST_RULES, return_value=[RULE_1, RULE_2]),
        patch(_P_CREATE_RUN, return_value=10),
        patch(_P_GET_RUN, return_value=RUNNING_DETAIL),
        patch(_P_EXECUTE_RUN),
    ):
        resp = client.post("/runs", json={"table_name": "policyholders", "rule_ids": [1, 2]})

    assert resp.status_code == 202


def test_no_rule_ids_runs_all():
    """POST /runs without rule_ids runs all rules (no filter validation called)."""
    with (
        patch(_P_CREATE_RUN, return_value=10),
        patch(_P_GET_RUN, return_value=RUNNING_DETAIL),
        patch(_P_EXECUTE_RUN) as mock_execute,
    ):
        resp = client.post("/runs", json={"table_name": "policyholders"})

    assert resp.status_code == 202
    # rule_ids=None means run all
    mock_execute.assert_called_once_with(10, "policyholders", None)


# ---------------------------------------------------------------------------
# Polling: GET /runs/{id} reflects real-time status
# ---------------------------------------------------------------------------


def test_get_run_returns_running_status():
    """GET /runs/{id} returns status='running' while background task is in progress."""
    with patch(_P_GET_RUN, return_value=RUNNING_DETAIL):
        resp = client.get("/runs/10")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running"
    assert data["results"] == []


def test_get_run_returns_success_after_completion():
    """GET /runs/{id} returns status='success' with results after background completes."""
    with patch(_P_GET_RUN, return_value=SUCCESS_DETAIL):
        resp = client.get("/runs/10")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["pass_count"] == 2
    assert len(data["results"]) == 1


# ---------------------------------------------------------------------------
# Background task integration: uses db_session fixture (real DB)
# ---------------------------------------------------------------------------


def test_execute_run_integration(db_session):
    """_execute_run sets run status to success after completing GE checks.

    This test does NOT use BackgroundTasks — it calls _execute_run directly
    to verify the store-level lifecycle.  GeEngine is mocked to avoid
    a live Postgres GE execution.
    """
    from app.services.runs_store import create_run, get_run
    from app.api.results import _execute_run

    run_id = create_run(db_session, table_name="policyholders")

    # Verify initial status
    run = get_run(db_session, run_id)
    assert run is not None
    assert run.status == "running"

    # Mock GeEngine so no real GE execution happens
    mock_result = RunResult(
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
    mock_engine = MagicMock()
    mock_engine.run_rules.return_value = [mock_result]

    with (
        patch("app.api.results.GeEngine", return_value=mock_engine),
        patch("app.api.results.list_rules", return_value=[]),
        # _execute_run opens its own session via get_session; redirect to db_session
        patch("app.api.results.get_session") as mock_get_session,
    ):
        from contextlib import contextmanager

        @contextmanager
        def _fake_session():
            yield db_session

        mock_get_session.return_value = _fake_session()
        _execute_run(run_id, "policyholders", None)

    run_after = get_run(db_session, run_id)
    assert run_after is not None
    assert run_after.status == "success"


# ---------------------------------------------------------------------------
# finalize_run atomic guard (D#23 Tradeoff)
# ---------------------------------------------------------------------------


def test_finalize_run_atomic_guard(db_session):
    """finalize_run is a no-op when status is not 'running' — prevents double-finalization."""
    from app.services.runs_store import create_run, finalize_run, get_run

    run_id = create_run(db_session, table_name="policyholders")
    finalize_run(db_session, run_id, "success", None)

    # Simulate a race condition: second finalize should be blocked by the WHERE guard.
    finalize_run(db_session, run_id, "failed", "should not overwrite")

    run = get_run(db_session, run_id)
    assert run is not None
    assert run.status == "success"    # first write wins
    assert run.error_message is None  # second error_message not applied


# ---------------------------------------------------------------------------
# list_rules rule_ids filter — store layer (D#28)
# ---------------------------------------------------------------------------


def test_list_rules_empty_rule_ids_short_circuits():
    """list_rules(rule_ids=[]) returns [] without executing a query."""
    from unittest.mock import MagicMock
    from app.services.rules_store import list_rules

    session = MagicMock()
    result = list_rules(session, table_name="policyholders", rule_ids=[])
    assert result == []
    session.execute.assert_not_called()


def test_list_rules_filter_by_rule_ids(db_session):
    """list_rules returns only matching rows when rule_ids is provided."""
    from app.services.rules_store import create_rule, list_rules
    from app.schemas.rules import GeRule

    rule = create_rule(
        db_session,
        "policyholders",
        "user",
        GeRule(
            expectation_type="expect_column_values_to_not_be_null",
            kwargs={"column": "national_id"},
            description="Integration test rule",
        ),
    )

    # Only the inserted rule should be returned.
    filtered = list_rules(db_session, table_name="policyholders", rule_ids=[rule.id])
    assert len(filtered) == 1
    assert filtered[0].id == rule.id

    # A non-existent ID should return nothing.
    not_found = list_rules(db_session, table_name="policyholders", rule_ids=[rule.id + 999999])
    assert not_found == []
