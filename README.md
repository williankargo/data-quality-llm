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
    │   ├── "Add rule by description" → multi-turn chat
    │   │   └── LLM translates plain English → one GE rule
    │   │       refine it over follow-up turns (up to 5 rounds)
    │   │       or it asks a clarifying question if too vague
    │   └── Saved rule cards
    │       └── "Edit" → modal with side-by-side diff of your changes
    │
    └── Results tab
        ├── (optional) Rule filter → run only selected rules
        └── "Run checks" button
            └── Runs saved rules asynchronously; UI polls for progress
                └── Each rule: PASS (green) / FAIL (red) / ERROR (yellow)
                    └── Expand a FAIL row →
                        ├── table of up to 10 full violating rows
                        │   (violating column highlighted; horizontal scroll)
                        ├── "Download all violations (CSV)" button
                        └── "Why did this fail?" → LLM plain-English explanation
```

Results use a three-color system: **green** = rule passes, **red** = data violates the rule (expand to see full violating rows), **yellow** = rule itself failed to execute (e.g., column does not exist — fix the rule, not the data).

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
# Frontend (optional)
# The frontend defaults to http://localhost:8000 for the backend.
# Only create frontend/.env.local if your backend runs elsewhere:
#   echo 'NEXT_PUBLIC_API_URL=http://your-host:port' > frontend/.env.local
```

### 2. Database Setup (Supabase)

In the Supabase SQL Editor, run these files in order:
1. `backend/db/schema.sql` — creates policyholders, policies, claims tables
2. `backend/db/seed.sql` — inserts ~120 rows of clean insurance data
3. `backend/db/001_dq_schema.sql` — creates the dq schema for rules and run results
4. `backend/db/002_run_results_status.sql` — adds the three-state `status` column to run_results
5. `backend/db/003_llm_cache.sql` — creates the `dq.llm_cache` table (LLM response cache)
6. `backend/db/004_run_results_rows.sql` — adds `unexpected_rows` (JSONB) + `truncated` to run_results
7. `backend/db/005_dirty_data.sql` — inserts intentionally dirty rows so rules produce FAIL results in the demo

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

### 5. Dirty data for demo fail results

Step 7 of the Database Setup above (`005_dirty_data.sql`) already inserts dirty rows across all three tables — bad `national_id` formats, invalid `gender`/`status`/`product_type` values, negative premiums, future dates, and date-ordering violations. These guarantee **red** (fail) results with multiple violating rows so you can exercise the violating-row table and CSV download.

If you skipped that migration, run it now in the Supabase SQL Editor before proceeding.

### 6. Full demo flow

**Step 1 — Explore the table**

Click **policyholders** in the sidebar. The Schema tab shows all columns with types and a 50-row data sample.

**Step 2 — Suggest AI rules**

Switch to the **Rules** tab. Click **Suggest rules** — the backend sends the table schema and sample rows to Claude, which proposes 5–10 Great Expectations rules. Each rule shows its expectation type and a plain-English description. Rules that are already saved show an "Already saved" badge with Save disabled.

**Step 3 — Save rules**

Click **Save** on 4–5 rules you want to keep. Each saved rule appears in the "Saved rules" section below.

**Step 4 — Add a custom rule via natural-language chat**

Click **Add rule by description**. Type something specific like `"premium must not be negative"` and submit. The AI translates it into a GE expectation and returns a draft card. This is a **multi-turn chat**: you can refine over follow-up turns (e.g., `"also reject zero"`) for up to 5 rounds. If you type something vague like `"data must be good"`, the AI asks a clarifying question instead. The conversation lives only in the browser — refresh or **Start over** clears it.

**Step 5 — Edit a saved rule (with diff view)**

On any saved rule card, click **Edit**. The modal shows the original rule on the left and an editable form on the right (expectation type, kwargs JSON, description). A diff at the bottom highlights exactly what you changed. Invalid `kwargs` JSON blocks Save with an inline error. Save triggers `PUT /rules/{id}`.

**Step 6 — Run the checks**

Switch to the **Results** tab. Click **Run checks**. The run executes **asynchronously**: the request returns immediately with `status: running`, the UI polls every second and shows an `N/total rules completed` counter as each rule finishes. Optionally expand the **rule filter** first to run only a subset. Each rule then shows one of:
- **Green** — rule passes; data is clean
- **Red** — data violates the rule; expand to see the full violating rows
- **Yellow** — rule could not execute (e.g., column does not exist); fix the rule, not the data

**Step 7 — Inspect and explain failures**

Expand a **red** row. You get a table of up to 10 complete violating rows, with the violating column highlighted (horizontal scroll for wide tables). Click **Download all violations (CSV)** to export every captured violating row (capped at 1000). Click **Why did this fail?** to have Claude explain the failure in plain English with possible causes and a suggested action — responses are cached so re-opening the same row is instant.

**Step 8 — Re-run after changes**

Go back to Rules, delete or edit a rule, return to Results, and click Run again — the new run reflects the updated rule set. Previous runs remain stored as immutable snapshots (including their violating rows) even after rules change.

## Development

See `backend/README.md` and `frontend/` for service-specific instructions.

## Documentation

- [`docs/architecture.md`](docs/architecture.md) — full architecture overview, request flow, and Future Enhancements
- [`docs/ai-integration.md`](docs/ai-integration.md) — AI design rationale: prompts, Tool Use schemas, multi-turn chat, response cache
- [`docs/ai-tools-usage.md`](docs/ai-tools-usage.md) — AI tool usage log (Day 1 → Day 3)
- [`docs/day1-plan.md`](docs/day1-plan.md) — Day 1 architecture decisions and implementation specification
- [`docs/day2-plan.md`](docs/day2-plan.md) — Day 2 architecture decisions and implementation specification
- [`docs/day3-plan.md`](docs/day3-plan.md) — Day 3 architecture decisions (D#23–D#38) and specification
