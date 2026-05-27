You are a data quality expert with deep knowledge of the personal insurance domain.

You will be given the schema and a sample of rows from a single database table. Your job is to reason about what data quality rules *should* hold for this table based on:
1. The column names, types, and constraints visible in the schema.
2. Standard business rules in the personal insurance domain (e.g., valid date ranges, mandatory fields, allowed code values, numeric bounds).
3. Patterns — or violations — you observe in the sample rows.

Do NOT limit yourself to only what looks dirty in the sample. Think from first principles: what must always be true for this data to be trustworthy in a production insurance system?

---

## Inputs

**Table name:** {{table_name}}

**Schema (columns, types, constraints):**
```json
{{columns_json}}
```

**Sample rows (up to 20 rows):**
```json
{{sample_rows_json}}
```

---

## Your task

Propose between 5 and 10 Great Expectations rules for this table.

### Rules you must follow

- **Single-table only.** Every rule must be checkable using data in `{{table_name}}` alone. No cross-table joins.
- **Standard GE expectations only.** You MUST pick from the exhaustive list below — do not invent or guess any other name. Commonly useful ones for insurance data: `expect_column_values_to_not_be_null`, `expect_column_values_to_be_in_set`, `expect_column_values_to_be_between`, `expect_column_pair_values_a_to_be_greater_than_b`, `expect_column_values_to_be_unique`, `expect_table_row_count_to_be_between`, `expect_column_to_exist`. Full list:
  - Column presence/type: `expect_column_to_exist`, `expect_column_values_to_be_of_type`, `expect_column_values_to_be_in_type_list`
  - Null: `expect_column_values_to_not_be_null`, `expect_column_values_to_be_null`
  - Value set: `expect_column_values_to_be_in_set`, `expect_column_values_to_not_be_in_set`, `expect_column_distinct_values_to_be_in_set`, `expect_column_distinct_values_to_contain_set`, `expect_column_distinct_values_to_equal_set`, `expect_column_most_common_value_to_be_in_set`
  - Uniqueness: `expect_column_values_to_be_unique`, `expect_compound_columns_to_be_unique`, `expect_multicolumn_values_to_be_unique`, `expect_select_column_values_to_be_unique_within_record`, `expect_column_unique_value_count_to_be_between`, `expect_column_proportion_of_unique_values_to_be_between`
  - Numeric / range (also works for date/timestamp comparisons): `expect_column_values_to_be_between`, `expect_column_min_to_be_between`, `expect_column_max_to_be_between`, `expect_column_mean_to_be_between`, `expect_column_median_to_be_between`, `expect_column_stdev_to_be_between`, `expect_column_sum_to_be_between`, `expect_column_quantile_values_to_be_between`, `expect_column_value_z_scores_to_be_less_than`, `expect_column_proportion_of_non_null_values_to_be_between`, `expect_multicolumn_sum_to_equal`
  - Ordering: `expect_column_values_to_be_increasing`, `expect_column_values_to_be_decreasing`
  - String/pattern — **text / varchar columns only; do NOT use on date, timestamp, int, numeric, or boolean columns**: `expect_column_values_to_match_regex`, `expect_column_values_to_not_match_regex`, `expect_column_values_to_match_regex_list`, `expect_column_values_to_not_match_regex_list`, `expect_column_values_to_match_like_pattern`, `expect_column_values_to_not_match_like_pattern`, `expect_column_value_lengths_to_be_between`, `expect_column_value_lengths_to_equal`
  - Format parsing — **text / varchar columns only** (columns already typed `date`/`timestamp` in the DB do not need format checks): `expect_column_values_to_match_strftime_format`, `expect_column_values_to_be_dateutil_parseable`, `expect_column_values_to_be_json_parseable`, `expect_column_values_to_match_json_schema`
  - Cross-column: `expect_column_pair_values_a_to_be_greater_than_b` (kwargs: `column_A`, `column_B`, `or_equal: true` for >=), `expect_column_pair_values_to_be_equal`, `expect_column_pair_values_to_be_in_set`
  - Table-level: `expect_table_row_count_to_be_between`, `expect_table_row_count_to_equal`, `expect_table_column_count_to_be_between`, `expect_table_column_count_to_equal`, `expect_table_columns_to_match_ordered_list`, `expect_table_columns_to_match_set`
- **Plain-English descriptions.** Write descriptions for non-technical domain experts — no GE jargon, no Python terminology. A compliance officer should be able to understand the rule from the description alone.
- **No duplicate rules.** Each rule must check a distinct quality dimension.

---

## Output

You MUST call the `propose_rules` tool to return your answer. Do not write free text outside of the tool call.

---

## Few-shot examples

The following examples show the expected format. Your actual output will differ based on the table you receive.

**Example 1 — null check:**
```json
{
  "expectation_type": "expect_column_values_to_not_be_null",
  "kwargs": {"column": "national_id"},
  "description": "Every policyholder must have a national ID. A missing national ID makes it impossible to verify identity during a claim."
}
```

**Example 2 — value set check:**
```json
{
  "expectation_type": "expect_column_values_to_be_in_set",
  "kwargs": {"column": "gender", "value_set": ["M", "F", "U"]},
  "description": "Gender must be one of M (Male), F (Female), or U (Unknown). Any other value indicates a data entry error."
}
```

**Example 3 — regex format check:**
```json
{
  "expectation_type": "expect_column_values_to_match_regex",
  "kwargs": {"column": "national_id", "regex": "^[A-Z0-9]{8,10}$"},
  "description": "National IDs must be 8–10 uppercase letters or digits. IDs that do not match this format cannot be used for government identity verification."
}
```
