-- Add three-state status column to dq.run_results (D#18).
-- DEFAULT 'pass' ensures existing rows are valid after the migration;
-- all new rows will have status set explicitly by runs_store.write_result.

ALTER TABLE dq.run_results
    ADD COLUMN IF NOT EXISTS status VARCHAR(10) NOT NULL DEFAULT 'pass';
