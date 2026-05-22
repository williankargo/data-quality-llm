"""HTTP handlers for the /tables resource.

Endpoints:
  GET /tables             — list all public tables with metadata
  GET /tables/{name}      — table detail: schema + row count
  GET /tables/{name}/sample — first N rows for AI context
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.errors import raise_error
from app.services.db import get_db, get_table_columns, list_public_tables, sample_table
from app.schemas.tables import SampleResponse, TableDetail, TableInfo

router = APIRouter(prefix="/tables", tags=["tables"])


@router.get("", response_model=list[TableInfo])
def get_tables(db: Session = Depends(get_db)) -> list[TableInfo]:
    """Return metadata for all base tables in the public schema."""
    return list_public_tables(db)


@router.get("/{name}", response_model=TableDetail)
def get_table(name: str, db: Session = Depends(get_db)) -> TableDetail:
    """Return column schema and row count for a single table.

    Raises HTTP 404 with code TABLE_NOT_FOUND when the table does not exist.
    """
    # Use list_public_tables to find the row_count for this table, and also
    # as an existence check — avoids a separate COUNT(*) query.
    tables = list_public_tables(db)
    matched = next((t for t in tables if t.name == name), None)
    if matched is None:
        raise_error("TABLE_NOT_FOUND")

    columns = get_table_columns(db, name)
    return TableDetail(
        name=matched.name,
        row_count=matched.row_count,
        columns=columns,
    )


@router.get("/{name}/sample", response_model=SampleResponse)
def get_table_sample(
    name: str, limit: int = 50, db: Session = Depends(get_db)
) -> SampleResponse:
    """Return a sample of rows from the table for use as LLM context.

    Raises HTTP 404 with code TABLE_NOT_FOUND when the table does not exist.
    The default limit is 50; callers may override via ?limit=N.
    """
    # sample_table returns [] for unknown table names (whitelist logic in db.py).
    # Cross-check with list_public_tables to distinguish "table not found" from
    # "table exists but is empty".
    tables = list_public_tables(db)
    if not any(t.name == name for t in tables):
        raise_error("TABLE_NOT_FOUND")

    rows = sample_table(db, name, limit)
    return SampleResponse(rows=rows, limit=limit)
