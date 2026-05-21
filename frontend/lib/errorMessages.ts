export interface ErrorMessage {
  title: string;
  possible_causes: string[];
  retry_label?: string;
}

const ERROR_MESSAGES: Record<string, ErrorMessage> = {
  TABLE_NOT_FOUND: {
    title: "Table Not Found",
    possible_causes: [
      "The table name in the URL may be incorrect.",
      "The table may have been deleted from the database.",
    ],
  },
  RULE_NOT_FOUND: {
    title: "Rule Not Found",
    possible_causes: [
      "The rule may have been deleted by another session.",
      "The rule ID in the request is incorrect.",
    ],
    retry_label: "Refresh Rules",
  },
  RUN_NOT_FOUND: {
    title: "Run Not Found",
    possible_causes: [
      "The run ID may be incorrect.",
      "The run record may have been deleted.",
    ],
    retry_label: "Refresh",
  },
  RESULT_NOT_FOUND: {
    title: "Result Not Found",
    possible_causes: [
      "The result record may have been deleted.",
      "The run it belongs to may have been removed.",
    ],
  },
  RESULT_NOT_FAILED: {
    title: "Explanation Not Available",
    possible_causes: [
      "Explanations are only shown for failed checks.",
      "This result may have passed or encountered an error.",
    ],
  },
  INVALID_RULE_IDS: {
    title: "Invalid Rule Selection",
    possible_causes: [
      "One or more selected rules do not belong to this table.",
      "A rule may have been deleted after you loaded the page.",
    ],
    retry_label: "Refresh Rules",
  },
  RUN_STILL_RUNNING: {
    title: "Run In Progress",
    possible_causes: [
      "A previous run for this table has not finished yet.",
      "Wait a moment and try again.",
    ],
    retry_label: "Try Again",
  },
  LLM_TIMEOUT: {
    title: "AI Service Timeout",
    possible_causes: [
      "The Anthropic API may be under high load.",
      "Your network connection may be slow or unstable.",
      "The prompt may be too large for the current timeout.",
    ],
    retry_label: "Retry",
  },
  LLM_OUTPUT_INVALID: {
    title: "AI Response Invalid",
    possible_causes: [
      "The AI returned a response that could not be parsed.",
      "The model may have deviated from the expected output format.",
      "Try rephrasing your request and retry.",
    ],
    retry_label: "Retry",
  },
  LLM_RATE_LIMITED: {
    title: "AI Rate Limit Reached",
    possible_causes: [
      "Too many AI requests have been made in a short period.",
      "Wait 10–30 seconds before retrying.",
    ],
    retry_label: "Retry",
  },
  DB_TIMEOUT: {
    title: "Database Timeout",
    possible_causes: [
      "The database is taking longer than expected to respond.",
      "The table you are querying may be very large.",
      "The Supabase connection pool may be exhausted.",
    ],
    retry_label: "Retry",
  },
  GE_EXECUTION_FAILED: {
    title: "Rule Execution Failed",
    possible_causes: [
      "One or more rules may reference a column that no longer exists.",
      "A rule's kwargs may contain an invalid value for the expectation type.",
      "The Great Expectations engine encountered an unexpected error.",
    ],
    retry_label: "Retry Run",
  },
  CACHE_CORRUPTED: {
    title: "Cached Response Corrupted",
    possible_causes: [
      "A previously cached AI response could not be parsed.",
      "The cache entry was automatically discarded — retrying will generate a fresh response.",
    ],
    retry_label: "Retry",
  },
  DATABASE_UNAVAILABLE: {
    title: "Database Unavailable",
    possible_causes: [
      "The database server may be temporarily unavailable.",
      "Your network connection may be unstable.",
      "The backend service may not be running.",
    ],
    retry_label: "Retry",
  },
  INTERNAL_ERROR: {
    title: "Unexpected Error",
    possible_causes: [
      "The backend service encountered an unexpected error.",
      "Try refreshing the page or restarting the backend.",
    ],
    retry_label: "Retry",
  },
};

const DEFAULT_ERROR_MESSAGE: ErrorMessage = {
  title: "Something Went Wrong",
  possible_causes: ["An unexpected error occurred. Please try again."],
  retry_label: "Retry",
};

export function getErrorMessage(code: string): ErrorMessage {
  if (process.env.NODE_ENV === "development" && !(code in ERROR_MESSAGES)) {
    console.warn(`[errorMessages] Unknown error code: "${code}". Add it to lib/errorMessages.ts.`);
  }
  return ERROR_MESSAGES[code] ?? DEFAULT_ERROR_MESSAGE;
}
