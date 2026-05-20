"""Anthropic client wrapper for AI-powered rule generation.

Uses Tool Use (structured output) so every response is machine-readable.
Pydantic validation runs after Tool Use as a second safety layer (D#7).
"""

import json
from pathlib import Path

import anthropic

from app.config import settings
from app.schemas.rules import GeRule, NlRuleClarification, NlRuleResponse, NlRuleSuccess
from app.schemas.tables import ColumnInfo

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


class LlmOutputError(Exception):
    """Raised when the LLM tool-use output fails Pydantic validation."""


# ---------------------------------------------------------------------------
# Tool schemas (inline — easy to edit without touching prompt files)
# ---------------------------------------------------------------------------

PROPOSE_RULES_TOOL: dict = {
    "name": "propose_rules",
    "description": "Return between 5 and 10 GE expectation rules for the table.",
    "input_schema": {
        "type": "object",
        "required": ["rules"],
        "properties": {
            "rules": {
                "type": "array",
                "minItems": 5,
                "maxItems": 10,
                "items": {
                    "type": "object",
                    "required": ["expectation_type", "kwargs", "description"],
                    "properties": {
                        "expectation_type": {"type": "string"},
                        "kwargs": {"type": "object"},
                        "description": {"type": "string"},
                    },
                },
            }
        },
    },
}

PROPOSE_RULE_TOOL: dict = {
    "name": "propose_rule",
    "description": "Return a single GE expectation rule translated from plain English.",
    "input_schema": {
        "type": "object",
        "required": ["expectation_type", "kwargs", "description"],
        "properties": {
            "expectation_type": {"type": "string"},
            "kwargs": {"type": "object"},
            "description": {"type": "string"},
        },
    },
}

REQUEST_CLARIFICATION_TOOL: dict = {
    "name": "request_clarification",
    "description": "Ask a specific follow-up question when the description is too vague to translate.",
    "input_schema": {
        "type": "object",
        "required": ["question"],
        "properties": {
            "question": {"type": "string"},
        },
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_template(filename: str, variables: dict[str, str]) -> str:
    """Load a Markdown prompt template and substitute {{variable}} placeholders."""
    template = (_PROMPTS_DIR / filename).read_text(encoding="utf-8")
    for key, value in variables.items():
        template = template.replace("{{" + key + "}}", value)
    return template


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------


class AiGenerator:
    def __init__(self) -> None:
        self.client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    def suggest_rules(
        self,
        table_name: str,
        columns: list[ColumnInfo],
        sample_rows: list[dict],
    ) -> list[GeRule]:
        prompt = _load_template(
            "rule_from_schema.md",
            {
                "table_name": table_name,
                "columns_json": json.dumps(
                    [c.model_dump() for c in columns], indent=2
                ),
                "sample_rows_json": json.dumps(
                    sample_rows[:20], default=str, indent=2
                ),
            },
        )
        response = self.client.messages.create(
            model=settings.LLM_MODEL,
            max_tokens=4096,
            tools=[PROPOSE_RULES_TOOL],
            tool_choice={"type": "tool", "name": "propose_rules"},
            messages=[{"role": "user", "content": prompt}],
        )
        return self._extract_and_validate_rules(response)

    def rule_from_nl(
        self,
        table_name: str,
        columns: list[ColumnInfo],
        description: str,
    ) -> NlRuleResponse:
        prompt = _load_template(
            "rule_from_nl.md",
            {
                "table_name": table_name,
                "columns_json": json.dumps(
                    [c.model_dump() for c in columns], indent=2
                ),
                "user_description": description,
            },
        )
        response = self.client.messages.create(
            model=settings.LLM_MODEL,
            max_tokens=1024,
            tools=[PROPOSE_RULE_TOOL, REQUEST_CLARIFICATION_TOOL],
            tool_choice={"type": "any"},
            messages=[{"role": "user", "content": prompt}],
        )
        return self._dispatch_nl_response(response)

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _extract_and_validate_rules(self, response) -> list[GeRule]:
        tool_block = next(
            (b for b in response.content if b.type == "tool_use"), None
        )
        if tool_block is None:
            raise LlmOutputError("No tool_use block in LLM response")
        try:
            raw_rules = tool_block.input["rules"]
            return [GeRule.model_validate(r) for r in raw_rules]
        except Exception as exc:
            raise LlmOutputError(str(exc)) from exc

    def _dispatch_nl_response(self, response) -> NlRuleResponse:
        tool_block = next(
            (b for b in response.content if b.type == "tool_use"), None
        )
        if tool_block is None:
            raise LlmOutputError("No tool_use block in LLM response")
        try:
            if tool_block.name == "propose_rule":
                rule = GeRule.model_validate(tool_block.input)
                return NlRuleSuccess(rule=rule)
            return NlRuleClarification(question=tool_block.input["question"])
        except Exception as exc:
            raise LlmOutputError(str(exc)) from exc
