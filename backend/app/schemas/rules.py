"""Pydantic models for GE expectation rules and suggestion/NL endpoints."""

from datetime import datetime
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field


class GeRule(BaseModel):
    """Core GE rule structure shared across store, API, and AI generator output."""

    model_config = ConfigDict(strict=False)

    expectation_type: str
    kwargs: dict[str, Any]
    description: str


class RuleRecord(GeRule):
    """Rule as stored in dq.rules — includes DB-assigned fields."""

    id: int
    table_name: str
    source: Literal["ai_schema", "ai_nl", "user"]
    created_at: datetime
    updated_at: datetime


class RuleDraft(GeRule):
    """LLM-suggested rule before it is saved; carries duplicate flag (D#22)."""

    already_saved: bool


class SuggestRequest(BaseModel):
    table_name: str


class SuggestResponse(BaseModel):
    drafts: list[RuleDraft]


class NlRuleRequest(BaseModel):
    table_name: str
    description: str = Field(min_length=3, max_length=500)


class NlRuleSuccess(BaseModel):
    type: Literal["rule"] = "rule"
    rule: GeRule


class NlRuleClarification(BaseModel):
    type: Literal["clarification"] = "clarification"
    question: str


NlRuleResponse = Annotated[
    Union[NlRuleSuccess, NlRuleClarification],
    Field(discriminator="type"),
]


class CreateRuleRequest(GeRule):
    table_name: str
    source: Literal["ai_schema", "ai_nl", "user"] = "user"


class UpdateRuleRequest(GeRule):
    """PUT body — may update expectation_type, kwargs, description only."""

    pass
