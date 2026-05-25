-- ============================================================
-- 005_dirty_data.sql  — DQ edge-case test fixtures
-- Purpose : Inject intentionally dirty rows so Phase 7 features
--           (violating-row table, CSV download, column highlight)
--           can be exercised on the web UI without needing a
--           separate test database.
-- Run in  : Supabase SQL Editor (same project as seed.sql)
-- Safe to re-run? NO — unique constraints will error on duplicate.
--           Wrap the whole block in a transaction or truncate first.
-- ============================================================

BEGIN;

-- ============================================================
-- A. DIRTY POLICYHOLDERS
-- Violations: national_id format, gender set, birth_date range
-- GE rules that will catch these:
--   • expect_column_values_to_match_regex  (national_id → ^[A-Z]\d{9}$)
--   • expect_column_values_to_be_in_set    (gender → ['M','F'])
--   • expect_column_values_to_be_between   (birth_date → max=today)
--   • expect_column_values_to_not_be_null  (email)
-- ============================================================

INSERT INTO public.policyholders
  (national_id, full_name, birth_date, gender, email, phone, created_at)
VALUES
  -- (A1) national_id starts with lowercase letter → regex fails
  ('a987654321', 'Alex Bad-ID One',     '1985-03-10', 'M', 'alex.bad1@dqtest.com',  '0900-001-001', '2024-01-01 00:00:00'),

  -- (A2) national_id is all digits, no leading letter → regex fails
  ('1234567891', 'Bob Bad-ID Two',      '1990-07-22', 'F', 'bob.bad2@dqtest.com',   '0900-001-002', '2024-01-01 00:00:00'),

  -- (A3) national_id has two leading letters → regex fails
  ('EE12345678', 'Clara Bad-ID Three',  '1978-11-05', 'F', 'clara.bad3@dqtest.com', '0900-001-003', '2024-01-01 00:00:00'),

  -- (B1) gender = 'X' (not in {'M','F'}) → set membership fails
  ('H111111111', 'Dan Wrong-Gender',    '1975-05-15', 'X', 'dan.bad4@dqtest.com',   '0900-001-004', '2024-01-01 00:00:00'),

  -- (B2) gender = 'U' (unknown) → set membership fails
  ('I222222222', 'Eve Wrong-Gender',    '1983-09-20', 'U', 'eve.bad5@dqtest.com',   '0900-001-005', '2024-01-01 00:00:00'),

  -- (C1) birth_date in the future → between(max=today) fails
  ('J333333333', 'Frank Future-Birth',  '2035-06-01', 'M', 'frank.bad6@dqtest.com', '0900-001-006', '2024-01-01 00:00:00'),

  -- (D1) email is NULL → not_be_null check fails
  ('K444444444', 'Grace Null-Email',    '1980-09-30', 'F', NULL,                    '0900-001-007', '2024-01-01 00:00:00'),

  -- (A4+B3) double violation: bad national_id AND wrong gender
  ('z555555555', 'Hank Double-Fail',    '1992-04-18', 'Z', 'hank.bad8@dqtest.com',  '0900-001-008', '2024-01-01 00:00:00');

-- ============================================================
-- B. DIRTY POLICIES
-- Violations: premium_monthly sign, coverage_amount sign,
--             product_type set, status set, date ordering
-- GE rules that will catch these:
--   • expect_column_values_to_be_between   (premium_monthly → min=0.01)
--   • expect_column_values_to_be_between   (coverage_amount → min=1)
--   • expect_column_values_to_be_in_set    (product_type → ['life','health','accident'])
--   • expect_column_values_to_be_in_set    (status → ['active','lapsed','terminated'])
--   • expect_column_pair_values_A_to_be_greater_than_B (expiry_date > effective_date)
-- ============================================================

INSERT INTO public.policies
  (policy_number, holder_id, product_type, coverage_amount, premium_monthly,
   effective_date, expiry_date, status, created_at)
VALUES
  -- (E1) premium_monthly = -100 (negative) → between(min=0.01) fails
  ('POL-DIRTY-001', 1,  'life',      500000.00,   -100.00, '2024-01-01', '2029-01-01', 'active',    '2024-01-01 00:00:00'),

  -- (E2) premium_monthly = -50 (negative) → between(min=0.01) fails
  ('POL-DIRTY-002', 2,  'health',    200000.00,    -50.00, '2024-01-01', '2027-01-01', 'active',    '2024-01-01 00:00:00'),

  -- (E3) premium_monthly = 0 (zero) → between(min=0.01) fails
  ('POL-DIRTY-003', 3,  'accident',  300000.00,      0.00, '2024-01-01', '2027-01-01', 'active',    '2024-01-01 00:00:00'),

  -- (F1) coverage_amount = 0 (zero) → between(min=1) fails
  ('POL-DIRTY-004', 4,  'life',           0.00,    800.00, '2024-01-01', '2027-01-01', 'active',    '2024-01-01 00:00:00'),

  -- (F2) coverage_amount = -500000 (negative) → between(min=1) fails
  ('POL-DIRTY-005', 5,  'health',    -500000.00,    640.00, '2024-01-01', '2027-01-01', 'active',   '2024-01-01 00:00:00'),

  -- (G1) product_type = 'car' (invalid category) → set membership fails
  ('POL-DIRTY-006', 6,  'car',        300000.00,    600.00, '2024-01-01', '2027-01-01', 'active',   '2024-01-01 00:00:00'),

  -- (G2) product_type = 'travel' (invalid category) → set membership fails
  ('POL-DIRTY-007', 7,  'travel',     150000.00,    400.00, '2024-01-01', '2027-01-01', 'active',   '2024-01-01 00:00:00'),

  -- (H1) status = 'cancelled' (not in valid set) → set membership fails
  ('POL-DIRTY-008', 8,  'life',       400000.00,    780.00, '2024-01-01', '2027-01-01', 'cancelled','2024-01-01 00:00:00'),

  -- (H2) status = 'pending' (not in valid set) → set membership fails
  ('POL-DIRTY-009', 9,  'health',     250000.00,    520.00, '2024-01-01', '2027-01-01', 'pending',  '2024-01-01 00:00:00'),

  -- (I1) expiry_date < effective_date (expired before it starts) → pair comparison fails
  ('POL-DIRTY-010', 10, 'accident',   200000.00,    420.00, '2024-06-01', '2023-01-01', 'active',   '2024-01-01 00:00:00'),

  -- (I2) expiry_date = effective_date (same day, zero-length policy) → strict > fails
  ('POL-DIRTY-011', 11, 'life',       600000.00,   1400.00, '2024-03-15', '2024-03-15', 'active',   '2024-01-01 00:00:00'),

  -- (E+G) double: negative premium AND invalid product type
  ('POL-DIRTY-012', 12, 'crypto',     100000.00,  -9999.00, '2024-01-01', '2027-01-01', 'active',   '2024-01-01 00:00:00');

-- ============================================================
-- C. DIRTY CLAIMS
-- Violations: claim vs coverage, date ordering,
--             status set, future incident_date, zero/negative amount
-- GE rules that will catch these:
--   • expect_column_values_to_be_between   (claim_amount → min=0.01)
--   • expect_column_values_to_be_between   (incident_date → max=today)
--   • expect_column_pair_values_A_to_be_greater_than_B (filed_date >= incident_date)
--   • expect_column_values_to_be_in_set    (status → ['pending','approved','rejected','paid'])
-- ============================================================

INSERT INTO public.claims
  (claim_number, policy_id, incident_date, filed_date,
   claim_amount, approved_amount, status, rejection_reason, created_at)
VALUES
  -- (J1) claim_amount (999999) > coverage of policy 1 (500000)
  ('CLM-DIRTY-001', 1,  '2024-09-01', '2024-09-10', 999999.00, NULL, 'pending',    NULL,                     '2024-09-10 00:00:00'),

  -- (J2) claim_amount (750000) > coverage of policy 4 (150000)
  ('CLM-DIRTY-002', 4,  '2024-10-05', '2024-10-10', 750000.00, NULL, 'pending',    NULL,                     '2024-10-10 00:00:00'),

  -- (K1) filed_date 45 days BEFORE incident_date → pair comparison fails
  ('CLM-DIRTY-003', 2,  '2024-11-15', '2024-10-01',  50000.00, NULL, 'pending',    NULL,                     '2024-10-01 00:00:00'),

  -- (K2) filed_date 20 days BEFORE incident_date → pair comparison fails
  ('CLM-DIRTY-004', 5,  '2024-12-20', '2024-11-30',  80000.00, NULL, 'approved',   NULL,                     '2024-11-30 00:00:00'),

  -- (L1) status = 'processing' (not in valid set) → set membership fails
  ('CLM-DIRTY-005', 3,  '2024-08-20', '2024-08-25',  30000.00, NULL, 'processing', NULL,                     '2024-08-25 00:00:00'),

  -- (L2) status = 'cancelled' (not in valid set) → set membership fails
  ('CLM-DIRTY-006', 7,  '2024-07-01', '2024-07-08',  45000.00, NULL, 'cancelled',  NULL,                     '2024-07-08 00:00:00'),

  -- (M1) incident_date in the future → between(max=today) fails
  ('CLM-DIRTY-007', 9,  '2030-01-01', '2030-01-05',  75000.00, NULL, 'pending',    NULL,                     '2024-09-01 00:00:00'),

  -- (M2) both dates in the future AND filed before incident (double fail)
  ('CLM-DIRTY-008', 10, '2031-06-01', '2031-05-15', 100000.00, NULL, 'pending',    NULL,                     '2024-09-01 00:00:00'),

  -- (N1) claim_amount = 0 (zero, should be > 0) → between(min=0.01) fails
  ('CLM-DIRTY-009', 6,  '2024-07-10', '2024-07-15',      0.00, NULL, 'pending',    NULL,                     '2024-07-15 00:00:00'),

  -- (N2) claim_amount = -500 (negative) → between(min=0.01) fails
  ('CLM-DIRTY-010', 8,  '2024-06-05', '2024-06-10',   -500.00, NULL, 'rejected',   'Negative amount error',  '2024-06-10 00:00:00'),

  -- (J+L) double: amount exceeds coverage AND invalid status
  ('CLM-DIRTY-011', 4,  '2024-05-20', '2024-05-25', 999999.00, NULL, 'waiting',    NULL,                     '2024-05-25 00:00:00'),

  -- (K+M) double: future incident_date AND filed before incident
  ('CLM-DIRTY-012', 11, '2035-03-10', '2035-02-28',  60000.00, NULL, 'pending',    NULL,                     '2024-09-01 00:00:00');

COMMIT;

-- ============================================================
-- Quick verification queries (run after INSERT):
-- ============================================================
--
-- Count dirty rows per table:
--   SELECT COUNT(*) FROM public.policyholders WHERE national_id NOT SIMILAR TO '[A-Z][0-9]{9}';
--   SELECT COUNT(*) FROM public.policies WHERE policy_number LIKE 'POL-DIRTY-%';
--   SELECT COUNT(*) FROM public.claims  WHERE claim_number  LIKE 'CLM-DIRTY-%';
--
-- See all dirty policies:
--   SELECT policy_number, product_type, premium_monthly, coverage_amount,
--          status, effective_date, expiry_date
--   FROM public.policies WHERE policy_number LIKE 'POL-DIRTY-%'
--   ORDER BY policy_number;
--
-- See all dirty claims:
--   SELECT claim_number, policy_id, incident_date, filed_date,
--          claim_amount, status
--   FROM public.claims WHERE claim_number LIKE 'CLM-DIRTY-%'
--   ORDER BY claim_number;
-- ============================================================
