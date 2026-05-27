"""Column-type compatibility checks for GE expectations.

String-based GE expectations push a regex or text-casting operator into the
SQL query.  PostgreSQL rejects these at runtime when the column is not a
text / varchar type (error: "operator does not exist: date ~ character varying").
"""

from __future__ import annotations

from app.schemas.tables import ColumnInfo

# GE expectations that only work on text / varchar columns.
STRING_ONLY_EXPECTATIONS: frozenset[str] = frozenset(
    [
        "expect_column_values_to_match_regex",
        "expect_column_values_to_not_match_regex",
        "expect_column_values_to_match_regex_list",
        "expect_column_values_to_not_match_regex_list",
        "expect_column_values_to_match_like_pattern",
        "expect_column_values_to_not_match_like_pattern",
        "expect_column_values_to_match_like_pattern_list",
        "expect_column_values_to_not_match_like_pattern_list",
        "expect_column_value_lengths_to_be_between",
        "expect_column_value_lengths_to_equal",
        "expect_column_values_to_match_strftime_format",
        "expect_column_values_to_be_dateutil_parseable",
        "expect_column_values_to_be_json_parseable",
        "expect_column_values_to_match_json_schema",
    ]
)

# PostgreSQL data_type values (from information_schema) compatible with the
# expectations above.
_TEXT_TYPES: frozenset[str] = frozenset(
    [
        "text",
        "character varying",
        "character",
        "varchar",
        "char",
        "name",
        "bpchar",
    ]
)

_DATE_TYPES: frozenset[str] = frozenset(
    [
        "date",
        "timestamp without time zone",
        "timestamp with time zone",
        "timestamptz",
        "timestamp",
    ]
)

_DATE_SUGGESTION = (
    "For `date` / `timestamp` columns the database already enforces a valid "
    "date format. Use `expect_column_values_to_not_be_null` to check for "
    "missing values, or `expect_column_values_to_be_between` with ISO date "
    "strings (e.g. \"1900-01-01\" / \"2100-12-31\") to validate a date range."
)


def check_rule_type_compat(
    expectation_type: str,
    kwargs: dict,
    columns: list[ColumnInfo],
) -> str | None:
    """Return a human-readable error message if *expectation_type* cannot be
    applied to the column referenced in *kwargs*, given the *columns* schema.
    Returns None when the rule is safe to run.
    """
    if expectation_type not in STRING_ONLY_EXPECTATIONS:
        return None

    col_name: str | None = kwargs.get("column")
    if col_name is None:
        return None  # no single-column kwarg — let GE surface the error

    col_info = next((c for c in columns if c.name == col_name), None)
    if col_info is None:
        return None  # unknown column — let GE surface the "column not found" error

    if col_info.data_type.lower() in _TEXT_TYPES:
        return None  # compatible

    msg = (
        f"`{expectation_type}` only works on text / varchar columns, "
        f"but `{col_name}` has type `{col_info.data_type}`."
    )
    if col_info.data_type.lower() in _DATE_TYPES:
        msg += f" {_DATE_SUGGESTION}"
    return msg
