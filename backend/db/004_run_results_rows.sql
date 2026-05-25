-- Add unexpected_rows (complete violating row data) and truncated flag to dq.run_results.
-- Part of D#33-D#37: violating rows full display with cap 1000.

ALTER TABLE dq.run_results
    ADD COLUMN IF NOT EXISTS unexpected_rows JSONB,
    ADD COLUMN IF NOT EXISTS truncated BOOLEAN NOT NULL DEFAULT FALSE;

-- No GIN index on unexpected_rows: we only do full-column reads, never per-key queries.
