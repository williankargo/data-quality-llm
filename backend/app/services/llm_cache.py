"""DB-backed LLM response cache (D#24).

Cache key = sha256 of (prompt_name, prompt_version, sorted payload JSON).
Bumping PROMPT_VERSION_* in ai_generator.py automatically invalidates old entries
for that prompt path.
"""

import hashlib
import json

from sqlalchemy import text
from sqlalchemy.orm import Session


def make_cache_key(prompt_name: str, prompt_version: str, **payload) -> str:
    canonical = json.dumps(
        {"_p": prompt_name, "_v": prompt_version, **payload},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def get_cached(session: Session, cache_key: str) -> dict | None:
    """Return the cached response dict if it exists and has not expired.

    Increments hit_count on a cache hit.
    """
    row = session.execute(
        text(
            "SELECT response FROM dq.llm_cache"
            " WHERE cache_key = :k AND expires_at > NOW()"
        ),
        {"k": cache_key},
    ).fetchone()
    if row is None:
        return None
    session.execute(
        text(
            "UPDATE dq.llm_cache SET hit_count = hit_count + 1 WHERE cache_key = :k"
        ),
        {"k": cache_key},
    )
    session.commit()
    return row.response  # psycopg3 returns JSONB as a Python dict


def set_cached(
    session: Session,
    cache_key: str,
    prompt_name: str,
    response: dict,
    ttl_hours: int = 24,
) -> None:
    """Upsert a cache entry. Resets hit_count to 0 on conflict."""
    session.execute(
        text(
            """
            INSERT INTO dq.llm_cache (cache_key, prompt_name, response, expires_at)
            VALUES (:k, :pname, CAST(:resp AS JSONB),
                    NOW() + (:ttl * INTERVAL '1 hour'))
            ON CONFLICT (cache_key) DO UPDATE
                SET response   = EXCLUDED.response,
                    expires_at = EXCLUDED.expires_at,
                    hit_count  = 0
            """
        ),
        {
            "k": cache_key,
            "pname": prompt_name,
            "resp": json.dumps(response),
            "ttl": ttl_hours,
        },
    )
    session.commit()
