"""HTTP handlers for rules resources.

Endpoints:
  POST /rules/suggest      — AI-suggest rules from table schema + sample
  POST /rules/from-nl      — Natural language → GE rule (or clarification)
  GET  /rules              — List rules, optionally filtered by table_name
  POST /rules              — Create a rule
  PUT  /rules/{id}         — Update a rule
  DELETE /rules/{id}       — Delete a rule
"""

from typing import Union

import anthropic
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.schemas.rules import (
    CreateRuleRequest,
    NlRuleClarification,
    NlRuleRequest,
    NlRuleSuccess,
    RuleRecord,
    SuggestRequest,
    SuggestResponse,
    UpdateRuleRequest,
)
from app.services.ai_generator import AiGenerator, LlmOutputError
from app.services.db import get_db, get_table_columns, list_public_tables, sample_table
from app.services.rules_store import (
    create_rule,
    delete_rule,
    get_rule,
    list_rules,
    mark_drafts_already_saved,
    update_rule,
)

router = APIRouter(prefix="/rules", tags=["rules"])

# Module-level singleton — constructed once at startup; mocked in tests via patch.
ai = AiGenerator()


# ---------------------------------------------------------------------------
# AI endpoints
# ---------------------------------------------------------------------------


@router.post("/suggest", response_model=SuggestResponse)
def suggest_rules(
    body: SuggestRequest, db: Session = Depends(get_db)
) -> SuggestResponse:
    _require_table(body.table_name, db)
    columns = get_table_columns(db, body.table_name)
    rows = sample_table(db, body.table_name, limit=50)
    try:
        raw_rules = ai.suggest_rules(body.table_name, columns, rows)
    except anthropic.APITimeoutError:
        raise HTTPException(status_code=504, detail="LLM_TIMEOUT")
    except LlmOutputError:
        raise HTTPException(status_code=502, detail="LLM_OUTPUT_INVALID")
    drafts = mark_drafts_already_saved(db, body.table_name, raw_rules)
    return SuggestResponse(drafts=drafts)


@router.post("/from-nl", response_model=Union[NlRuleSuccess, NlRuleClarification])
def rule_from_nl(
    body: NlRuleRequest, db: Session = Depends(get_db)
) -> Union[NlRuleSuccess, NlRuleClarification]:
    _require_table(body.table_name, db)
    columns = get_table_columns(db, body.table_name)
    try:
        result = ai.rule_from_nl(body.table_name, columns, body.description)
    except anthropic.APITimeoutError:
        raise HTTPException(status_code=504, detail="LLM_TIMEOUT")
    except LlmOutputError:
        raise HTTPException(status_code=502, detail="LLM_OUTPUT_INVALID")
    return result


# ---------------------------------------------------------------------------
# CRUD endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=list[RuleRecord])
def get_rules(
    table_name: str | None = None, db: Session = Depends(get_db)
) -> list[RuleRecord]:
    return list_rules(db, table_name=table_name)


@router.post("", response_model=RuleRecord, status_code=201)
def create_rule_endpoint(
    body: CreateRuleRequest, db: Session = Depends(get_db)
) -> RuleRecord:
    return create_rule(db, table_name=body.table_name, source=body.source, rule=body)


@router.put("/{rule_id}", response_model=RuleRecord)
def update_rule_endpoint(
    rule_id: int, body: UpdateRuleRequest, db: Session = Depends(get_db)
) -> RuleRecord:
    if get_rule(db, rule_id) is None:
        raise HTTPException(status_code=404, detail="RULE_NOT_FOUND")
    return update_rule(db, rule_id, body)


@router.delete("/{rule_id}")
def delete_rule_endpoint(
    rule_id: int, db: Session = Depends(get_db)
) -> dict:
    if not delete_rule(db, rule_id):
        raise HTTPException(status_code=404, detail="RULE_NOT_FOUND")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------


def _require_table(table_name: str, db: Session) -> None:
    tables = list_public_tables(db)
    if not any(t.name == table_name for t in tables):
        raise HTTPException(status_code=404, detail="TABLE_NOT_FOUND")
