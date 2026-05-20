"""CRUD helpers for dq.rules.

All queries use SQLAlchemy text() — no ORM declarative model.
The already_saved duplicate check (D#22) uses canonical JSON with sort_keys=True
so that key ordering in kwargs JSONB does not affect comparison.
"""

import json

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.rules import GeRule, RuleDraft, RuleRecord


def _row_to_record(row) -> RuleRecord:
    return RuleRecord(
        id=row.id,
        table_name=row.table_name,
        expectation_type=row.expectation_type,
        kwargs=row.kwargs,
        description=row.description,
        source=row.source,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def list_rules(session: Session, table_name: str | None = None) -> list[RuleRecord]:
    if table_name is not None:
        sql = text(
            "SELECT * FROM dq.rules WHERE table_name = :table_name ORDER BY id"
        )
        rows = session.execute(sql, {"table_name": table_name}).fetchall()
    else:
        sql = text("SELECT * FROM dq.rules ORDER BY id")
        rows = session.execute(sql).fetchall()
    return [_row_to_record(r) for r in rows]


def get_rule(session: Session, rule_id: int) -> RuleRecord | None:
    sql = text("SELECT * FROM dq.rules WHERE id = :id")
    row = session.execute(sql, {"id": rule_id}).fetchone()
    return _row_to_record(row) if row else None


def create_rule(
    session: Session, table_name: str, source: str, rule: GeRule
) -> RuleRecord:
    sql = text(
        """
        INSERT INTO dq.rules (table_name, expectation_type, kwargs, description, source)
        VALUES (:table_name, :expectation_type, :kwargs, :description, :source)
        RETURNING *
        """
    )
    row = session.execute(
        sql,
        {
            "table_name": table_name,
            "expectation_type": rule.expectation_type,
            "kwargs": json.dumps(rule.kwargs),
            "description": rule.description,
            "source": source,
        },
    ).fetchone()
    session.commit()
    return _row_to_record(row)


def update_rule(session: Session, rule_id: int, rule: GeRule) -> RuleRecord:
    sql = text(
        """
        UPDATE dq.rules
        SET expectation_type = :expectation_type,
            kwargs            = :kwargs,
            description       = :description,
            updated_at        = NOW()
        WHERE id = :id
        RETURNING *
        """
    )
    row = session.execute(
        sql,
        {
            "id": rule_id,
            "expectation_type": rule.expectation_type,
            "kwargs": json.dumps(rule.kwargs),
            "description": rule.description,
        },
    ).fetchone()
    session.commit()
    return _row_to_record(row)


def delete_rule(session: Session, rule_id: int) -> bool:
    sql = text("DELETE FROM dq.rules WHERE id = :id")
    result = session.execute(sql, {"id": rule_id})
    session.commit()
    return result.rowcount > 0


def mark_drafts_already_saved(
    session: Session, table_name: str, drafts: list[GeRule]
) -> list[RuleDraft]:
    """Tag each draft with already_saved=True if an identical rule exists in dq.rules (D#22).

    Identity is determined by (expectation_type, canonical JSON of kwargs).
    """
    existing = list_rules(session, table_name=table_name)
    saved_fingerprints = {
        (r.expectation_type, json.dumps(r.kwargs, sort_keys=True)) for r in existing
    }

    result: list[RuleDraft] = []
    for draft in drafts:
        fingerprint = (
            draft.expectation_type,
            json.dumps(draft.kwargs, sort_keys=True),
        )
        result.append(
            RuleDraft(
                expectation_type=draft.expectation_type,
                kwargs=draft.kwargs,
                description=draft.description,
                already_saved=fingerprint in saved_fingerprints,
            )
        )
    return result
