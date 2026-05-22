"""Anthropic client wrapper for AI-powered rule generation.

Uses Tool Use (structured output) so every response is machine-readable.
Pydantic validation runs after Tool Use as a second safety layer (D#7).
LLM responses are cached in dq.llm_cache (D#24); bump PROMPT_VERSION_* here
whenever the corresponding prompt template changes to invalidate stale entries.
"""

import json
from pathlib import Path

import anthropic
from sqlalchemy.orm import Session

from app.config import settings
from app.schemas.explain import ChatMessage
from app.schemas.rules import GeRule, NlRuleClarification, NlRuleResponse, NlRuleSuccess
from app.schemas.tables import ColumnInfo
from app.services.llm_cache import get_cached, make_cache_key, set_cached

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

# Bump these whenever the corresponding prompt template file changes.
# A version change invalidates all existing cache entries for that prompt path.
PROMPT_VERSION_SCHEMA = "v1"
PROMPT_VERSION_NL = "v2"       # bumped: multi-turn messages support (D#25)
PROMPT_VERSION_EXPLAIN = "v1"  # used in Phase 6


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
        session: Session,
        table_name: str,
        columns: list[ColumnInfo],
        sample_rows: list[dict],
    ) -> list[GeRule]:
        cache_key = make_cache_key(
            "rule_from_schema",
            PROMPT_VERSION_SCHEMA,
            table_name=table_name,
            columns=[c.model_dump() for c in columns],
            sample=sample_rows[:20],
        )
        if (cached := get_cached(session, cache_key)) is not None:
            return [GeRule.model_validate(r) for r in cached["rules"]]

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
        rules = self._extract_and_validate_rules(response)
        set_cached(
            session,
            cache_key,
            "rule_from_schema",
            {"rules": [r.model_dump() for r in rules]},
        )
        return rules

    def rule_from_nl(
        self,
        session: Session,
        table_name: str,
        columns: list[ColumnInfo],
        messages: list[ChatMessage],
    ) -> NlRuleResponse:
        cache_key = make_cache_key(
            "rule_from_nl",
            PROMPT_VERSION_NL,
            table_name=table_name,
            columns=[c.model_dump() for c in columns],
            messages=[m.model_dump() for m in messages],
        )
        if (cached := get_cached(session, cache_key)) is not None:
            return _nl_from_cache(cached)

        system_prompt = _load_template(
            "rule_from_nl.md",
            {
                "table_name": table_name,
                "columns_json": json.dumps(
                    [c.model_dump() for c in columns], indent=2
                ),
            },
        )
        anthropic_messages = _build_anthropic_messages(messages)
        response = self.client.messages.create(
            model=settings.LLM_MODEL,
            max_tokens=1024,
            system=system_prompt,
            tools=[PROPOSE_RULE_TOOL, REQUEST_CLARIFICATION_TOOL],
            tool_choice={"type": "any"},
            messages=anthropic_messages,
        )
        result = self._dispatch_nl_response(response)
        set_cached(session, cache_key, "rule_from_nl", _nl_to_cache(result))
        return result

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


# ---------------------------------------------------------------------------
# Multi-turn message format helpers
# ---------------------------------------------------------------------------


def _build_anthropic_messages(messages: list[ChatMessage]) -> list[dict]:
    """Convert ChatMessage list to Anthropic Messages API format (D#25).

    Assistant messages store a JSON-serialised NlRuleResponse.  We reconstruct
    proper tool_use / tool_result block pairs so the API accepts the history.
    Each pair:
      assistant turn  → content: [tool_use block]
      next user turn  → content: [tool_result block + text block]
    """
    result: list[dict] = []
    i = 0
    while i < len(messages):
        msg = messages[i]
        if msg.role == "user":
            result.append({"role": "user", "content": msg.content})
            i += 1
        else:
            # Parse stored NlRuleResponse JSON to reconstruct tool_use block.
            try:
                parsed = json.loads(msg.content)
                tool_id = f"tu_{i:03d}"
                if parsed.get("type") == "rule":
                    tool_name = "propose_rule"
                    tool_input = parsed["rule"]
                else:
                    tool_name = "request_clarification"
                    tool_input = {"question": parsed.get("question", "")}
            except (json.JSONDecodeError, KeyError):
                # Fallback: pass as plain text so the conversation is not lost.
                result.append({"role": "assistant", "content": msg.content})
                i += 1
                continue

            result.append({
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": tool_id, "name": tool_name, "input": tool_input}
                ],
            })
            i += 1
            # The next user message must close the tool_use with a tool_result block.
            if i < len(messages) and messages[i].role == "user":
                result.append({
                    "role": "user",
                    "content": [
                        {"type": "tool_result", "tool_use_id": tool_id, "content": "OK"},
                        {"type": "text", "text": messages[i].content},
                    ],
                })
                i += 1
    return result


# ---------------------------------------------------------------------------
# Cache serialization helpers for NlRuleResponse discriminated union
# ---------------------------------------------------------------------------


def _nl_to_cache(result: NlRuleResponse) -> dict:
    if isinstance(result, NlRuleSuccess):
        return {"type": "rule", "rule": result.rule.model_dump()}
    return {"type": "clarification", "question": result.question}  # type: ignore[union-attr]


def _nl_from_cache(cached: dict) -> NlRuleResponse:
    if cached.get("type") == "rule":
        return NlRuleSuccess(rule=GeRule.model_validate(cached["rule"]))
    return NlRuleClarification(question=cached["question"])
