"""Pydantic models for run execution and result retrieval."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

ResultStatus = Literal["pass", "fail", "error"]


class RunResult(BaseModel):
    id: int
    rule_id: int | None
    expectation_type: str
    status: ResultStatus
    success: bool
    unexpected_count: int | None
    unexpected_sample: list[Any] | None
    observed_value: Any | None
    error_message: str | None


class RunSummary(BaseModel):
    id: int
    table_name: str
    status: Literal["success", "failed"]
    started_at: datetime
    completed_at: datetime | None
    error_message: str | None
    pass_count: int
    fail_count: int
    error_count: int


class RunDetail(RunSummary):
    results: list[RunResult]


class CreateRunRequest(BaseModel):
    table_name: str
