"""Static validation of LLM prompt files.

Two classes of checks, both without LLM calls:

1. Every `expect_*` name listed in the prompts must exist as a real GE class.
2. Every string-only expectation (only valid on text/varchar columns) must be
   accompanied by a type-compatibility warning in each prompt that lists it,
   so the LLM doesn't apply it to date/timestamp/int columns.
"""

import re
from pathlib import Path

import great_expectations as gx
import pytest

PROMPTS_DIR = Path(__file__).parent.parent / "app" / "prompts"
PROMPT_FILES = [
    PROMPTS_DIR / "rule_from_nl.md",
    PROMPTS_DIR / "rule_from_schema.md",
]

_BACKTICK_PATTERN = re.compile(r"`(expect_[a-z_]+)`")


def _snake_to_camel(name: str) -> str:
    return "".join(word.capitalize() for word in name.split("_"))


def _extract_expectation_names(path: Path) -> list[tuple[str, str]]:
    """Return [(snake_name, source_file), ...] for every `expect_*` in the file."""
    text = path.read_text()
    return [(m.group(1), path.name) for m in _BACKTICK_PATTERN.finditer(text)]


def _all_prompt_expectations() -> list[tuple[str, str]]:
    names = []
    for p in PROMPT_FILES:
        names.extend(_extract_expectation_names(p))
    # deduplicate while preserving origin for parametrize IDs
    seen: set[str] = set()
    unique = []
    for name, src in names:
        if name not in seen:
            seen.add(name)
            unique.append((name, src))
    return unique


# ---------------------------------------------------------------------------
# Expectations that only work on text/varchar columns.
# Applying any of these to a date/timestamp/int/numeric column causes a
# PostgreSQL runtime error ("operator does not exist: date ~ character varying").
# ---------------------------------------------------------------------------
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

# Sentinel phrase that must appear in every prompt which lists string-only
# expectations.  The exact string is also written into both prompt files so
# grep-style searches stay in sync.
_TYPE_COMPAT_SENTINEL = "text / varchar"


# ---------------------------------------------------------------------------
# Test 1 — all listed expectation names must exist in GE
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "snake_name,source_file",
    _all_prompt_expectations(),
    ids=[name for name, _ in _all_prompt_expectations()],
)
def test_expectation_exists_in_ge(snake_name: str, source_file: str) -> None:
    """Each expectation name in the prompt must resolve to a real GE class."""
    camel = _snake_to_camel(snake_name)
    assert hasattr(gx.expectations, camel), (
        f"'{snake_name}' listed in {source_file} does not exist in "
        f"great_expectations.expectations (looked for '{camel}'). "
        f"Either the name is misspelled or GE does not support it."
    )


# ---------------------------------------------------------------------------
# Test 2 — every prompt that lists a string-only expectation must also
#           contain the type-compatibility warning sentinel
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", PROMPT_FILES, ids=[p.name for p in PROMPT_FILES])
def test_prompt_has_type_compat_warning(path: Path) -> None:
    """A prompt that lists any string-only expectation must warn about column types."""
    content = path.read_text()
    listed = {name for name, _ in _extract_expectation_names(path)}
    string_only_listed = listed & STRING_ONLY_EXPECTATIONS
    if not string_only_listed:
        pytest.skip(f"{path.name} lists no string-only expectations — warning not required")
    assert _TYPE_COMPAT_SENTINEL in content, (
        f"{path.name} lists string-only expectations {sorted(string_only_listed)} "
        f"but is missing the type-compatibility warning "
        f"(expected to find '{_TYPE_COMPAT_SENTINEL}'). "
        f"Add a note that these expectations only work on text / varchar columns."
    )


# ---------------------------------------------------------------------------
# Test 3 — every string-only expectation listed in a prompt must appear
#           within a section that contains the type-compat sentinel, ensuring
#           the warning is co-located with the expectation name, not buried
#           elsewhere in the file.
# ---------------------------------------------------------------------------


def _sections(text: str) -> list[str]:
    """Split a Markdown file on top-level bullet list items (lines starting with '  -')."""
    # Split on lines that start a new bullet group (single '  -' prefix or section headers).
    # We use double-newline boundaries to get paragraphs/blocks.
    return re.split(r"\n{2,}", text)


@pytest.mark.parametrize(
    "snake_name,path",
    [
        (name, path)
        for path in PROMPT_FILES
        for name, _ in _extract_expectation_names(path)
        if name in STRING_ONLY_EXPECTATIONS
    ],
    ids=[
        f"{path.name}::{name}"
        for path in PROMPT_FILES
        for name, _ in _extract_expectation_names(path)
        if name in STRING_ONLY_EXPECTATIONS
    ],
)
def test_string_only_expectation_collocated_with_type_warning(
    snake_name: str, path: Path
) -> None:
    """The type-compat sentinel must appear in the same paragraph/block as the expectation."""
    content = path.read_text()
    for block in _sections(content):
        if snake_name in block and _TYPE_COMPAT_SENTINEL in block:
            return  # found — pass
    pytest.fail(
        f"'{snake_name}' appears in {path.name} but the type-compatibility warning "
        f"('{_TYPE_COMPAT_SENTINEL}') is not in the same paragraph/block. "
        f"Move the warning next to the expectation so the LLM sees them together."
    )
