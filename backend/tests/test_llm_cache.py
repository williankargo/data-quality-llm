"""Integration tests for llm_cache.py (D#24).

All tests use the db_session fixture (transaction-rollback isolation) so no
rows persist after the test suite completes.
"""

from sqlalchemy import text

from app.services.llm_cache import get_cached, make_cache_key, set_cached


class TestLlmCacheMiss:
    def test_returns_none_for_unknown_key(self, db_session):
        key = make_cache_key("test_prompt", "v1", foo="bar_unique_12345")
        assert get_cached(db_session, key) is None


class TestLlmCacheHit:
    def test_returns_stored_response(self, db_session):
        key = make_cache_key("rule_from_schema", "v1", table_name="orders_test")
        payload = {
            "rules": [
                {
                    "expectation_type": "expect_column_values_to_not_be_null",
                    "kwargs": {"column": "id"},
                    "description": "id must not be null",
                }
            ]
        }
        set_cached(db_session, key, "rule_from_schema", payload)

        result = get_cached(db_session, key)
        assert result == payload

    def test_increments_hit_count_on_each_get(self, db_session):
        key = make_cache_key("rule_from_nl", "v1", description="test rule 42")
        set_cached(db_session, key, "rule_from_nl", {"type": "rule", "rule": {}})

        get_cached(db_session, key)
        row = db_session.execute(
            text("SELECT hit_count FROM dq.llm_cache WHERE cache_key = :k"),
            {"k": key},
        ).fetchone()
        assert row.hit_count == 1

        get_cached(db_session, key)
        row = db_session.execute(
            text("SELECT hit_count FROM dq.llm_cache WHERE cache_key = :k"),
            {"k": key},
        ).fetchone()
        assert row.hit_count == 2

    def test_upsert_resets_hit_count(self, db_session):
        key = make_cache_key("rule_from_schema", "v1", table_name="upsert_test")
        payload_v1 = {"rules": []}
        payload_v2 = {"rules": [{"expectation_type": "expect_table_row_count_to_be_between"}]}

        set_cached(db_session, key, "rule_from_schema", payload_v1)
        get_cached(db_session, key)  # hit_count → 1

        # Upserting should reset hit_count to 0 and store new payload
        set_cached(db_session, key, "rule_from_schema", payload_v2)
        row = db_session.execute(
            text("SELECT hit_count FROM dq.llm_cache WHERE cache_key = :k"),
            {"k": key},
        ).fetchone()
        assert row.hit_count == 0

        result = get_cached(db_session, key)
        assert result == payload_v2


class TestLlmCacheExpire:
    def test_expired_entry_returns_none(self, db_session):
        """An entry whose expires_at is in the past is not returned."""
        key = make_cache_key("rule_from_schema", "v1", table_name="expired_cache_test")
        db_session.execute(
            text(
                """
                INSERT INTO dq.llm_cache (cache_key, prompt_name, response, expires_at)
                VALUES (:k, 'rule_from_schema', '{"rules": []}',
                        NOW() - INTERVAL '1 hour')
                """
            ),
            {"k": key},
        )
        db_session.commit()

        assert get_cached(db_session, key) is None
