"""Database connectivity and table-inspection helpers.

This module owns:
- The SQLAlchemy engine and session factory.
- `get_db()` — a FastAPI dependency that yields a session per request.
- Helper functions that query information_schema and pg_stat_user_tables
  to support the /tables endpoints without touching application-level tables.
"""

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.schemas.tables import ColumnInfo, TableInfo

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine)


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Context-manager that opens a session and ensures it is closed."""
    session: Session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: yields a DB session, closes it after the request."""
    with get_session() as session:
        yield session


def list_public_tables(session: Session) -> list[TableInfo]:
    """Return metadata for every base table in the public schema.

    Row count comes from pg_stat_user_tables.n_live_tup which is an
    approximate value maintained by the autovacuum daemon — O(1) cost
    and good enough for display purposes.
    """
    sql = text(
        """
        SELECT
            t.table_name,
            COALESCE(s.n_live_tup, 0)                        AS row_count,
            (
                SELECT COUNT(*)
                FROM information_schema.columns c
                WHERE c.table_schema = 'public'
                  AND c.table_name  = t.table_name
            )::INTEGER                                        AS column_count
        FROM information_schema.tables t
        LEFT JOIN pg_stat_user_tables s
               ON s.schemaname = 'public'
              AND s.relname    = t.table_name
        WHERE t.table_schema = 'public'
          AND t.table_type   = 'BASE TABLE'
        ORDER BY t.table_name
        """
    )
    rows = session.execute(sql).fetchall()
    return [
        TableInfo(
            name=row.table_name,
            row_count=int(row.row_count),
            column_count=int(row.column_count),
        )
        for row in rows
    ]


def get_table_columns(session: Session, name: str) -> list[ColumnInfo]:
    """Return ordered column metadata for a single public table."""
    sql = text(
        """
        SELECT
            column_name,
            data_type,
            is_nullable,
            column_default
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name   = :name
        ORDER BY ordinal_position
        """
    )
    rows = session.execute(sql, {"name": name}).fetchall()
    return [
        ColumnInfo(
            name=row.column_name,
            data_type=row.data_type,
            is_nullable=(row.is_nullable == "YES"),
            column_default=row.column_default,
        )
        for row in rows
    ]


def sample_table(session: Session, name: str, limit: int = 50) -> list[dict]:
    """Return up to *limit* rows from a public table as plain dicts.

    The table name is validated against the list returned by
    list_public_tables() before being interpolated into SQL, preventing
    SQL injection via the path parameter.
    """
    # Whitelist check: only proceed if the name is a known public table.
    known = {t.name for t in list_public_tables(session)}
    if name not in known:
        return []

    sql = text(f'SELECT * FROM public."{name}" LIMIT :limit')
    rows = session.execute(sql, {"limit": limit}).fetchall()
    return [dict(row._mapping) for row in rows]
