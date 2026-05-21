"""Centralised error raising helpers (D#31).

All API handlers should call raise_error() instead of raising HTTPException
directly.  This keeps the code → (user_message, http_status) mapping in one
place so frontend and backend stay in sync.
"""

from fastapi import HTTPException

# Maps error code → (http_status, user_message)
CODE_MAP: dict[str, tuple[int, str]] = {
    "TABLE_NOT_FOUND": (404, "Table not found."),
    "RULE_NOT_FOUND": (404, "Rule not found."),
    "RUN_NOT_FOUND": (404, "Run not found."),
    "RESULT_NOT_FOUND": (404, "Result not found."),
    "RESULT_NOT_FAILED": (400, "Explanations are only available for failed results."),
    "INVALID_RULE_IDS": (400, "Some rule IDs don't belong to this table."),
    "RUN_STILL_RUNNING": (409, "This run is still in progress."),
    "LLM_TIMEOUT": (504, "The AI service is temporarily unresponsive."),
    "LLM_OUTPUT_INVALID": (502, "The AI returned an invalid response."),
    "LLM_RATE_LIMITED": (429, "Too many AI requests. Please wait a moment."),
    "DB_TIMEOUT": (504, "The database is taking too long to respond."),
    "GE_EXECUTION_FAILED": (500, "Rule execution failed. Please check the rule configuration."),
    "CACHE_CORRUPTED": (500, "Cached response is corrupted and was discarded."),
    "DATABASE_UNAVAILABLE": (503, "Unable to connect to the database temporarily."),
}


def raise_error(code: str, technical_detail: str = "") -> None:
    """Raise an HTTPException using the centralised code map.

    The *code* string is passed as exc.detail so the global exception handler
    in main.py can reconstruct the full error envelope.
    """
    if code not in CODE_MAP:
        raise HTTPException(status_code=500, detail=code)
    http_status, _ = CODE_MAP[code]
    raise HTTPException(status_code=http_status, detail=code)
