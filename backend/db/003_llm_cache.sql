-- LLM response cache: avoids duplicate LLM calls for identical prompts (D#24).
-- Run this in the Supabase SQL Editor after 002_run_results_status.sql.

CREATE TABLE IF NOT EXISTS dq.llm_cache (
  cache_key    VARCHAR(64)   PRIMARY KEY,
  prompt_name  VARCHAR(50)   NOT NULL,
  response     JSONB         NOT NULL,
  created_at   TIMESTAMP     NOT NULL DEFAULT NOW(),
  expires_at   TIMESTAMP     NOT NULL,
  hit_count    INTEGER       NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS llm_cache_expires_idx ON dq.llm_cache (expires_at);
