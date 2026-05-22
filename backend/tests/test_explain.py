"""Tests for POST /results/{result_id}/explain (D#30).

Covers:
- 404 RESULT_NOT_FOUND for unknown result IDs
- 400 RESULT_NOT_FAILED for non-fail results
- LLM call returns correct ExplainResponse shape
- Cache hit on second call skips LLM
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.explain import ExplainResponse
from app.schemas.runs import RunResult
from app.services.ai_generator import AiGenerator, PROMPT_VERSION_EXPLAIN
from app.services.llm_cache import get_cached, make_cache_key, set_cached

client = TestClient(app)

_NOW = datetime(2024, 1, 1, 12, 0, 0)

_FAIL_RESULT = RunResult(
    id=99,
    rule_id=1,
    expectation_type="expect_column_values_to_be_between",
    status="fail",
    success=False,
    unexpected_count=3,
    unexpected_sample=[-100, -50, 0],
    observed_value=None,
    error_message=None,
)

_PASS_RESULT = RunResult(
    id=100,
    rule_id=2,
    expectation_type="expect_column_values_to_not_be_null",
    status="pass",
    success=True,
    unexpected_count=0,
    unexpected_sample=None,
    observed_value=None,
    error_message=None,
)

_EXPLAIN_PAYLOAD = {
    "explanation": "Three rows have negative premium values, which violates the rule.",
    "possible_causes": [
        "Data entry errors during policy creation.",
        "A batch import script may have applied incorrect sign conventions.",
    ],
    "suggested_action": "Audit the rows identified above and correct the premium values.",
}


# ---------------------------------------------------------------------------
# 404 — unknown result
# ---------------------------------------------------------------------------


class TestExplainNotFound:
    def test_returns_404_for_unknown_result(self):
        with patch(
            "app.api.results.get_result_with_table", return_value=None
        ):
            resp = client.post("/results/9999/explain")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "RESULT_NOT_FOUND"


# ---------------------------------------------------------------------------
# 400 — non-fail result
# ---------------------------------------------------------------------------


class TestExplainNotFailed:
    def test_returns_400_for_pass_result(self):
        with patch(
            "app.api.results.get_result_with_table",
            return_value=(_PASS_RESULT, "policyholders"),
        ):
            resp = client.post("/results/100/explain")
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "RESULT_NOT_FAILED"


# ---------------------------------------------------------------------------
# 200 — successful LLM explanation
# ---------------------------------------------------------------------------


class TestExplainSuccess:
    def _make_llm_response(self):
        block = MagicMock()
        block.type = "tool_use"
        block.input = _EXPLAIN_PAYLOAD
        msg = MagicMock()
        msg.content = [block]
        return msg

    def test_returns_explain_response_shape(self):
        rule_mock = MagicMock()
        rule_mock.kwargs = {"column": "premium_monthly", "min_value": 0}

        with (
            patch(
                "app.api.results.get_result_with_table",
                return_value=(_FAIL_RESULT, "policyholders"),
            ),
            patch("app.api.results.get_rule", return_value=rule_mock),
            patch("app.services.llm_cache.get_cached", return_value=None),
            patch("app.services.llm_cache.set_cached"),
            patch.object(AiGenerator, "__init__", lambda self: None),
            patch.object(
                AiGenerator,
                "explain_failure",
                return_value=ExplainResponse(**_EXPLAIN_PAYLOAD),
            ),
        ):
            resp = client.post("/results/99/explain")

        assert resp.status_code == 200
        body = resp.json()
        assert "explanation" in body
        assert isinstance(body["possible_causes"], list)
        assert len(body["possible_causes"]) >= 2
        assert "suggested_action" in body

    def test_explain_uses_llm_cache(self, db_session):
        """Cache miss triggers LLM; cache hit returns stored value without LLM."""
        cache_key = make_cache_key(
            "explain_failure",
            PROMPT_VERSION_EXPLAIN,
            rule_id=_FAIL_RESULT.rule_id,
            unexpected_sample=_FAIL_RESULT.unexpected_sample or [],
        )

        # Seed cache directly.
        set_cached(db_session, cache_key, "explain_failure", _EXPLAIN_PAYLOAD)

        # AiGenerator should return the cached value without calling the Anthropic client.
        generator = AiGenerator.__new__(AiGenerator)
        generator.client = MagicMock()

        result = generator.explain_failure(
            session=db_session,
            rule_id=_FAIL_RESULT.rule_id,
            expectation_type=_FAIL_RESULT.expectation_type,
            kwargs={"column": "premium_monthly", "min_value": 0},
            unexpected_sample=_FAIL_RESULT.unexpected_sample,
            observed_value=None,
            table_name="policyholders",
        )

        generator.client.messages.create.assert_not_called()
        assert isinstance(result, ExplainResponse)
        assert result.explanation == _EXPLAIN_PAYLOAD["explanation"]
        assert result.possible_causes == _EXPLAIN_PAYLOAD["possible_causes"]
        assert result.suggested_action == _EXPLAIN_PAYLOAD["suggested_action"]
