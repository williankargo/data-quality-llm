"""Tests for rules_store CRUD and rules API endpoints.

test_rules_store_crud is an integration test that hits the real DB.
All endpoint tests mock the Anthropic client and DB store functions so
no live AI or DB calls are made.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import anthropic
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.rules import GeRule, RuleDraft, RuleRecord
from app.services.rules_store import (
    create_rule,
    delete_rule,
    get_rule,
    list_rules,
    mark_drafts_already_saved,
    update_rule,
)

client = TestClient(app)

# ---------------------------------------------------------------------------
# Shared fixtures / helpers for endpoint tests
# ---------------------------------------------------------------------------

_NOW = datetime(2024, 1, 1, 12, 0, 0)

SAMPLE_RULE_RECORD = RuleRecord(
    id=1,
    table_name="policyholders",
    expectation_type="expect_column_values_to_not_be_null",
    kwargs={"column": "national_id"},
    description="National ID must never be null.",
    source="user",
    created_at=_NOW,
    updated_at=_NOW,
)

SAMPLE_GE_RULE = GeRule(
    expectation_type="expect_column_values_to_not_be_null",
    kwargs={"column": "national_id"},
    description="National ID must never be null.",
)

SAMPLE_DRAFT = RuleDraft(
    expectation_type="expect_column_values_to_not_be_null",
    kwargs={"column": "national_id"},
    description="National ID must never be null.",
    already_saved=False,
)

# Patch paths — names as imported inside app.api.rules
_P_LIST_TABLES = "app.api.rules.list_public_tables"
_P_GET_COLS = "app.api.rules.get_table_columns"
_P_SAMPLE = "app.api.rules.sample_table"
_P_MARK_DRAFTS = "app.api.rules.mark_drafts_already_saved"
_P_LIST_RULES = "app.api.rules.list_rules"
_P_GET_RULE = "app.api.rules.get_rule"
_P_CREATE_RULE = "app.api.rules.create_rule"
_P_UPDATE_RULE = "app.api.rules.update_rule"
_P_DELETE_RULE = "app.api.rules.delete_rule"

from app.schemas.tables import ColumnInfo, TableInfo  # noqa: E402

SAMPLE_TABLES = [TableInfo(name="policyholders", row_count=30, column_count=8)]
SAMPLE_COLUMNS = [
    ColumnInfo(name="national_id", data_type="character varying", is_nullable=False, column_default=None),
]


# ---------------------------------------------------------------------------
# Rules store integration test (real DB, transaction-rollback isolation)
# ---------------------------------------------------------------------------


def test_rules_store_crud(db_session):
    rule_data = GeRule(
        expectation_type="expect_column_values_to_not_be_null",
        kwargs={"column": "national_id"},
        description="National ID must never be null.",
    )

    # CREATE
    created = create_rule(db_session, table_name="policyholders", source="user", rule=rule_data)
    assert created.id is not None
    assert created.table_name == "policyholders"
    assert created.expectation_type == "expect_column_values_to_not_be_null"
    assert created.kwargs == {"column": "national_id"}
    assert created.source == "user"

    # READ (single)
    fetched = get_rule(db_session, created.id)
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.description == "National ID must never be null."

    # LIST (filtered by table)
    rules = list_rules(db_session, table_name="policyholders")
    ids = [r.id for r in rules]
    assert created.id in ids

    # UPDATE
    updated_data = GeRule(
        expectation_type="expect_column_values_to_not_be_null",
        kwargs={"column": "national_id"},
        description="Updated description.",
    )
    updated = update_rule(db_session, created.id, updated_data)
    assert updated.description == "Updated description."

    # MARK DRAFTS — same rule should be already_saved=True
    drafts = mark_drafts_already_saved(
        db_session,
        table_name="policyholders",
        drafts=[rule_data],
    )
    assert len(drafts) == 1
    assert drafts[0].already_saved is True

    # MARK DRAFTS — different kwargs should be already_saved=False
    new_draft = GeRule(
        expectation_type="expect_column_values_to_not_be_null",
        kwargs={"column": "email"},
        description="Email must never be null.",
    )
    drafts2 = mark_drafts_already_saved(
        db_session,
        table_name="policyholders",
        drafts=[new_draft],
    )
    assert drafts2[0].already_saved is False

    # DELETE
    deleted = delete_rule(db_session, created.id)
    assert deleted is True

    # Confirm gone
    assert get_rule(db_session, created.id) is None

    # DELETE non-existent returns False
    assert delete_rule(db_session, created.id) is False


# ---------------------------------------------------------------------------
# Rules API endpoint tests (mocked AI + mocked DB store)
# ---------------------------------------------------------------------------


def test_suggest_returns_drafts():
    """POST /rules/suggest returns drafts list with already_saved flag."""
    with (
        patch(_P_LIST_TABLES, return_value=SAMPLE_TABLES),
        patch(_P_GET_COLS, return_value=SAMPLE_COLUMNS),
        patch(_P_SAMPLE, return_value=[]),
        patch("app.api.rules.ai") as mock_ai,
        patch(_P_MARK_DRAFTS, return_value=[SAMPLE_DRAFT]),
    ):
        mock_ai.suggest_rules.return_value = [SAMPLE_GE_RULE]
        resp = client.post("/rules/suggest", json={"table_name": "policyholders"})

    assert resp.status_code == 200
    data = resp.json()
    assert "drafts" in data
    assert len(data["drafts"]) == 1
    assert data["drafts"][0]["already_saved"] is False
    assert data["drafts"][0]["expectation_type"] == "expect_column_values_to_not_be_null"


def test_suggest_llm_timeout():
    """POST /rules/suggest returns LLM_TIMEOUT error envelope on timeout."""
    with (
        patch(_P_LIST_TABLES, return_value=SAMPLE_TABLES),
        patch(_P_GET_COLS, return_value=SAMPLE_COLUMNS),
        patch(_P_SAMPLE, return_value=[]),
        patch("app.api.rules.ai") as mock_ai,
    ):
        mock_ai.suggest_rules.side_effect = anthropic.APITimeoutError(request=MagicMock())
        resp = client.post("/rules/suggest", json={"table_name": "policyholders"})

    assert resp.status_code == 504
    assert resp.json()["error"]["code"] == "LLM_TIMEOUT"


def test_suggest_table_not_found():
    """POST /rules/suggest returns TABLE_NOT_FOUND when table does not exist."""
    with patch(_P_LIST_TABLES, return_value=[]):
        resp = client.post("/rules/suggest", json={"table_name": "nonexistent"})

    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "TABLE_NOT_FOUND"


def test_from_nl_returns_rule():
    """POST /rules/from-nl returns a rule object when description is clear."""
    from app.schemas.rules import NlRuleSuccess

    expected = NlRuleSuccess(rule=SAMPLE_GE_RULE)
    with (
        patch(_P_LIST_TABLES, return_value=SAMPLE_TABLES),
        patch(_P_GET_COLS, return_value=SAMPLE_COLUMNS),
        patch("app.api.rules.ai") as mock_ai,
    ):
        mock_ai.rule_from_nl.return_value = expected
        resp = client.post(
            "/rules/from-nl",
            json={"table_name": "policyholders", "description": "national_id must not be null"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "rule"
    assert data["rule"]["expectation_type"] == "expect_column_values_to_not_be_null"


def test_from_nl_returns_clarification():
    """POST /rules/from-nl returns clarification when description is too vague."""
    from app.schemas.rules import NlRuleClarification

    expected = NlRuleClarification(question="Which column should be checked?")
    with (
        patch(_P_LIST_TABLES, return_value=SAMPLE_TABLES),
        patch(_P_GET_COLS, return_value=SAMPLE_COLUMNS),
        patch("app.api.rules.ai") as mock_ai,
    ):
        mock_ai.rule_from_nl.return_value = expected
        resp = client.post(
            "/rules/from-nl",
            json={"table_name": "policyholders", "description": "data must be good"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "clarification"
    assert "question" in data


def test_get_rules():
    """GET /rules?table_name=X returns list of rules."""
    with patch(_P_LIST_RULES, return_value=[SAMPLE_RULE_RECORD]):
        resp = client.get("/rules?table_name=policyholders")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == 1
    assert data[0]["source"] == "user"


def test_create_rule():
    """POST /rules returns the created rule with 201."""
    with patch(_P_CREATE_RULE, return_value=SAMPLE_RULE_RECORD):
        resp = client.post(
            "/rules",
            json={
                "table_name": "policyholders",
                "expectation_type": "expect_column_values_to_not_be_null",
                "kwargs": {"column": "national_id"},
                "description": "National ID must never be null.",
                "source": "user",
            },
        )

    assert resp.status_code == 201
    assert resp.json()["id"] == 1


def test_update_rule():
    """PUT /rules/{id} returns the updated rule."""
    with (
        patch(_P_GET_RULE, return_value=SAMPLE_RULE_RECORD),
        patch(_P_UPDATE_RULE, return_value=SAMPLE_RULE_RECORD),
    ):
        resp = client.put(
            "/rules/1",
            json={
                "expectation_type": "expect_column_values_to_not_be_null",
                "kwargs": {"column": "national_id"},
                "description": "Updated.",
            },
        )

    assert resp.status_code == 200
    assert resp.json()["id"] == 1


def test_update_rule_not_found():
    """PUT /rules/{id} returns RULE_NOT_FOUND when rule does not exist."""
    with patch(_P_GET_RULE, return_value=None):
        resp = client.put(
            "/rules/999",
            json={
                "expectation_type": "expect_column_values_to_not_be_null",
                "kwargs": {"column": "national_id"},
                "description": "x",
            },
        )

    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "RULE_NOT_FOUND"


def test_delete_rule():
    """DELETE /rules/{id} returns {ok: true} on success."""
    with patch(_P_DELETE_RULE, return_value=True):
        resp = client.delete("/rules/1")

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_delete_rule_not_found():
    """DELETE /rules/{id} returns RULE_NOT_FOUND when rule does not exist."""
    with patch(_P_DELETE_RULE, return_value=False):
        resp = client.delete("/rules/999")

    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "RULE_NOT_FOUND"
