-- Personal insurance domain schema (public schema)
-- Run this first before seed.sql and 001_dq_schema.sql

CREATE TABLE public.policyholders (
  id SERIAL PRIMARY KEY,
  national_id VARCHAR(10) UNIQUE NOT NULL,
  full_name VARCHAR(100) NOT NULL,
  birth_date DATE NOT NULL,
  gender VARCHAR(1) NOT NULL,
  email VARCHAR(200),
  phone VARCHAR(20),
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE public.policies (
  id SERIAL PRIMARY KEY,
  policy_number VARCHAR(20) UNIQUE NOT NULL,
  holder_id INTEGER REFERENCES public.policyholders(id),
  product_type VARCHAR(30) NOT NULL,
  coverage_amount NUMERIC(14,2) NOT NULL,
  premium_monthly NUMERIC(10,2) NOT NULL,
  effective_date DATE NOT NULL,
  expiry_date DATE NOT NULL,
  status VARCHAR(10) NOT NULL,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE public.claims (
  id SERIAL PRIMARY KEY,
  claim_number VARCHAR(20) UNIQUE NOT NULL,
  policy_id INTEGER REFERENCES public.policies(id),
  incident_date DATE NOT NULL,
  filed_date DATE NOT NULL,
  claim_amount NUMERIC(14,2) NOT NULL,
  approved_amount NUMERIC(14,2),
  status VARCHAR(15) NOT NULL,
  rejection_reason TEXT,
  created_at TIMESTAMP DEFAULT NOW()
);
