"""Unit tests for type_compat filtering inside AiGenerator (D#B).

Covers all four new code paths added in the uncommitted changes:
  - suggest_rules: cache hit path filters incompatible rules
  - suggest_rules: LLM path filters incompatible rules
  - rule_from_nl: cache hit path converts incompatible NlRuleSuccess → NlRuleClarification
  - rule_from_nl: LLM path converts incompatible NlRuleSuccess → NlRuleClarification

No live DB or Anthropic calls are made.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.schemas.explain import ChatMessage
from app.schemas.rules import GeRule, NlRuleClarification, NlRuleSuccess
from app.schemas.tables import ColumnInfo
from app.services.ai_generator import AiGenerator

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_REGEX_RULE = {
    "expectation_type": "expect_column_values_to_match_regex",
    "kwargs": {"column": "birth_date", "regex": r"\d{4}-\d{2}-\d{2}"},
    "description": "Birth date must match YYYY-MM-DD.",
}

_NULL_RULE = {
    "expectation_type": "expect_column_values_to_not_be_null",
    "kwargs": {"column": "birth_date"},
    "description": "Birth date must not be null.",
}

_DATE_COL = ColumnInfo(name="birth_date", data_type="date", is_nullable=True, column_default=None)
_TEXT_COL = ColumnInfo(name="email", data_type="character varying", is_nullable=True, column_default=None)

_MESSAGES = [ChatMessage(role="user", content="Birth date must look like YYYY-MM-DD.")]

_P_GET_CACHED = "app.services.ai_generator.get_cached"
_P_SET_CACHED = "app.services.ai_generator.set_cached"


def _make_generator() -> AiGenerator:
    gen = object.__new__(AiGenerator)
    gen.client = MagicMock()
    return gen


def _schema_llm_response(*rules_data: dict) -> MagicMock:
    block = MagicMock()
    block.type = "tool_use"
    block.input = {"rules": list(rules_data)}
    resp = MagicMock()
    resp.content = [block]
    return resp


def _nl_llm_response(rule_data: dict) -> MagicMock:
    block = MagicMock()
    block.type = "tool_use"
    block.name = "propose_rule"
    block.input = rule_data
    resp = MagicMock()
    resp.content = [block]
    return resp


# ---------------------------------------------------------------------------
# suggest_rules — cache hit path
# ---------------------------------------------------------------------------


class TestSuggestRulesCacheHit:
    def test_incompatible_rule_is_filtered(self):
        gen = _make_generator()
        cached_payload = {"rules": [_REGEX_RULE]}  # regex on date col → incompatible

        with patch(_P_GET_CACHED, return_value=cached_payload):
            result = gen.suggest_rules(
                session=MagicMock(),
                table_name="policyholders",
                columns=[_DATE_COL],
                sample_rows=[],
            )

        assert result == []

    def test_compatible_rule_passes_through(self):
        gen = _make_generator()
        cached_payload = {"rules": [_NULL_RULE]}

        with patch(_P_GET_CACHED, return_value=cached_payload):
            result = gen.suggest_rules(
                session=MagicMock(),
                table_name="policyholders",
                columns=[_DATE_COL],
                sample_rows=[],
            )

        assert len(result) == 1
        assert result[0].expectation_type == "expect_column_values_to_not_be_null"

    def test_mixed_rules_only_compatible_returned(self):
        gen = _make_generator()
        cached_payload = {"rules": [_REGEX_RULE, _NULL_RULE]}

        with patch(_P_GET_CACHED, return_value=cached_payload):
            result = gen.suggest_rules(
                session=MagicMock(),
                table_name="policyholders",
                columns=[_DATE_COL],
                sample_rows=[],
            )

        assert len(result) == 1
        assert result[0].expectation_type == "expect_column_values_to_not_be_null"


# ---------------------------------------------------------------------------
# suggest_rules — LLM path
# ---------------------------------------------------------------------------


class TestSuggestRulesLlmPath:
    def test_incompatible_rule_is_filtered(self):
        gen = _make_generator()
        gen.client.messages.create.return_value = _schema_llm_response(_REGEX_RULE)

        with patch(_P_GET_CACHED, return_value=None), patch(_P_SET_CACHED):
            result = gen.suggest_rules(
                session=MagicMock(),
                table_name="policyholders",
                columns=[_DATE_COL],
                sample_rows=[],
            )

        assert result == []

    def test_compatible_rule_passes_through(self):
        gen = _make_generator()
        gen.client.messages.create.return_value = _schema_llm_response(_NULL_RULE)

        with patch(_P_GET_CACHED, return_value=None), patch(_P_SET_CACHED):
            result = gen.suggest_rules(
                session=MagicMock(),
                table_name="policyholders",
                columns=[_DATE_COL],
                sample_rows=[],
            )

        assert len(result) == 1
        assert result[0].expectation_type == "expect_column_values_to_not_be_null"

    def test_filtered_result_is_cached(self):
        """set_cached must be called with only the compatible rules (not the rejected one)."""
        gen = _make_generator()
        gen.client.messages.create.return_value = _schema_llm_response(_REGEX_RULE, _NULL_RULE)

        captured: list[dict] = []

        def capture_set(session, key, kind, payload):
            captured.append(payload)

        with patch(_P_GET_CACHED, return_value=None), patch(_P_SET_CACHED, side_effect=capture_set):
            result = gen.suggest_rules(
                session=MagicMock(),
                table_name="policyholders",
                columns=[_DATE_COL],
                sample_rows=[],
            )

        assert len(result) == 1
        assert len(captured) == 1
        saved_types = [r["expectation_type"] for r in captured[0]["rules"]]
        assert "expect_column_values_to_match_regex" not in saved_types
        assert "expect_column_values_to_not_be_null" in saved_types


# ---------------------------------------------------------------------------
# rule_from_nl — cache hit path
# ---------------------------------------------------------------------------


class TestRuleFromNlCacheHit:
    def test_incompatible_success_becomes_clarification(self):
        gen = _make_generator()
        cached_payload = {"type": "rule", "rule": _REGEX_RULE}

        with patch(_P_GET_CACHED, return_value=cached_payload):
            result = gen.rule_from_nl(
                session=MagicMock(),
                table_name="policyholders",
                columns=[_DATE_COL],
                messages=_MESSAGES,
            )

        assert isinstance(result, NlRuleClarification)
        assert "text / varchar" in result.question

    def test_compatible_success_stays_success(self):
        gen = _make_generator()
        cached_payload = {"type": "rule", "rule": _NULL_RULE}

        with patch(_P_GET_CACHED, return_value=cached_payload):
            result = gen.rule_from_nl(
                session=MagicMock(),
                table_name="policyholders",
                columns=[_DATE_COL],
                messages=_MESSAGES,
            )

        assert isinstance(result, NlRuleSuccess)
        assert result.rule.expectation_type == "expect_column_values_to_not_be_null"

    def test_cached_clarification_is_returned_unchanged(self):
        gen = _make_generator()
        cached_payload = {"type": "clarification", "question": "Which column?"}

        with patch(_P_GET_CACHED, return_value=cached_payload):
            result = gen.rule_from_nl(
                session=MagicMock(),
                table_name="policyholders",
                columns=[_DATE_COL],
                messages=_MESSAGES,
            )

        assert isinstance(result, NlRuleClarification)
        assert result.question == "Which column?"


# ---------------------------------------------------------------------------
# rule_from_nl — LLM path
# ---------------------------------------------------------------------------


class TestRuleFromNlLlmPath:
    def test_incompatible_success_becomes_clarification(self):
        gen = _make_generator()
        gen.client.messages.create.return_value = _nl_llm_response(_REGEX_RULE)

        with patch(_P_GET_CACHED, return_value=None), patch(_P_SET_CACHED):
            result = gen.rule_from_nl(
                session=MagicMock(),
                table_name="policyholders",
                columns=[_DATE_COL],
                messages=_MESSAGES,
            )

        assert isinstance(result, NlRuleClarification)
        assert "text / varchar" in result.question

    def test_compatible_success_stays_success(self):
        gen = _make_generator()
        gen.client.messages.create.return_value = _nl_llm_response(_NULL_RULE)

        with patch(_P_GET_CACHED, return_value=None), patch(_P_SET_CACHED):
            result = gen.rule_from_nl(
                session=MagicMock(),
                table_name="policyholders",
                columns=[_DATE_COL],
                messages=_MESSAGES,
            )

        assert isinstance(result, NlRuleSuccess)
        assert result.rule.expectation_type == "expect_column_values_to_not_be_null"

    def test_incompatible_clarification_is_cached(self):
        """The downgraded NlRuleClarification (not the original rule) must be cached."""
        gen = _make_generator()
        gen.client.messages.create.return_value = _nl_llm_response(_REGEX_RULE)

        captured: list = []

        def capture_set(session, key, kind, payload):
            captured.append(payload)

        with patch(_P_GET_CACHED, return_value=None), patch(_P_SET_CACHED, side_effect=capture_set):
            result = gen.rule_from_nl(
                session=MagicMock(),
                table_name="policyholders",
                columns=[_DATE_COL],
                messages=_MESSAGES,
            )

        assert isinstance(result, NlRuleClarification)
        assert len(captured) == 1
        assert captured[0]["type"] == "clarification"
        assert "text / varchar" in captured[0]["question"]

    def test_regex_on_text_col_stays_success(self):
        """Regex on a varchar column must not be downgraded."""
        gen = _make_generator()
        email_rule = {
            "expectation_type": "expect_column_values_to_match_regex",
            "kwargs": {"column": "email", "regex": r".*@.*"},
            "description": "Email must contain @.",
        }
        gen.client.messages.create.return_value = _nl_llm_response(email_rule)

        with patch(_P_GET_CACHED, return_value=None), patch(_P_SET_CACHED):
            result = gen.rule_from_nl(
                session=MagicMock(),
                table_name="policyholders",
                columns=[_TEXT_COL],
                messages=_MESSAGES,
            )

        assert isinstance(result, NlRuleSuccess)
        assert result.rule.expectation_type == "expect_column_values_to_match_regex"
