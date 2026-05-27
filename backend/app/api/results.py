"""Results API: run GE checks against a table and retrieve run history."""

import csv
import io

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.errors import raise_error
from app.services.ai_generator import AiGenerator, LlmOutputError
from app.services.db import get_db, get_session
from app.services.ge_engine import GeEngine
from app.services.db import get_table_columns
from app.services.rules_store import get_rule, list_rules
from app.services.runs_store import (
    create_run,
    finalize_run,
    get_result_with_table,
    get_run,
    list_runs,
    write_result,
)
from app.schemas.explain import ExplainResponse
from app.schemas.runs import CreateRunRequest, RunDetail, RunSummary

router = APIRouter(tags=["results"])


def _execute_run(run_id: int, table_name: str, rule_ids: list[int] | None) -> None:
    """BackgroundTask: execute GE checks, write results, finalize the run."""
    with get_session() as session:
        try:
            rules = list_rules(session, table_name=table_name, rule_ids=rule_ids)
            columns = get_table_columns(session, table_name)
            engine = GeEngine()
            engine.run_rules(
                table_name,
                rules,
                session=session,
                progress_callback=lambda r: write_result(
                    session, run_id=run_id, rule_id=r.rule_id, result=r
                ),
                columns=columns,
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
        raise_error("RUN_NOT_FOUND")
        return None  # unreachable; satisfies type checker
    return run


@router.get("/runs", response_model=list[RunSummary])
def fetch_runs(
    table_name: str | None = None,
    limit: int = 20,
    session: Session = Depends(get_db),
) -> list[RunSummary]:
    return list_runs(session, table_name=table_name, limit=limit)


@router.post("/results/{result_id}/explain", response_model=ExplainResponse)
def explain_result(result_id: int, session: Session = Depends(get_db)) -> ExplainResponse:
    """Return a plain-English LLM explanation for a failed run result (D#30)."""
    pair = get_result_with_table(session, result_id)
    if pair is None:
        raise_error("RESULT_NOT_FOUND")
        return None  # unreachable; satisfies type checker

    result, table_name = pair
    if result.status != "fail":
        raise_error("RESULT_NOT_FAILED")
        return None  # unreachable

    rule = get_rule(session, result.rule_id) if result.rule_id is not None else None

    try:
        generator = AiGenerator()
        return generator.explain_failure(
            session=session,
            rule_id=result.rule_id,
            expectation_type=result.expectation_type,
            kwargs=rule.kwargs if rule else {},
            unexpected_sample=result.unexpected_sample,
            observed_value=result.observed_value,
            table_name=table_name,
        )
    except LlmOutputError as exc:
        raise_error("LLM_OUTPUT_INVALID", str(exc))
        return None  # unreachable


@router.get("/results/{result_id}/violations.csv")
def download_violations_csv(
    result_id: int,
    session: Session = Depends(get_db),
) -> StreamingResponse:
    """Stream violating rows for a failed result as a CSV file (D#34/D#37).

    Only available for results with status='fail'. Returns RESULT_NOT_FAILED for
    pass/error results (D#35). Returns RESULT_NOT_FOUND for unknown result IDs.
    """
    pair = get_result_with_table(session, result_id)
    if pair is None:
        raise_error("RESULT_NOT_FOUND")
        return None  # unreachable

    result, _ = pair
    if result.status != "fail":
        raise_error("RESULT_NOT_FAILED")
        return None  # unreachable

    rows = result.unexpected_rows or []
    filename = f"violations_result{result_id}.csv"

    def _generate():
        if not rows:
            yield "# No row data available (table has no primary key)\n"
            return
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate()
        for row in rows:
            safe_row = {k: ("" if v is None else str(v)) for k, v in row.items()}
            writer.writerow(safe_row)
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate()

    return StreamingResponse(
        _generate(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
