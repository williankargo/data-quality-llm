"""Tests for type_compat.check_rule_type_compat and GeEngine pre-flight check (Option B).

Covers:
- check_rule_type_compat returns None for compatible rules
- check_rule_type_compat returns error string for string-only expectations on non-text columns
- check_rule_type_compat includes date-specific advice for date/timestamp columns
- check_rule_type_compat passes through unknown column names
- check_rule_type_compat passes through non-string-only expectations unconditionally
- GeEngine._run_one routes to status="error" when pre-flight check fails
"""

from unittest.mock import MagicMock, patch

import pytest

from app.schemas.runs import RunResult
from app.schemas.tables import ColumnInfo
from app.services.ge_engine import GeEngine
from app.services.type_compat import check_rule_type_compat


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _col(name: str, data_type: str) -> ColumnInfo:
    return ColumnInfo(name=name, data_type=data_type, is_nullable=True, column_default=None)


_TEXT_COL = _col("email", "character varying")
_DATE_COL = _col("birth_date", "date")
_INT_COL = _col("age", "integer")
_TS_COL = _col("created_at", "timestamp without time zone")


# ---------------------------------------------------------------------------
# check_rule_type_compat
# ---------------------------------------------------------------------------


class TestCheckRuleTypeCompat:
    def test_non_string_expectation_always_passes(self):
        assert check_rule_type_compat(
            "expect_column_values_to_not_be_null",
            {"column": "birth_date"},
            [_DATE_COL],
        ) is None

    def test_regex_on_text_col_passes(self):
        assert check_rule_type_compat(
            "expect_column_values_to_match_regex",
            {"column": "email"},
            [_TEXT_COL],
        ) is None

    def test_regex_on_date_col_fails(self):
        msg = check_rule_type_compat(
            "expect_column_values_to_match_regex",
            {"column": "birth_date"},
            [_DATE_COL],
        )
        assert msg is not None
        assert "text / varchar" in msg
        assert "birth_date" in msg
        # Date-specific guidance is included for date columns
        assert "expect_column_values_to_be_between" in msg

    def test_regex_on_int_col_fails_without_date_hint(self):
        col = _col("score", "integer")
        msg = check_rule_type_compat(
            "expect_column_values_to_match_regex",
            {"column": "score"},
            [col],
        )
        assert msg is not None
        assert "text / varchar" in msg
        # No date-specific hint for integer columns
        assert "expect_column_values_to_be_between" not in msg

    def test_regex_on_timestamp_col_includes_date_hint(self):
        msg = check_rule_type_compat(
            "expect_column_values_to_match_strftime_format",
            {"column": "created_at"},
            [_TS_COL],
        )
        assert msg is not None
        assert "expect_column_values_to_be_between" in msg

    def test_unknown_column_passes_through(self):
        assert check_rule_type_compat(
            "expect_column_values_to_match_regex",
            {"column": "nonexistent_col"},
            [_TEXT_COL],
        ) is None

    def test_no_column_kwarg_passes_through(self):
        assert check_rule_type_compat(
            "expect_column_values_to_match_regex",
            {},
            [_DATE_COL],
        ) is None

    def test_like_pattern_on_date_col_fails(self):
        msg = check_rule_type_compat(
            "expect_column_values_to_match_like_pattern",
            {"column": "birth_date"},
            [_DATE_COL],
        )
        assert msg is not None

    def test_length_check_on_text_col_passes(self):
        assert check_rule_type_compat(
            "expect_column_value_lengths_to_be_between",
            {"column": "email", "min_value": 5, "max_value": 100},
            [_TEXT_COL],
        ) is None

    def test_length_check_on_int_col_fails(self):
        col = _col("score", "integer")
        msg = check_rule_type_compat(
            "expect_column_value_lengths_to_be_between",
            {"column": "score", "min_value": 1, "max_value": 10},
            [col],
        )
        assert msg is not None

    def test_json_parseable_on_text_col_passes(self):
        col = _col("payload", "text")
        assert check_rule_type_compat(
            "expect_column_values_to_be_json_parseable",
            {"column": "payload"},
            [col],
        ) is None

    def test_empty_column_list_passes_through(self):
        assert check_rule_type_compat(
            "expect_column_values_to_match_regex",
            {"column": "email"},
            [],
        ) is None


# ---------------------------------------------------------------------------
# GeEngine pre-flight check (Option B) — unit-level, no DB required
# ---------------------------------------------------------------------------


def _make_engine() -> GeEngine:
    """Instantiate GeEngine without a real DB connection."""
    return object.__new__(GeEngine)


def _make_rule(rule_id: int, expectation_type: str, kwargs: dict):
    rule = MagicMock()
    rule.id = rule_id
    rule.expectation_type = expectation_type
    rule.kwargs = kwargs
    return rule


class TestGeEnginePreflightCheck:
    def _run_rules_with_columns(self, rules, columns):
        """Call run_rules with mocked GX internals; return list[RunResult]."""
        engine = _make_engine()

        # Mock GX context / datasource / batch chain
        mock_batch = MagicMock()
        mock_asset = MagicMock()
        mock_asset.add_batch_definition_whole_table.return_value.get_batch.return_value = mock_batch
        mock_datasource = MagicMock()
        mock_datasource.add_table_asset.return_value = mock_asset
        engine.datasource = mock_datasource

        # Mock get_pk_columns to return None (no PK, simpler path)
        with patch("app.services.ge_engine.get_pk_columns", return_value=None):
            return engine.run_rules(
                table_name="orders",
                rules=rules,
                session=MagicMock(),
                columns=columns,
            )

    def test_incompatible_rule_becomes_error(self):
        rule = _make_rule(
            rule_id=1,
            expectation_type="expect_column_values_to_match_regex",
            kwargs={"column": "birth_date", "regex": r"\d{4}-\d{2}-\d{2}"},
        )
        columns = [_DATE_COL]
        results = self._run_rules_with_columns([rule], columns)

        assert len(results) == 1
        r = results[0]
        assert r.status == "error"
        assert r.rule_id == 1
        assert "text / varchar" in (r.error_message or "")

    def test_compatible_rule_runs_normally(self):
        rule = _make_rule(
            rule_id=2,
            expectation_type="expect_column_values_to_not_be_null",
            kwargs={"column": "birth_date"},
        )
        columns = [_DATE_COL]

        # Mock _build_expectation and batch.validate to simulate a pass
        engine = _make_engine()
        mock_ge_result = MagicMock()
        mock_ge_result.success = True
        mock_ge_result.result = {"unexpected_count": 0}
        mock_ge_result.exception_info = {}

        mock_batch = MagicMock()
        mock_batch.validate.return_value = mock_ge_result
        mock_asset = MagicMock()
        mock_asset.add_batch_definition_whole_table.return_value.get_batch.return_value = mock_batch
        engine.datasource = MagicMock()
        engine.datasource.add_table_asset.return_value = mock_asset

        with patch("app.services.ge_engine.get_pk_columns", return_value=None):
            results = engine.run_rules(
                table_name="orders",
                rules=[rule],
                session=MagicMock(),
                columns=columns,
            )

        assert len(results) == 1
        assert results[0].status == "pass"

    def test_no_columns_skips_preflight(self):
        """When columns=None, pre-flight is skipped and the rule runs (or errors from GX)."""
        rule = _make_rule(
            rule_id=3,
            expectation_type="expect_column_values_to_match_regex",
            kwargs={"column": "birth_date", "regex": r"\d+"},
        )
        engine = _make_engine()
        mock_ge_result = MagicMock()
        mock_ge_result.success = False
        mock_ge_result.result = {"unexpected_count": 5, "partial_unexpected_list": ["bad"]}
        mock_ge_result.exception_info = {}

        mock_batch = MagicMock()
        mock_batch.validate.return_value = mock_ge_result
        mock_asset = MagicMock()
        mock_asset.add_batch_definition_whole_table.return_value.get_batch.return_value = mock_batch
        engine.datasource = MagicMock()
        engine.datasource.add_table_asset.return_value = mock_asset

        with patch("app.services.ge_engine.get_pk_columns", return_value=None):
            results = engine.run_rules(
                table_name="orders",
                rules=[rule],
                session=MagicMock(),
                columns=None,  # no pre-flight
            )

        # Without pre-flight, GX mock returns fail (not error from type check)
        assert len(results) == 1
        assert results[0].status == "fail"
