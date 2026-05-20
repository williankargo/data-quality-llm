"""CRUD helpers for dq.runs and dq.run_results.

All queries use SQLAlchemy text() — no ORM declarative model.
error_message for individual results is stored in raw_result JSONB
because dq.run_results has no dedicated error_message column.
"""

import json
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.runs import RunDetail, RunResult, RunSummary


def create_run(session: Session, table_name: str) -> int:
    """Insert a new run row with status='running'; return the new run_id."""
    sql = text(
        """
        INSERT INTO dq.runs (table_name, status, started_at)
        VALUES (:table_name, 'running', NOW())
        RETURNING id
        """
    )
    row = session.execute(sql, {"table_name": table_name}).fetchone()
    session.commit()
    return row.id


def finalize_run(
    session: Session,
    run_id: int,
    status: str,
    error_message: str | None,
) -> None:
    """Set the final status and completed_at timestamp on a run."""
    sql = text(
        """
        UPDATE dq.runs
        SET status        = :status,
            completed_at  = NOW(),
            error_message = :error_message
        WHERE id = :run_id
        """
    )
    session.execute(
        sql,
        {"run_id": run_id, "status": status, "error_message": error_message},
    )
    session.commit()


def write_result(
    session: Session,
    run_id: int,
    rule_id: int | None,
    result: RunResult,
) -> None:
    """Persist a single per-rule result row into dq.run_results."""
    raw_result = None
    if result.error_message:
        raw_result = json.dumps({"error_message": result.error_message})

    sql = text(
        """
        INSERT INTO dq.run_results
            (run_id, rule_id, expectation_type, success,
             unexpected_count, unexpected_sample, observed_value, raw_result, status)
        VALUES
            (:run_id, :rule_id, :expectation_type, :success,
             :unexpected_count, :unexpected_sample, :observed_value, CAST(:raw_result AS JSONB), :status)
        """
    )
    session.execute(
        sql,
        {
            "run_id": run_id,
            "rule_id": rule_id,
            "expectation_type": result.expectation_type,
            "success": result.success,
            "unexpected_count": result.unexpected_count,
            "unexpected_sample": (
                json.dumps(result.unexpected_sample)
                if result.unexpected_sample is not None
                else None
            ),
            "observed_value": (
                json.dumps(result.observed_value)
                if result.observed_value is not None
                else None
            ),
            "raw_result": raw_result,
            "status": result.status,
        },
    )
    session.commit()


def get_run(session: Session, run_id: int) -> RunDetail | None:
    """Return a run with its full result list, or None if not found."""
    run_sql = text(
        """
        SELECT r.*,
            COUNT(rr.id) FILTER (WHERE rr.status = 'pass')  AS pass_count,
            COUNT(rr.id) FILTER (WHERE rr.status = 'fail')  AS fail_count,
            COUNT(rr.id) FILTER (WHERE rr.status = 'error') AS error_count
        FROM dq.runs r
        LEFT JOIN dq.run_results rr ON rr.run_id = r.id
        WHERE r.id = :run_id
        GROUP BY r.id
        """
    )
    run_row = session.execute(run_sql, {"run_id": run_id}).fetchone()
    if run_row is None:
        return None

    results = _fetch_results(session, run_id)
    return _row_to_detail(run_row, results)


def list_runs(
    session: Session,
    table_name: str | None = None,
    limit: int = 20,
) -> list[RunSummary]:
    """Return up to *limit* runs ordered by most recent first."""
    _agg = """
        SELECT r.*,
            COUNT(rr.id) FILTER (WHERE rr.status = 'pass')  AS pass_count,
            COUNT(rr.id) FILTER (WHERE rr.status = 'fail')  AS fail_count,
            COUNT(rr.id) FILTER (WHERE rr.status = 'error') AS error_count
        FROM dq.runs r
        LEFT JOIN dq.run_results rr ON rr.run_id = r.id
    """
    if table_name is not None:
        sql = text(
            _agg
            + " WHERE r.table_name = :table_name AND r.status IN ('success', 'failed')"
            + " GROUP BY r.id ORDER BY r.started_at DESC LIMIT :limit"
        )
        rows = session.execute(sql, {"table_name": table_name, "limit": limit}).fetchall()
    else:
        sql = text(
            _agg
            + " WHERE r.status IN ('success', 'failed')"
            + " GROUP BY r.id ORDER BY r.started_at DESC LIMIT :limit"
        )
        rows = session.execute(sql, {"limit": limit}).fetchall()
    return [_row_to_summary(r) for r in rows]


def get_latest_run_for_table(session: Session, table_name: str) -> RunDetail | None:
    """Return the most recent finalized run for a table, with full results."""
    sql = text(
        """
        SELECT id FROM dq.runs
        WHERE table_name = :table_name
          AND status IN ('success', 'failed')
        ORDER BY started_at DESC
        LIMIT 1
        """
    )
    row = session.execute(sql, {"table_name": table_name}).fetchone()
    if row is None:
        return None
    return get_run(session, row.id)


# ------------------------------------------------------------------
# Private helpers
# ------------------------------------------------------------------


def _fetch_results(session: Session, run_id: int) -> list[RunResult]:
    sql = text(
        "SELECT * FROM dq.run_results WHERE run_id = :run_id ORDER BY id"
    )
    rows = session.execute(sql, {"run_id": run_id}).fetchall()
    return [_row_to_result(r) for r in rows]


def _row_to_result(row) -> RunResult:
    raw = row.raw_result or {}
    error_msg: str | None = raw.get("error_message") if isinstance(raw, dict) else None
    return RunResult(
        id=row.id,
        rule_id=row.rule_id,
        expectation_type=row.expectation_type,
        status=row.status,
        success=row.success,
        unexpected_count=row.unexpected_count,
        unexpected_sample=row.unexpected_sample,
        observed_value=row.observed_value,
        error_message=error_msg,
    )


def _row_to_summary(row) -> RunSummary:
    return RunSummary(
        id=row.id,
        table_name=row.table_name,
        status=row.status,
        started_at=row.started_at,
        completed_at=row.completed_at,
        error_message=row.error_message,
        pass_count=int(row.pass_count or 0),
        fail_count=int(row.fail_count or 0),
        error_count=int(row.error_count or 0),
    )


def _row_to_detail(row, results: list[RunResult]) -> RunDetail:
    return RunDetail(
        id=row.id,
        table_name=row.table_name,
        status=row.status,
        started_at=row.started_at,
        completed_at=row.completed_at,
        error_message=row.error_message,
        pass_count=int(row.pass_count or 0),
        fail_count=int(row.fail_count or 0),
        error_count=int(row.error_count or 0),
        results=results,
    )
