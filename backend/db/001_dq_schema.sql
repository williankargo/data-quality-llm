-- DQ system tables: stores rules, run metadata, and per-expectation results.
-- Run this after schema.sql and seed.sql.

CREATE SCHEMA IF NOT EXISTS dq;

CREATE TABLE dq.rules (
  id SERIAL PRIMARY KEY,
  table_name VARCHAR(100) NOT NULL,
  expectation_type VARCHAR(100) NOT NULL,
  kwargs JSONB NOT NULL,
  description TEXT,
  source VARCHAR(20) NOT NULL,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE dq.runs (
  id SERIAL PRIMARY KEY,
  table_name VARCHAR(100) NOT NULL,
  status VARCHAR(20) NOT NULL,
  started_at TIMESTAMP DEFAULT NOW(),
  completed_at TIMESTAMP,
  error_message TEXT
);

CREATE TABLE dq.run_results (
  id SERIAL PRIMARY KEY,
  run_id INTEGER REFERENCES dq.runs(id) ON DELETE CASCADE,
  rule_id INTEGER REFERENCES dq.rules(id) ON DELETE SET NULL,
  expectation_type VARCHAR(100) NOT NULL,
  success BOOLEAN NOT NULL,
  unexpected_count INTEGER,
  unexpected_sample JSONB,
  observed_value JSONB,
  raw_result JSONB
);
