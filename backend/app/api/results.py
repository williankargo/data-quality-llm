"""Results API: run GE checks against a table and retrieve run history."""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.errors import raise_error
from app.services.db import get_db, get_session
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


def _execute_run(run_id: int, table_name: str, rule_ids: list[int] | None) -> None:
    """BackgroundTask: execute GE checks, write results, finalize the run."""
    with get_session() as session:
        try:
            rules = list_rules(session, table_name=table_name, rule_ids=rule_ids)
            engine = GeEngine()
            engine.run_rules(
                table_name,
                rules,
                progress_callback=lambda r: write_result(
                    session, run_id=run_id, rule_id=r.rule_id, result=r
                ),
            )
            finalize_run(session, run_id=run_id, status="success", error_message=None)
        except Exception as exc:
            finalize_run(
                session,
                run_id=run_id,
                status="failed",
                error_message=str(exc)[:200],
            )


@router.post("/runs", response_model=RunSummary, status_code=202)
def trigger_run(
    body: CreateRunRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db),
) -> RunSummary:
    """Create a run record, queue execution as a background task, return 202."""
    if body.rule_ids is not None:
        matched = list_rules(session, table_name=body.table_name, rule_ids=body.rule_ids)
        if len(matched) != len(set(body.rule_ids)):
            raise_error("INVALID_RULE_IDS")

    run_id = create_run(session, table_name=body.table_name)
    background_tasks.add_task(_execute_run, run_id, body.table_name, body.rule_ids)

    run = get_run(session, run_id)
    assert run is not None, "get_run returned None immediately after create_run"
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
