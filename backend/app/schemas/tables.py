"""Pydantic models for the /tables endpoints."""

from typing import Any

from pydantic import BaseModel


class ColumnInfo(BaseModel):
    name: str
    data_type: str
    is_nullable: bool
    column_default: str | None


class TableInfo(BaseModel):
    name: str
    row_count: int
    column_count: int


class TableDetail(BaseModel):
    name: str
    row_count: int
    columns: list[ColumnInfo]


class SampleResponse(BaseModel):
    rows: list[dict[str, Any]]
    limit: int
