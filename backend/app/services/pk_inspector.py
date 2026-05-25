"""Detect primary key columns for a PostgreSQL table (D#36).

Uses pg_index + pg_attribute system catalogs, which are authoritative for
both single-column and composite PKs. Returns None when no PK exists so
callers can fall back to the no-PK display path.
"""

from sqlalchemy import text
from sqlalchemy.orm import Session


def get_pk_columns(session: Session, table_name: str, schema: str = "public") -> list[str] | None:
    """Return PK column names for *table_name* in *schema*, ordered by key position.

    Returns None if the table has no primary key.
    Handles single-column and composite PKs.
    """
    sql = text(
        """
        SELECT a.attname AS column_name
        FROM pg_index i
        JOIN pg_attribute a
          ON a.attrelid = i.indrelid
         AND a.attnum   = ANY(i.indkey)
        WHERE i.indrelid = (:schema || '.' || :table)::regclass
          AND i.indisprimary
        ORDER BY array_position(i.indkey, a.attnum)
        """
    )
    rows = session.execute(sql, {"schema": schema, "table": table_name}).all()
    cols = [r.column_name for r in rows]
    return cols if cols else None
