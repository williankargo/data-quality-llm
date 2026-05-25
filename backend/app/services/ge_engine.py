"""Great Expectations 1.x SQL Datasource execution engine.

Uses an ephemeral context (no GE file store) so all state lives in memory.
DATABASE_URL dialect prefix is stripped before passing to GE (D#16).
Rules are validated in parallel via ThreadPoolExecutor(max_workers=4) (D#29).
Violating rows are fetched as complete row dicts via PK index lookup (D#33/D#36).
"""

import json
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import great_expectations as gx
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.config import settings
from app.schemas.rules import RuleRecord
from app.schemas.runs import ResultStatus, RunResult
from app.services.db import get_session
from app.services.pk_inspector import get_pk_columns

# COMPLETE format returns partial_unexpected_index_list when
# unexpected_index_column_names is set (D#36). Cap 1000 per D#37.
_RESULT_FORMAT: dict = {
    "result_format": "COMPLETE",
    "partial_unexpected_count": 1000,
}
_MAX_WORKERS = 4


def _snake_to_camel(name: str) -> str:
    return "".join(word.capitalize() for word in name.split("_"))


def _sanitize_error(msg: str) -> str:
    """Remove connection strings and truncate to 200 chars."""
    msg = re.sub(r"postgresql\S*", "[redacted]", msg)
    return msg[:200]


class GeEngine:
    """Wraps a single GE ephemeral context for one run.

    Create a new instance per run to avoid asset-name collisions.
    """

    def __init__(self) -> None:
        self.context = gx.get_context(mode="ephemeral")
        self.datasource = self.context.data_sources.add_postgres(
            name="dq_pg",
            connection_string=settings.DATABASE_URL,
        )

    def run_rules(
        self,
        table_name: str,
        rules: list[RuleRecord],
        session: Session | None = None,
        progress_callback: Callable[[RunResult], None] | None = None,
    ) -> list[RunResult]:
        """Validate every rule against the table in parallel; return one RunResult per rule.

        progress_callback is invoked from the *calling* thread after each future
        completes, so it is safe to use a shared SQLAlchemy Session inside it.
        session is used to look up PK columns once before the executor starts;
        each thread opens its own session for _fetch_full_rows.
        """
        asset = self.datasource.add_table_asset(
            name=f"asset_{table_name}",
            table_name=table_name,
        )
        batch_def = asset.add_batch_definition_whole_table(name=f"batch_{table_name}")
        batch = batch_def.get_batch()

        # Resolve PK columns once in the main thread (D#36).
        pk_cols: list[str] | None = None
        if session is not None:
            try:
                pk_cols = get_pk_columns(session, table_name)
            except Exception:
                pk_cols = None  # be defensive; fallback to no-PK path

        # Build result_format once; threads get a shallow copy with optional pk field.
        base_fmt = dict(_RESULT_FORMAT)
        if pk_cols:
            base_fmt["unexpected_index_column_names"] = pk_cols

        def _run_one(rule: RuleRecord) -> RunResult:
            try:
                expectation = self._build_expectation(rule.expectation_type, rule.kwargs)
                try:
                    ge_result = batch.validate(expectation, result_format=base_fmt)
                except OperationalError:
                    # Retry once on connection-recycle errors from Supabase Session Pooler (D#29).
                    ge_result = batch.validate(expectation, result_format=base_fmt)
                result = self._normalize_pass_fail(rule, ge_result)

                # Fetch complete rows for failed results when we have PK columns (D#36/D#33).
                if result.status == "fail" and pk_cols:
                    index_list: list[dict] = (ge_result.result or {}).get(
                        "partial_unexpected_index_list"
                    ) or []
                    result.unexpected_rows = self._fetch_full_rows(table_name, pk_cols, index_list)
                    result.truncated = len(index_list) >= 1000

                return result
            except Exception as exc:
                return self._normalize_error(rule, exc)

        results: list[RunResult] = []
        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
            futures = {pool.submit(_run_one, r): r for r in rules}
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                if progress_callback is not None:
                    progress_callback(result)
        return results

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_expectation(
        self, expectation_type: str, kwargs: dict
    ) -> gx.expectations.Expectation:
        camel = _snake_to_camel(expectation_type)
        try:
            cls = getattr(gx.expectations, camel)
        except AttributeError as exc:
            raise ValueError(f"Unknown expectation type: {expectation_type}") from exc
        return cls(**kwargs)

    def _normalize_pass_fail(self, rule: RuleRecord, ge_result: Any) -> RunResult:
        # GE 1.x does not raise Python exceptions for invalid columns; instead
        # it returns success=False with exception_info containing raised_exception=True.
        # Detect this and route to _normalize_error so callers see status="error"
        # rather than status="fail" (D#18).
        exc_info = getattr(ge_result, "exception_info", {}) or {}
        if self._exception_was_raised(exc_info):
            msg = self._first_exception_message(exc_info) or "GE raised an internal exception"
            return self._normalize_error(rule, Exception(msg))

        result_dict: dict = ge_result.result if ge_result.result else {}
        status: ResultStatus = "pass" if ge_result.success else "fail"
        raw_sample = result_dict.get("partial_unexpected_list") or []
        return RunResult(
            id=0,
            rule_id=rule.id,
            expectation_type=rule.expectation_type,
            status=status,
            success=bool(ge_result.success),
            unexpected_count=result_dict.get("unexpected_count"),
            unexpected_sample=raw_sample[:3] if raw_sample else None,
            unexpected_rows=None,
            truncated=False,
            observed_value=result_dict.get("observed_value"),
            error_message=None,
        )

    def _fetch_full_rows(
        self,
        table_name: str,
        pk_cols: list[str],
        index_list: list[dict],
    ) -> list[dict]:
        """Fetch complete rows from *table_name* whose PKs appear in *index_list*.

        index_list is [{"id": 42}, {"id": 107}, ...] for single PK, or
        [{"col_a": 1, "col_b": 2}, ...] for composite PK (D#36).
        Opens its own DB session so it is safe to call from worker threads.
        """
        if not index_list:
            return []

        with get_session() as session:
            if len(pk_cols) == 1:
                pk_col = pk_cols[0]
                values = [row[pk_col] for row in index_list if pk_col in row]
                if not values:
                    return []
                placeholders = ", ".join(f":v{i}" for i in range(len(values)))
                params: dict = {f"v{i}": v for i, v in enumerate(values)}
                sql = text(
                    f'SELECT * FROM public."{table_name}" WHERE "{pk_col}" IN ({placeholders})'
                )
            else:
                # Composite PK: WHERE (col_a, col_b) IN ((v0_0, v0_1), (v1_0, v1_1), ...)
                col_expr = ", ".join(f'"{c}"' for c in pk_cols)
                row_parts: list[str] = []
                params = {}
                for i, row in enumerate(index_list):
                    cell_placeholders = ", ".join(f":r{i}_{j}" for j in range(len(pk_cols)))
                    row_parts.append(f"({cell_placeholders})")
                    for j, col in enumerate(pk_cols):
                        params[f"r{i}_{j}"] = row.get(col)
                sql = text(
                    f'SELECT * FROM public."{table_name}"'
                    f" WHERE ({col_expr}) IN ({', '.join(row_parts)})"
                )

            rows = session.execute(sql, params).fetchall()
            return [_serialize_row(dict(r._mapping)) for r in rows]

    @staticmethod
    def _exception_was_raised(exc_info: dict) -> bool:
        """Return True if GE's exception_info signals a raised exception.

        GE 1.x uses two shapes:
        - Flat (normal validation): {"raised_exception": bool, ...}
        - Nested (metric error): {<metric_id>: {"raised_exception": bool, ...}, ...}
        """
        if "raised_exception" in exc_info:
            return bool(exc_info["raised_exception"])
        for value in exc_info.values():
            if isinstance(value, dict) and value.get("raised_exception"):
                return True
        return False

    @staticmethod
    def _first_exception_message(exc_info: dict) -> str | None:
        """Extract the first non-None exception_message from exc_info."""
        if "exception_message" in exc_info:
            return exc_info.get("exception_message")
        for value in exc_info.values():
            if isinstance(value, dict) and value.get("exception_message"):
                return value["exception_message"]
        return None

    def _normalize_error(self, rule: RuleRecord, exc: Exception) -> RunResult:
        return RunResult(
            id=0,
            rule_id=rule.id,
            expectation_type=rule.expectation_type,
            status="error",
            success=False,
            unexpected_count=None,
            unexpected_sample=None,
            unexpected_rows=None,
            truncated=False,
            observed_value=None,
            error_message=_sanitize_error(str(exc)),
        )


def _serialize_row(row: dict) -> dict:
    """Convert non-JSON-serializable values (Decimal, date, etc.) to strings."""
    out: dict = {}
    for k, v in row.items():
        if v is None:
            out[k] = None
        else:
            try:
                json.dumps(v)
                out[k] = v
            except (TypeError, ValueError):
                out[k] = str(v)
    return out
