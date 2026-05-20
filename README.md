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
    ├── Schema tab
    │   ├── Column list: name, type, nullable, default
    │   └── Sample data: first 50 rows
    │
    ├── Rules tab
    │   ├── "Suggest rules" button
    │   │   └── LLM reads schema + sample → proposes 5–10 GE rules
    │   │       (e.g. "national_id must match A999999999 format")
    │   └── Plain-English input box
    │       └── LLM translates one sentence → one GE rule
    │           or asks a clarifying question if too vague
    │
    └── Results tab
        └── "Run checks" button
            └── Runs all saved rules against the live table
                └── Each rule: PASS (green) / FAIL (red) / ERROR (yellow)
                    └── Expand row → violating sample values + count, or error message
```

Results use a three-color system: **green** = rule passes, **red** = data violates the rule (with violating sample values), **yellow** = rule itself failed to execute (e.g., column does not exist — fix the rule, not the data).

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
4. `backend/db/002_run_results_status.sql` — adds the three-state `status` column to run_results

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

### 5. Insert a dirty row (required for demo fail results)

Run this in the Supabase SQL Editor before proceeding — it creates one row that will trigger rule failures:

```sql
INSERT INTO public.policyholders (national_id, full_name, birth_date, gender)
VALUES (NULL, 'Dirty Row', '2030-01-01', 'X');
```

This row has a null `national_id` and an invalid `gender` value, which will produce **red** (fail) results in the Results Dashboard.

### 6. Full demo flow

**Step 1 — Explore the table**

Click **policyholders** in the sidebar. The Schema tab shows all columns with types and a 50-row data sample.

**Step 2 — Suggest AI rules**

Switch to the **Rules** tab. Click **Suggest rules** — the backend sends the table schema and sample rows to Claude, which proposes 5–10 Great Expectations rules. Each rule shows its expectation type and a plain-English description. Rules that are already saved show an "Already saved" badge with Save disabled.

**Step 3 — Save rules**

Click **Save** on 4–5 rules you want to keep. Each saved rule appears in the "Saved rules" section below.

**Step 4 — Add a custom rule via natural language**

Click **Add rule by description**. Type something specific like `"premium must not be negative"` and submit. The AI translates it into a GE expectation and returns a draft card to save. If you type something vague like `"data must be good"`, the AI asks a clarifying question instead.

**Step 5 — Run the checks**

Switch to the **Results** tab. Click **Run checks**. Within 2 seconds, each rule shows one of:
- **Green** — rule passes; data is clean
- **Red** — data violates the rule; expand to see violating row samples and count
- **Yellow** — rule could not execute (e.g., column does not exist); check rule configuration

**Step 6 — Re-run after changes**

Go back to Rules, delete a rule, return to Results, and click Run again — the new run reflects the updated rule set. Previous run results remain visible in the database even after rules are deleted.

## Development

See `backend/README.md` and `frontend/` for service-specific instructions.

## Documentation

- `docs/day1-plan.md` — Day 1 architecture decisions and implementation specification
- `docs/day2-plan.md` — Day 2 architecture decisions and implementation specification
- `docs/ai-tools-usage.md` — AI tool usage log (Day 1 + Day 2)
- `docs/ai-integration.md` — AI integration details (Day 3)
- `docs/architecture.md` — Full architecture overview (Day 3)
