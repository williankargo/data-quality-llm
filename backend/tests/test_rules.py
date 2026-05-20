"""Tests for rules_store CRUD and (later) rules API endpoints.

test_rules_store_crud is an integration test that hits the real DB.
It relies on the db_session fixture in conftest.py, which rolls back
all changes after each test so Supabase state is left clean.
"""

from app.schemas.rules import GeRule
from app.services.rules_store import (
    create_rule,
    delete_rule,
    get_rule,
    list_rules,
    mark_drafts_already_saved,
    update_rule,
)


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
