"""Tests for multi-turn NL chat (D#25).

Covers:
- _build_anthropic_messages: single-turn, two-turn, clarification-then-refine
- POST /rules/from-nl with multi-turn messages body
- 10-message (5-turn) cap enforced by Pydantic
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.explain import ChatMessage
from app.schemas.rules import GeRule, NlRuleRequest
from app.services.ai_generator import _build_anthropic_messages

client = TestClient(app)

# ---------------------------------------------------------------------------
# _build_anthropic_messages unit tests
# ---------------------------------------------------------------------------


def test_single_user_turn():
    """One user message → single Anthropic user message."""
    msgs = [ChatMessage(role="user", content="Premium cannot be negative.")]
    result = _build_anthropic_messages(msgs)
    assert result == [{"role": "user", "content": "Premium cannot be negative."}]


def test_user_assistant_user_turn():
    """user + assistant(rule) + user → proper tool_use + tool_result pairs."""
    rule_payload = json.dumps({
        "type": "rule",
        "rule": {
            "expectation_type": "expect_column_values_to_be_between",
            "kwargs": {"column": "premium", "min_value": 0},
            "description": "Premium must be non-negative.",
        },
    })
    msgs = [
        ChatMessage(role="user", content="Premium cannot be negative."),
        ChatMessage(role="assistant", content=rule_payload),
        ChatMessage(role="user", content="Also no zero."),
    ]
    result = _build_anthropic_messages(msgs)

    assert len(result) == 3
    # First user message is plain text
    assert result[0] == {"role": "user", "content": "Premium cannot be negative."}
    # Assistant carries tool_use block
    assert result[1]["role"] == "assistant"
    assert len(result[1]["content"]) == 1
    tool_block = result[1]["content"][0]
    assert tool_block["type"] == "tool_use"
    assert tool_block["name"] == "propose_rule"
    assert tool_block["input"]["expectation_type"] == "expect_column_values_to_be_between"
    # Refinement user message carries tool_result + text
    assert result[2]["role"] == "user"
    assert len(result[2]["content"]) == 2
    assert result[2]["content"][0]["type"] == "tool_result"
    assert result[2]["content"][0]["tool_use_id"] == tool_block["id"]
    assert result[2]["content"][1] == {"type": "text", "text": "Also no zero."}


def test_clarification_assistant_turn():
    """assistant(clarification) serialises as request_clarification tool_use."""
    clarification_payload = json.dumps({
        "type": "clarification",
        "question": "Which column represents the premium amount?",
    })
    msgs = [
        ChatMessage(role="user", content="Check premium."),
        ChatMessage(role="assistant", content=clarification_payload),
        ChatMessage(role="user", content="The column is named 'annual_premium'."),
    ]
    result = _build_anthropic_messages(msgs)
    tool_block = result[1]["content"][0]
    assert tool_block["name"] == "request_clarification"
    assert tool_block["input"]["question"] == "Which column represents the premium amount?"


def test_malformed_assistant_content_fallback():
    """Non-JSON assistant content falls back to plain text — does not crash."""
    msgs = [
        ChatMessage(role="user", content="Hello."),
        ChatMessage(role="assistant", content="not json"),
        ChatMessage(role="user", content="OK."),
    ]
    result = _build_anthropic_messages(msgs)
    # Fallback: assistant is plain text; next user message is its own entry
    assert any(m["role"] == "assistant" and isinstance(m["content"], str) for m in result)


# ---------------------------------------------------------------------------
# NlRuleRequest Pydantic validation — cap boundary
# ---------------------------------------------------------------------------


def test_nl_rule_request_accepts_max_messages():
    """10 messages (5 user + 5 assistant alternating) is accepted."""
    messages = [
        ChatMessage(role="user" if i % 2 == 0 else "assistant", content=f"msg {i}")
        for i in range(10)
    ]
    req = NlRuleRequest(table_name="policyholders", messages=messages)
    assert len(req.messages) == 10


def test_nl_rule_request_rejects_too_many_messages():
    """11 messages exceeds max_length=10 and raises ValidationError."""
    from pydantic import ValidationError

    messages = [
        ChatMessage(role="user" if i % 2 == 0 else "assistant", content=f"msg {i}")
        for i in range(11)
    ]
    with pytest.raises(ValidationError):
        NlRuleRequest(table_name="policyholders", messages=messages)


def test_nl_rule_request_rejects_empty_messages():
    """Empty messages list raises ValidationError (min_length=1)."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        NlRuleRequest(table_name="policyholders", messages=[])


# ---------------------------------------------------------------------------
# POST /rules/from-nl endpoint — multi-turn body shape
# ---------------------------------------------------------------------------

_MOCK_RULE = GeRule(
    expectation_type="expect_column_values_to_be_between",
    kwargs={"column": "premium", "min_value": 1},
    description="Premium must be positive.",
)

_P_TABLES = "app.api.rules.list_public_tables"
_P_COLUMNS = "app.api.rules.get_table_columns"
_P_AI = "app.api.rules.ai"


def _mock_table(name="policyholders"):
    t = MagicMock()
    t.name = name
    return t


def test_from_nl_single_turn_success():
    """Single user message → 200 with rule."""
    from app.schemas.rules import NlRuleSuccess

    with (
        patch(_P_TABLES, return_value=[_mock_table()]),
        patch(_P_COLUMNS, return_value=[]),
        patch.object(
            __import__("app.api.rules", fromlist=["ai"]).ai,
            "rule_from_nl",
            return_value=NlRuleSuccess(rule=_MOCK_RULE),
        ),
    ):
        resp = client.post(
            "/rules/from-nl",
            json={
                "table_name": "policyholders",
                "messages": [{"role": "user", "content": "Premium must be positive."}],
            },
        )

    assert resp.status_code == 200
    assert resp.json()["type"] == "rule"
    assert resp.json()["rule"]["expectation_type"] == "expect_column_values_to_be_between"


def test_from_nl_multi_turn_success():
    """Multi-turn messages body is accepted and forwarded to ai.rule_from_nl."""
    from app.schemas.rules import NlRuleSuccess
    import app.api.rules as rules_module

    captured_messages: list = []

    def fake_rule_from_nl(session, table_name, columns, messages):
        captured_messages.extend(messages)
        return NlRuleSuccess(rule=_MOCK_RULE)

    rule_payload = json.dumps({"type": "rule", "rule": _MOCK_RULE.model_dump()})
    multi_turn_body = {
        "table_name": "policyholders",
        "messages": [
            {"role": "user", "content": "Premium cannot be negative."},
            {"role": "assistant", "content": rule_payload},
            {"role": "user", "content": "Also no zero."},
        ],
    }

    with (
        patch(_P_TABLES, return_value=[_mock_table()]),
        patch(_P_COLUMNS, return_value=[]),
        patch.object(rules_module.ai, "rule_from_nl", side_effect=fake_rule_from_nl),
    ):
        resp = client.post("/rules/from-nl", json=multi_turn_body)

    assert resp.status_code == 200
    assert len(captured_messages) == 3
    assert captured_messages[0].role == "user"
    assert captured_messages[1].role == "assistant"
    assert captured_messages[2].role == "user"
    assert captured_messages[2].content == "Also no zero."


def test_from_nl_rejects_11_messages():
    """Body with 11 messages returns 422 Unprocessable Entity."""
    messages = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg {i}"}
        for i in range(11)
    ]
    resp = client.post(
        "/rules/from-nl",
        json={"table_name": "policyholders", "messages": messages},
    )
    assert resp.status_code == 422
