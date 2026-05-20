# AI-Powered Data Quality Assistant

An AI tool that lets domain experts define and run data quality rules against a PostgreSQL database via a chat-style interface — no Great Expectations knowledge required.

## Product Overview

```
User opens localhost:3000
│
├── Sidebar (always visible)
│   └── Lists all tables in the database
│       └── Click a table → URL becomes /tables/{name}?tab=schema
│
└── Main area (tab-switched per table)
    │
    ├── Schema tab          [available now]
    │   ├── Column list: name, type, nullable, default
    │   └── Sample data: first 50 rows
    │
    ├── Rules tab           [Day 2]
    │   ├── "Suggest rules" button
    │   │   └── LLM reads schema + sample → proposes 5–10 GE rules
    │   │       (e.g. "national_id must match A999999999 format")
    │   └── Plain-English input box
    │       └── LLM translates one sentence → one GE rule
    │           or asks a clarifying question if too vague
    │
    └── Results tab         [Day 2]
        └── "Run checks" button
            └── Runs all saved rules against the live table
                └── Each rule: PASS (green) / FAIL (red)
                    └── Expand failed rule → violating sample values + count
```

Any error (DB down, LLM timeout) shows a human-readable message with possible causes and a retry button — no raw stack traces shown to the user.

## Architecture

- **Backend**: FastAPI (Python) — AI rule generation, GE execution, REST API — port 8000
- **Frontend**: Next.js (TypeScript) — Table Explorer, Rule Manager, Results Dashboard — port 3000
- **Database**: PostgreSQL via Supabase (Session Pooler)
- **LLM**: Anthropic Claude `claude-sonnet-4-6`

## 5-Minute Demo Quick Start

### Prerequisites
- Python 3.11+ with `uv` installed (`pip install uv`)
- Node.js 18+
- A Supabase project with the schema set up (see Database Setup below)

### 1. Clone and configure

```bash
git clone <repo-url>
cd data-quality-llm
```

```bash
# Backend
cp backend/.env.example backend/.env
# Edit backend/.env: fill in DATABASE_URL and ANTHROPIC_API_KEY
```

```bash
# Frontend
cp frontend/.env.local.example frontend/.env.local
# Edit frontend/.env.local if your backend runs on a different host/port
```

### 2. Database Setup (Supabase)

In the Supabase SQL Editor, run these files in order:
1. `backend/db/schema.sql` — creates policyholders, policies, claims tables
2. `backend/db/seed.sql` — inserts ~120 rows of clean insurance data
3. `backend/db/001_dq_schema.sql` — creates the dq schema for rules and run results

### 3. Start the backend

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

Verify: `curl http://localhost:8000/health` should return `{"status":"ok",...}`

### 4. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000` — you should see the Table Explorer with 3 tables in the sidebar.

### 5. Demo flow

1. Click **policyholders** in the sidebar → Schema tab shows columns and sample data
2. Switch to **Rules** tab → click "Suggest rules" → AI proposes 5–10 data quality rules
3. Accept a rule or type your own in plain English
4. Switch to **Results** tab → click "Run checks" → see pass/fail per rule with red/green indicators
5. Expand a failed rule → see the violating sample values

### To show failing rules in the demo

Run this in Supabase SQL Editor to insert one dirty row:
```sql
INSERT INTO public.policyholders (national_id, full_name, birth_date, gender)
VALUES ('INVALID', 'Test User', '2030-01-01', 'X');
```
Then re-run the checks — rules for `national_id` format and `gender` enum will fail with sample values.

## Development

See `backend/README.md` and `frontend/` for service-specific instructions.

## Documentation

- `docs/day1-plan.md` — Architecture decisions and implementation specification
- `docs/ai-tools-usage.md` — AI tool usage log
- `docs/ai-integration.md` — AI integration details (Day 3)
- `docs/architecture.md` — Full architecture overview (Day 3)
