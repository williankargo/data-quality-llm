"""Great Expectations 1.x SQL Datasource execution engine.

Uses an ephemeral context (no GE file store) so all state lives in memory.
DATABASE_URL dialect prefix is stripped before passing to GE (D#16).
"""

import re
from typing import Any

import great_expectations as gx

from app.config import settings
from app.schemas.rules import RuleRecord
from app.schemas.runs import ResultStatus, RunResult

_RESULT_FORMAT = {"result_format": "SUMMARY", "partial_unexpected_count": 3}


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
        # GE add_postgres expects plain postgresql:// not postgresql+psycopg://
        pg_url = settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)
        self.datasource = self.context.data_sources.add_postgres(
            name="dq_pg",
            connection_string=pg_url,
        )

    def run_rules(self, table_name: str, rules: list[RuleRecord]) -> list[RunResult]:
        """Validate every rule against the table; return one RunResult per rule.

        Does not write to DB — caller (runs_store) is responsible for persistence.
        """
        asset = self.datasource.add_table_asset(
            name=f"asset_{table_name}",
            table_name=table_name,
        )
        batch_def = asset.add_batch_definition_whole_table(name=f"batch_{table_name}")
        batch = batch_def.get_batch()

        results: list[RunResult] = []
        for rule in rules:
            try:
                expectation = self._build_expectation(rule.expectation_type, rule.kwargs)
                ge_result = batch.validate(expectation, result_format=_RESULT_FORMAT)
                results.append(self._normalize_pass_fail(rule, ge_result))
            except Exception as exc:
                results.append(self._normalize_error(rule, exc))
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
            # Extract the first exception message found in the exception_info payload.
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
            observed_value=result_dict.get("observed_value"),
            error_message=None,
        )

    @staticmethod
    def _exception_was_raised(exc_info: dict) -> bool:
        """Return True if GE's exception_info signals a raised exception.

        GE 1.x uses two shapes:
        - Flat (normal validation): {"raised_exception": bool, ...}
        - Nested (metric error): {<metric_id>: {"raised_exception": bool, ...}, ...}
        """
        # Flat shape
        if "raised_exception" in exc_info:
            return bool(exc_info["raised_exception"])
        # Nested shape: any metric entry with raised_exception=True is sufficient
        for value in exc_info.values():
            if isinstance(value, dict) and value.get("raised_exception"):
                return True
        return False

    @staticmethod
    def _first_exception_message(exc_info: dict) -> str | None:
        """Extract the first non-None exception_message from exc_info."""
        # Flat shape
        if "exception_message" in exc_info:
            return exc_info.get("exception_message")
        # Nested shape
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
            observed_value=None,
            error_message=_sanitize_error(str(exc)),
        )
