export interface ColumnInfo {
  name: string;
  data_type: string;
  is_nullable: boolean;
  column_default: string | null;
}

export interface TableInfo {
  name: string;
  row_count: number;
  column_count: number;
}

export interface TableDetail {
  name: string;
  row_count: number;
  columns: ColumnInfo[];
}

export interface SampleResponse {
  rows: Record<string, unknown>[];
  limit: number;
}

export interface ApiErrorData {
  code: string;
  user_message: string;
  technical_detail: string;
}

// ─── Rule types ─────────────────────────────────────────────────────────────

export type RuleSource = "ai_schema" | "ai_nl" | "user";

export interface GeRule {
  expectation_type: string;
  kwargs: Record<string, unknown>;
  description: string;
}

export interface RuleRecord extends GeRule {
  id: number;
  table_name: string;
  source: RuleSource;
  created_at: string;
  updated_at: string;
}

export interface RuleDraft extends GeRule {
  already_saved: boolean;
}

/** Frontend-only: draft with source tracked for save request. */
export interface FrontendDraft extends RuleDraft {
  source: RuleSource;
}

export interface SuggestResponse {
  drafts: RuleDraft[];
}

export interface NlRuleSuccess {
  type: "rule";
  rule: GeRule;
}

export interface NlRuleClarification {
  type: "clarification";
  question: string;
}

export type NlRuleResponse = NlRuleSuccess | NlRuleClarification;

export interface CreateRuleRequest extends GeRule {
  table_name: string;
  source: RuleSource;
}

// ─── Run / result types ──────────────────────────────────────────────────────

export type ResultStatus = "pass" | "fail" | "error";

export interface RunResult {
  id: number;
  rule_id: number | null;
  expectation_type: string;
  status: ResultStatus;
  success: boolean;
  unexpected_count: number | null;
  unexpected_sample: unknown[] | null;
  observed_value: unknown | null;
  error_message: string | null;
}

export interface RunSummary {
  id: number;
  table_name: string;
  status: "success" | "failed";
  started_at: string;
  completed_at: string | null;
  error_message: string | null;
  pass_count: number;
  fail_count: number;
  error_count: number;
}

export interface RunDetail extends RunSummary {
  results: RunResult[];
}
