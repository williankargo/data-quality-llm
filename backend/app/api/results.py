"""Results API: run GE checks against a table and retrieve run history."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.services.db import get_db
from app.services.ge_engine import GeEngine
from app.services.rules_store import list_rules
from app.services.runs_store import (
    create_run,
    finalize_run,
    get_run,
    list_runs,
    write_result,
)
from app.schemas.runs import CreateRunRequest, RunDetail, RunSummary

router = APIRouter(tags=["results"])


@router.post("/runs", response_model=RunDetail, status_code=201)
def trigger_run(body: CreateRunRequest, session: Session = Depends(get_db)) -> RunDetail:
    rules = list_rules(session, table_name=body.table_name)
    run_id = create_run(session, table_name=body.table_name)

    try:
        engine = GeEngine()
        results = engine.run_rules(body.table_name, rules)

        for rule, result in zip(rules, results):
            write_result(session, run_id=run_id, rule_id=rule.id, result=result)

        finalize_run(session, run_id=run_id, status="success", error_message=None)
    except Exception as exc:
        finalize_run(
            session,
            run_id=run_id,
            status="failed",
            error_message=str(exc)[:500],
        )
        raise HTTPException(status_code=500, detail="GE_EXECUTION_FAILED") from exc

    run = get_run(session, run_id)
    if run is None:
        raise HTTPException(status_code=500, detail="GE_EXECUTION_FAILED")
    return run


@router.get("/runs/{run_id}", response_model=RunDetail)
def fetch_run(run_id: int, session: Session = Depends(get_db)) -> RunDetail:
    run = get_run(session, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="RUN_NOT_FOUND")
    return run


@router.get("/runs", response_model=list[RunSummary])
def fetch_runs(
    table_name: str | None = None,
    limit: int = 20,
    session: Session = Depends(get_db),
) -> list[RunSummary]:
    return list_runs(session, table_name=table_name, limit=limit)
