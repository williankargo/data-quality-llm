# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

AI-Powered Data Quality Assistant — a 3-day MVP that lets domain experts define and run Great Expectations data quality rules against a PostgreSQL (Supabase) database via a chat-style interface, without needing to know the GE framework.

## Architecture

Monorepo with two independent services:

```
backend/    FastAPI (Python) — AI rule generation, GE execution, REST API
frontend/   Next.js (TypeScript) — Table Explorer, Rule Manager, Results Dashboard
docs/       Deliverable documentation (architecture, AI integration, AI tool usage log)
```

**Request flow:**
1. Frontend calls backend REST API
2. Backend queries Postgres for schema/sample data
3. Backend sends schema + sample to LLM (OpenAI or Anthropic) using prompt templates in `backend/app/prompts/`
4. LLM returns structured GE expectation JSON (validated by Pydantic)
5. Backend runs GE against the table and stores results in Postgres
6. Frontend displays results

## Backend

**Key files:**
- `app/main.py` — FastAPI app entry point; routers are registered here
- `app/config.py` — All env vars via Pydantic Settings; `.env` is loaded from the `backend/` directory
- `app/api/` — HTTP layer (thin controllers); one file per resource: `tables.py`, `rules.py`, `results.py`
- `app/services/` — Business logic: `db.py` (SQLAlchemy + psycopg3), `ai_generator.py` (LLM calls), `ge_engine.py` (Great Expectations)
- `app/schemas/` — Pydantic request/response models
- `app/prompts/` — LLM prompt templates (Markdown); injected at runtime with `{{variable}}` substitution

**Constraints:**
- LLM provider: Anthropic Claude (claude-sonnet-4-6); no OpenAI dependency needed
- MVP scope: read-only — users can explore tables, get AI-suggested rules, and run checks; they cannot add/modify database tables
- Rules are stored in Postgres (NOT in GE's built-in file/cloud store) — keeps state in one place
- LLM output is always validated against a Pydantic schema before being persisted or returned to the client
- `app/config.py` is the single source of truth for env vars; never read `os.environ` directly elsewhere
- Quality reports must include per-expectation pass/fail, count of violating rows, and 1–3 sample violating values for diagnostics
- Run results are cached in Postgres (`runs` + `run_results` tables) so the UI can re-display without re-executing GE

## Frontend

> To be scaffolded: `cd frontend && npx create-next-app@latest . --typescript --app --tailwind --eslint`

Three main views:
1. **Table Explorer** — list Postgres tables, show schema + row count
2. **Rule Management** — display AI-suggested rules, accept natural-language input, show/edit GE config before saving
3. **Results Dashboard** — run rules; view pass/fail per expectation with **red/yellow/green** color coding for failures/warnings/passes; expand each row to see violating values and counts; one-click re-run

Backend base URL: `http://localhost:8000` (configure via `NEXT_PUBLIC_API_URL` env var).

## API Endpoints (planned)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check (implemented) |
| GET | `/tables` | List tables + metadata |
| GET | `/tables/{name}/sample` | Sample rows for AI context |
| POST | `/rules/suggest` | AI-suggest rules from schema |
| POST | `/rules/from-nl` | Natural language → GE rule |
| GET/POST | `/rules` | List / create rules |
| PUT/DELETE | `/rules/{id}` | Update / delete rule |
| POST | `/runs` | Execute rules against a table |
| GET | `/runs/{id}` | Fetch cached run results |

## Development Commands

### Backend
```bash
# First-time setup (from backend/)
uv sync                                          # install deps
cp ../.env.example .env                          # then fill in real values

# Run dev server (from backend/)
uv run uvicorn app.main:app --reload --port 8000

# Run tests
uv run pytest
uv run pytest tests/test_foo.py::test_bar        # single test

# Lint / format
uv run ruff check .
uv run ruff format .
```

### Frontend
```bash
# From frontend/
npm run dev     # start dev server on :3000
npm run build   # production build
npm run lint    # ESLint
```

## Environment Variables

All backend config lives in `backend/.env` (copy from `.env.example`):

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | `postgresql+psycopg://USER:PASS@HOST:PORT/DB` (Supabase) |
| `LLM_PROVIDER` | `anthropic` (decided) |
| `LLM_MODEL` | `claude-sonnet-4-6` (default) |
| `ANTHROPIC_API_KEY` | Required |
| `CORS_ORIGINS` | Comma-separated; default `http://localhost:3000` |

## Prompt Templates

Templates in `backend/app/prompts/` use `{{variable}}` placeholders.

**`rule_from_schema.md`** — the user selects a table; the system feeds its schema + sample rows to the LLM; the LLM observes patterns and proposes multiple rules on its own. Returns an **array**.

**`rule_from_nl.md`** — the user types a rule in plain English; the LLM translates it into a GE expectation. Returns a **single rule**. If the description is too vague to translate, returns `needs_clarification` with a follow-up question instead.

Typical workflow: run `rule_from_schema` first to get a baseline set of suggestions, then use `rule_from_nl` to add domain-specific rules that the LLM couldn't infer from data alone.

LLM responses must be constrained to JSON (use structured outputs / function calling).

## Compaction Policy
When compacting, focus on:
- Test output and code changes
- Complete list of modified files
- All unfinished tasks


## Evaluation Criteria

Per the spec, three equal-weight areas:

1. **AI-First Development** — effective use of AI coding tools, quality of AI integrations, prompt engineering, AI-driven automation
2. **Product Thinking** — UX design, feature prioritization, error handling and edge cases, overall solution architecture
3. **Technical Implementation** — code quality and organization, system performance, API design, documentation

**Bonus areas** (rewarded if delivered): creative AI usage beyond requirements, innovative UX, additional automated features, performance optimizations, thoughtful error handling, clear AI tool usage documentation.

Use these to prioritize trade-offs: when deciding what to cut, prefer cutting items that don't show up in any of the three criteria.

---

## Product Principles

From the spec's "Notes for candidates" — internalize when making design decisions:

- **Target user is non-technical** (domain expert, not engineer). Hide GE jargon; surface plain-language descriptions.
- **Working features > perfect code.** Ship the slice; iterate later.
- **Don't reinvent the wheel.** Use existing libraries (Great Expectations, Anthropic SDK, shadcn/ui-style patterns) rather than rebuild.
- **Document AI tool usage as you go.** This is a graded criterion, not an afterthought.
- **Consider scalability and maintainability** in architecture choices, even though MVP is small.

---

## Task Breakdown

Granular checklist mirroring spec's Day 1/2/3 outline. Update as work progresses.

### Day 1 — Foundation & Core AI Integration
- [x] Project infrastructure (uv, npm, Git, monorepo layout)
- [x] Backend skeleton (FastAPI app, config, CORS, `/health`)
- [x] Database connectivity (`services/db.py` with Supabase Session Pooler)
- [x] Schema + seed data (`db/schema.sql`, `db/seed.sql` with intentional DQ issues)
- [x] AI prompt templates (`prompts/rule_from_schema.md`, `prompts/rule_from_nl.md`)
- [x] Initial API endpoints (`GET /tables/`, `GET /tables/{name}/sample`)
- [x] Frontend scaffold (Next.js 16 + Tailwind v4)
- [x] Frontend Table Explorer (sidebar + detail page, loading skeletons)

### Day 2 — Core Functionality

**Backend**
- [ ] `schemas/rules.py` — Pydantic models for GE expectation rules + suggestion/save requests
- [ ] `services/ai_generator.py` — Anthropic client wrapper; load prompts; call LLM with structured output; validate against Pydantic
- [ ] `api/rules.py` — `POST /rules/suggest`, `POST /rules/from-nl`, `GET/POST /rules`, `PUT/DELETE /rules/{id}`
- [ ] Rules persistence — `dq.rules` table via `001_dq_schema.sql`; CRUD in `rules_store.py`
- [ ] `services/ge_engine.py` — Great Expectations execution against Postgres; map JSON rules → GE Expectation objects
- [ ] Runs persistence — `dq.runs` + `dq.run_results` tables; results cached in `runs_store.py`
- [ ] `api/results.py` — `POST /runs`, `GET /runs/{id}`, `GET /runs/`
- [ ] Register `rules` and `results` routers in `main.py`

**Frontend**
- [ ] Rule Management view (`/tables/[name]/rules`)
  - [ ] Suggest button → `POST /rules/suggest`
  - [ ] Natural-language input → `POST /rules/from-nl`
  - [ ] Show GE config inline (expectation_type + kwargs per draft)
  - [ ] Delete saved rule (Delete button per card, optimistic UI update)
- [ ] Results Dashboard view (`/tables/[name]/results`)
  - [ ] Run button → `POST /runs`
  - [ ] List of expectations with red/green color coding
  - [ ] Expand row → violating sample values and counts
  - [ ] Re-run button (same "Run checks" button)

### Day 3 — Polish & Enhancement
- [ ] Error handling: graceful UI for failed LLM call, DB timeout, GE crash
- [ ] Input validation: reject malformed NL inputs; LLM `needs_clarification` flow in UI
- [ ] Caching: avoid re-calling LLM with identical schema+sample (hash-based)
- [ ] UI polish: empty states, hover affordances, keyboard nav, mobile layout
- [ ] Performance: parallel rule execution where independent; cap sample row size sent to LLM
- [ ] `docs/architecture.md` (incl. future enhancements section)
- [ ] `docs/ai-integration.md`
- [ ] `docs/ai-tools-usage.md`
- [ ] README — end-to-end "5-minute demo" walkthrough

### Bonus (only if time permits)
- [ ] LLM auto-explains failures in plain English on Results Dashboard
- [ ] One-click "fix data" suggestions for failed rows
- [ ] Diff view when editing a suggested rule
- [ ] Export rules as a GE checkpoint YAML
