# Day 1 Architecture Plan — AI-Powered Data Quality Assistant

This document is the complete Day 1 architecture plan, covering all resolved decisions (Decision Log), open decisions (Decision Points — currently empty), and the implementation specification. Treat this as the single source of truth.

---

## Section 1: Decision Log (Resolved Decisions)

Each decision includes a **Problem Essence** (why this is a real decision, not a trivial one) and **Tradeoffs** (what we are giving up with this choice).

---

### D#0-a: LLM Provider — Anthropic Claude `claude-sonnet-4-6`

- **Decision**: Anthropic is the sole LLM provider. Model is `claude-sonnet-4-6`. No OpenAI SDK dependency.
- **Why it matters**: All prompt engineering, structured-output mechanisms, and SDK abstractions bind to this choice.
- **Options considered**: OpenAI GPT; dual-provider abstraction layer. A provider-agnostic interface is over-engineering for a 3-day MVP.
- **How chosen**: MVP timeline + Anthropic Tool Use maturity for schema-inference tasks.
- **Problem essence**: Choosing a provider is not just swapping an import. It locks in the prompt style, the structured-output syntax (tool use vs. function calling vs. JSON mode), and the token pricing model. Once downstream code heavily uses a provider's proprietary features (e.g., Anthropic's `tools` parameter format), switching cost grows from "change one import" to "rewrite all prompt-and-schema binding logic." Locking in one provider for a 3-day MVP is more pragmatic than building an abstraction layer.
- **Tradeoffs**: Lose multi-provider flexibility. If Anthropic has an outage or reprices, migration will take half a day to a full day. Also lose the ability to compare output quality across models (unless manual experiments are added later).

---

### D#0-b: Backend Stack — FastAPI + uv + SQLAlchemy + psycopg3

- **Decision**: Backend uses FastAPI, uv for package management, SQLAlchemy as ORM/Core, psycopg3 as the Postgres driver.
- **Why it matters**: Affects all import paths, dependency locking, and test infrastructure.
- **Options considered**: Flask (too minimal; requires assembling validation and OpenAPI manually); Django (too heavyweight); pip + venv (uv is strictly better on lock speed and install performance).
- **How chosen**: "Built-in Pydantic validation + auto OpenAPI + async-friendly" as the three filters.
- **Problem essence**: The backend must do three things simultaneously — serve REST, make structured LLM calls, and query Postgres for schema inspection and GE execution. The framework must optimize ergonomics across all three paths. FastAPI + Pydantic lets LLM-output validation and API request/response validation share the same model definitions, which is the biggest time-saver within the MVP.
- **Tradeoffs**: Lose Django's built-in admin CRUD UI (not needed for MVP). psycopg3 is newer than psycopg2; some older StackOverflow answers don't apply and official docs must be consulted for edge cases.

---

### D#0-c: Frontend Stack — Next.js + TypeScript + App Router + Tailwind

- **Decision**: Frontend uses Next.js 16, TypeScript, App Router, Tailwind v4.
- **Why it matters**: Determines the entire frontend directory structure, routing model, and styling conventions.
- **Options considered**: Vite + React Router (lighter, but no server components or file-based routing); Pages Router (older Next.js — App Router is the current recommendation).
- **How chosen**: "File-based routing reduces boilerplate" + "Tailwind accelerates style iteration."
- **Problem essence**: The MVP frontend has three major views (Table Explorer, Rule Manager, Results Dashboard), but all are structurally "list + detail" variants. Next.js App Router's nested layouts make the "persistent left sidebar + right tab switching" layout nearly free to implement (see D#5). Tailwind v4's utility-first approach also eliminates the overhead of writing many CSS files for a small demo.
- **Tradeoffs**: Lose the pure SPA model (Next.js brings SSR/RSC machinery the MVP doesn't necessarily need). Tailwind's utility classes make markup more verbose; readability is a known cost.

---

### D#0-d: Rules Stored in Postgres (Not GE's Built-in Store)

- **Decision**: All rules and run results are stored in Postgres. Great Expectations' built-in file-based or cloud store is not used.
- **Why it matters**: Forces GE to be treated as a one-shot evaluation engine, not a stateful rule-management system.
- **Options considered**: GE native Expectation Suite YAML (closer to GE conventions, but state is scattered); hybrid (part in GE, part in DB).
- **How chosen**: "Centralized state, easy querying, simple CRUD API."
- **Problem essence**: GE has its own store abstractions (Expectation Store, Validation Store, Checkpoint Store), but these are designed for data engineers working in CLIs/notebooks — not for real-time web UI CRUD. Using GE's native store would require reading the filesystem or GE Cloud for every rule listing, and the structure doesn't match web app needs (multi-user, historical runs, result querying). Treating rules as ordinary DB records is simply simpler.
- **Tradeoffs**: Lose the ability to use GE ecosystem tooling directly (e.g., `great_expectations checkpoint run` CLI). We must write our own JSON → GE Expectation object translation layer in `services/ge_engine.py`.

---

### D#0-e: CORS and Port Defaults

- **Decision**: Backend defaults to port 8000, frontend to port 3000, `CORS_ORIGINS` defaults to `http://localhost:3000`.
- **Why it matters**: If these are inconsistent during local dev, the frontend is blocked by CORS and the demo breaks entirely.
- **Options considered**: Same port via Next.js API route proxy — removes the dependency on the backend being separately running, but increases deployment complexity.
- **How chosen**: "Simplest local dev setup + two completely independent services that can be restarted separately."
- **Problem essence**: Separate services have independent restart cycles during development (backend restarts on LLM SDK changes; frontend hot-reloads constantly). Sharing a port couples them, defeating the purpose of the monorepo layout.
- **Tradeoffs**: Lose "same-origin, no CORS needed" convenience — but production deployments use a reverse proxy anyway, so this can never be relied on.

---

### D#1: Seed Data — Personal Insurance Domain (Custom)

- **Decision**: The seed data uses a personal insurance business domain. Representative tables: `policyholders`, `policies`, `claims` (columns defined in the Specification).
- **Why it matters**: Seed data determines whether the LLM's rule suggestions look like they have genuine domain insight. Without business context, suggestions end up as generic rules like `column_values_to_not_be_null`.
- **Options considered**: Generic e-commerce (products/orders/customers — too familiar, LLM is overtrained on it); railroad maintenance (domain terminology needs explanation); banking transactions (compliance-sensitive).
- **How chosen**: "LLM has baseline domain knowledge + business rules are intuitively obvious + demo audience needs no background explanation."
- **Problem essence**: The core MVP demo point is "the LLM can propose meaningful rules just by looking at a schema." Insurance has rich, natural data quality rules — "premium must not be negative," "policy expiry must be after effective date," "claim amount must not exceed coverage amount," "insured age must be in a reasonable range." These rules are intuitive, the LLM has ample training data, and demo audiences understand them without domain expertise.
- **Tradeoffs**: Insurance fields (e.g., `national_id`, `premium`) feel more like real sensitive data than e-commerce fields; the demo must clarify this is fake data. Some insurance business rules require cross-table computation (e.g., claim amount vs. coverage amount), which GE does not support natively — Day 2 must restrict proposed rules to single-table checks.

---

### D#2: Dirty Data Strategy — Clean Samples + Prompt-Guided LLM Inference (Option C)

- **Decision**: All seed data is **clean**. No dirty data is intentionally injected. The prompt instructs the LLM to "infer potential data quality issues from schema and business logic" and propose corresponding rules.
- **Why it matters**: Affects the prompt template framing and the LLM's output behavior. Also affects whether the demo can show failing rules.
- **Options considered**:
  - Option A: Inject dirty data directly (simple, but the LLM is just doing "observe dirty rows → extract rules," which weakens the "intelligent inference" demonstration).
  - Option B: Two datasets (clean for suggestion, dirty for execution) — complicated to switch between.
  - Option C: Pure clean data + prompt-guided inference. To show failing rules in a demo, manually INSERT one dirty row.
- **How chosen**: "Best demonstrates LLM reasoning ability" — this is the primary exhibit for the AI-First Development evaluation criterion.
- **Problem essence**: The answer to "why is AI better than hardcoded rules?" is "AI can infer rules engineers wouldn't have thought of." If the sample data already contains dirty rows, the LLM is just doing pattern matching — the demo degrades to "automatic anomaly detection." Option C forces the LLM to actually *reason*, which is exactly what evaluators want to see.
- **Tradeoffs**: Lose the convenience of "automatically seeing failures when rules run." To show red failure results in the demo, one dirty row must be manually INSERTed (this step will be documented in the README demo script). Also lose "data realism" — real databases always have dirty data, and a purely clean sample looks slightly artificial.

---

### D#3: DB Schema Namespacing — Business Data in `public`, System Tables in `dq` (Option C)

- **Decision**: Seed business data (`policyholders`, `policies`, `claims`) goes in the `public` schema. System tables (`rules`, `runs`, `run_results`) go in a separate `dq` schema.
- **Why it matters**: Determines what `GET /tables` returns and whether the UI sidebar looks clean to the user.
- **Options considered**:
  - Option A: Everything in `public` (simplest, but system tables appear in the user's Table Explorer list).
  - Option B: Table name prefixes (`_dq_rules`), hidden via filter logic (brittle, easy to accidentally expose).
  - Option C: Separate schema (standard Postgres pattern, physical isolation).
- **How chosen**: "Clean user experience + simple backend filter logic + follows Postgres conventions."
- **Problem essence**: Non-technical users opening the Table Explorer should not see `rules` or `runs` in their sidebar — it will confuse them ("Can I write rules against the rules table?"). Meanwhile, the backend's `GET /tables` filter logic should be clean: "list tables in the public schema" is a single-line SQL clause. Prefix-based filtering is error-prone.
- **Tradeoffs**: Lose the convenience of "all tables in one schema, easy to JOIN" (though we would never JOIN business tables with DQ system tables). Migrations and connection strings must remember `search_path` configuration, adding a line of boilerplate.

---

### D#4: DB Connection Mode — Full Sync (Option A)

- **Decision**: Use synchronous SQLAlchemy + psycopg3. All FastAPI endpoints use `def` (not `async def`).
- **Why it matters**: Affects all service-layer function signatures, thread pool behavior, and future background task choices.
- **Options considered**:
  - Option A: Full sync (simplest; FastAPI automatically runs sync endpoints in a thread pool).
  - Option B: Full async (async SQLAlchemy + asyncpg — better performance, but steep learning curve).
  - Option C: Mixed (async API layer, sync DB/GE) — error-prone.
- **How chosen**: "Minimize pitfalls within 3-day MVP timeline."
- **Problem essence**: FastAPI is async-first, but sync endpoints are fully supported and performant at MVP traffic levels (FastAPI runs `def` endpoints in a thread pool automatically, without blocking the event loop). Async SQLAlchemy, while available in v2.0, has weaker ecosystem support — fewer tutorials, weaker type hint tooling, harder-to-debug issues. For a 3-day MVP, the "performance" gain of async is negligible, but the "debugging time" cost is real.
- **Tradeoffs**: Lose the ability to natively parallelize multiple LLM requests with async (would require `asyncio.to_thread` or `concurrent.futures`, making the code slightly messier). Under high concurrency (which will not occur during the MVP), thread pools consume more memory than async event loops.

---

### D#5: Table Explorer Layout — Two-Column + Tabs (Option C)

- **Decision**: Left sidebar lists all tables. Right main area contains `[Schema][Rules][Results]` tabs.
- **Why it matters**: This is the screen users spend most time on. The layout determines the friction of the "explore → define rules → view results" workflow.
- **Options considered**:
  - Option A: Three separate pages (clean URLs, but each page switch loses table context).
  - Option B: Single column (mobile-friendly, but wastes horizontal space on desktop).
  - Option C: Two columns + tabs (sidebar always visible, tabs switch within the same table context).
- **How chosen**: "Minimize friction within a single user workflow."
- **Problem essence**: The user's workflow is "select table → inspect schema → define rule → run → view results" — a loop. Separate pages lose "which table am I on" context on every navigation. Single-column wastes desktop screen space. Tabs switch within the same table context, and the URL still reflects state (`/tables/[name]?tab=rules`), preserving deep-link capability.
- **Tradeoffs**: Lose mobile-first simplicity (a two-column layout requires a collapsible drawer on mobile — known extra work). Tab state must be persisted to the URL, otherwise a page refresh resets to the default tab — a detail that must be handled explicitly.

---

### D#6: Sample API Strategy — First N Rows, Fixed limit=50 (Option A)

- **Decision**: `GET /tables/{name}/sample` returns the first 50 rows of the table (no random sampling, no offset parameter). Shared by both the LLM context and the UI preview.
- **Why it matters**: Affects prompt token cost (larger samples = higher cost) and LLM rule quality (unrepresentative samples can lead to wrong rules).
- **Options considered**:
  - Option A: Fixed limit=50, shared endpoint.
  - Option B: Random sampling (`TABLESAMPLE` or `ORDER BY random()`) — more representative, but non-deterministic (breaks caching).
  - Option C: Separate endpoints for LLM and UI (more flexible, but more complex).
- **How chosen**: "Simple to implement + reproducible (cache-friendly) + 50 rows is sufficient for LLM."
- **Problem essence**: The MVP's seed data is small; the first 50 rows will cover most patterns. `ORDER BY random()` is slow on large tables (full scan) and non-deterministic, breaking hash-based caching. The difference in rule quality between LLM seeing 50 rows vs. 500 rows is much smaller than the difference caused by how well the prompt is written — sample size is not the bottleneck.
- **Tradeoffs**: Lose sampling representativeness rigor (if the table has strong ordering bias — e.g., sorted by `created_at` — the LLM only sees the oldest data). Lose the ability to paginate through more data in the UI (not shown in the MVP; can be added later with an `offset` param).

---

### D#7: Structured Output — Anthropic Tool Use (Option A)

- **Decision**: Use Anthropic Tool Use, defining a `propose_rules` tool with a JSON Schema `input_schema`. The LLM is forced to return structured output via a tool call. Pydantic validates the result again on the backend.
- **Why it matters**: This is the foundation of "LLM output is stable and parseable." Without structured output, the LLM occasionally returns markdown-wrapped JSON or adds explanatory prose, causing parse failures.
- **Options considered**:
  - Option A: Tool Use (Anthropic's officially recommended structured-output approach).
  - Option B: Prompt-level "respond with JSON" instruction + post-hoc JSON extraction (brittle; 5–10% failure rate).
  - Option C: Use `instructor` or `outlines` library for retry/repair (adds a dependency).
- **How chosen**: "LLM output stability + first-class SDK integration + no additional dependencies."
- **Problem essence**: The degree to which LLM output is "structured" is the foundation of the entire pipeline's reliability. Prompt-based JSON output works for simple cases, but as soon as the schema gets complex (nested structures, enums, optional fields), the LLM introduces trailing commas, extra explanations, or misspelled field names. Tool use pushes the schema into the model's sampling stage, fundamentally reducing error rates. Pydantic re-validation is still necessary, because tool use does not guarantee semantic correctness (e.g., a valid enum value that violates business logic).
- **Tradeoffs**: Lose "prompt is pure text, easy to read in a markdown file" simplicity — the tool schema is an additional artifact to maintain. Tool use also makes provider-switching harder (OpenAI function calling uses a different format), but this was decided in D#0-a.

---

### D#8: Env Vars and Connection — Supabase Session Pooler + `backend/.env.example` (Option A)

- **Decision**: `DATABASE_URL` uses Supabase Session Pooler (port 5432, IPv4-compatible, persistent connections). `.env.example` lives in the `backend/` directory.
- **Why it matters**: The MVP runs locally while Supabase is in the cloud. The IPv4/IPv6 and connection pool mode directly affects whether the connection succeeds at all.
- **Options considered**:
  - Option A: Session Pooler (port 5432) — IPv4-friendly, persistent connections, ORM-compatible.
  - Option B: Transaction Pooler (port 6543) — lighter, but incompatible with prepared statements; psycopg3's default behavior will break.
  - Option C: Direct connection (port 5432) — requires IPv6 support; fails on some local networks.
- **How chosen**: "Works reliably in common dev environments (including macOS + home networks)."
- **Problem essence**: Supabase provides three connection endpoints with different pooling behavior and IPv4/IPv6 support. Transaction Pooler is incompatible with prepared statements — psycopg3 uses them by default, producing obscure errors like `prepared statement "__asyncpg_stmt_X__" already exists` that are hard to google. Session Pooler is the safe default for ORM workloads.
- **Tradeoffs**: Lose the Transaction Pooler's high connection density for serverless deployments (the MVP doesn't run on serverless). Session Pooler costs more under high concurrency, but MVP traffic is nowhere near that threshold.

---

### D#9: Frontend API Client — TanStack Query + Hand-Written TypeScript Interfaces

- **Decision**: Frontend uses TanStack Query (react-query) for all server state (fetch, cache, refetch, loading state). TypeScript types are written by hand, not auto-generated from OpenAPI.
- **Why it matters**: Determines the writing style of all frontend data-fetching code and the consistency of loading/error states.
- **Options considered**:
  - Hand-written TanStack Query + hand-written types (chosen).
  - SWR + hand-written types (similar capability; TanStack Query has a larger ecosystem).
  - OpenAPI client generation (most rigorous, but over-engineered for a 3-day MVP; FastAPI's OpenAPI schema changes frequently, generating noise).
  - Raw `fetch` + `useEffect` (reinventing the wheel).
- **How chosen**: "Built-in server state cache/retry + no codegen step + manageable manual type sync cost."
- **Problem essence**: Every API call in the MVP has three states: loading, error, success. Managing these with manual `useState` requires the same boilerplate in every component. TanStack Query handles all of this with one `useQuery` call, and includes cache invalidation out of the box — exactly what "click Run → wait → Results tab auto-refreshes" needs. Hand-written types will occasionally drift from the backend, but with only ~10 endpoints over 3 days, the risk is manageable.
- **Tradeoffs**: Lose "backend schema change automatically reflected in frontend" type safety (must be covered by code review and integration tests). TanStack Query adds one learning surface (though it is not complex).

---

### D#10: Error Handling — Backend Error Envelope + Full Frontend Error Component (Option C)

- **Decision**:
  - **Backend**: All 4xx/5xx errors return `{ "error": { "code": string, "user_message": string, "technical_detail": string } }`.
  - **Frontend**: A shared `<ErrorState>` component displays "human-readable title + bullet-list of possible causes + retry button." All frontend error fallbacks use this component.
- **Why it matters**: Error experience is an explicit exhibit for the "Product Thinking" evaluation criterion, and the most likely place non-technical users get stuck.
- **Options considered**:
  - Option A: HTTP status + plain text message (simple, but hard for frontend to customize).
  - Option B: Backend envelope, frontend only renders `user_message` (adequate but minimal).
  - Option C: Backend envelope + full frontend error component with possible causes and retry (most work, but matches the "non-technical user" principle).
- **How chosen**: "Align with Product Thinking and Error Handling evaluation criteria."
- **Problem essence**: The target user is a domain expert, not an engineer, but there are many failure modes — LLM timeout, JSON parse failure, DB connection drop, GE crash. Displaying "Error: 500" leaves the user completely stuck. The envelope design lets the backend simultaneously return a message for the user and technical detail for the developer, and the frontend can customize the UI based on the error `code`. The full error component forces us to think through "what are the possible causes?" for every error scenario — that process itself is the Product Thinking demonstration.
- **Tradeoffs**: Lose "fast ship" — the envelope must be applied to every endpoint, the frontend component must be designed, and every `code` needs a `user_message` and possible causes written. Estimated extra time: 1–2 hours. But this is exactly where the evaluation score differentiates.

---

## Section 2: Decision Points (Open Decisions)

**(Empty — all decisions are resolved in the Decision Log.)**

If a new architectural choice arises during implementation, stop, add a new Decision Point here, wait for the user's answer, then continue.

---

## Section 3: Specification

### 3.1 Problem Restatement

We are building a tool that lets non-technical users (domain experts) define and run data quality rules. Users interact via a chat-style interface; the LLM translates natural language or schema observations into Great Expectations rules, which are run against Postgres data, and the UI displays red/yellow/green results.

Day 1's core goal is to **build a working skeleton**: both services start, the backend connects to the DB, lists tables, returns schema and sample data, and the frontend renders a basic Table Explorer. By end of Day 1, a user opening `localhost:3000` can select a table, see its schema and first 50 rows in the Schema tab, and see placeholder content in the Rules and Results tabs.

**Ambiguities and assumptions**:
- Day 1 involves no LLM calls or GE execution — those belong to Day 2. Prompt templates are written and committed, but not invoked.
- Minimum demo bar: left sidebar + right Schema tab functional = Day 1 complete.

---

### 3.2 Affected Surface Area (File Paths)

#### Backend (`backend/`)

```
backend/
├── pyproject.toml                       # uv-managed; add dependencies here
├── .env.example                         # D#8: template without secrets
├── .env                                 # D#8: developer's local values (gitignored)
├── app/
│   ├── __init__.py
│   ├── main.py                          # FastAPI entry point; CORS; router registration; global exception handler
│   ├── config.py                        # Pydantic Settings; single source of truth for env vars
│   ├── api/
│   │   ├── __init__.py
│   │   ├── health.py                    # GET /health
│   │   └── tables.py                    # GET /tables, GET /tables/{name}, GET /tables/{name}/sample
│   ├── services/
│   │   ├── __init__.py
│   │   └── db.py                        # SQLAlchemy engine, session factory, schema inspection helpers
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── tables.py                    # Pydantic: TableInfo, ColumnInfo, TableDetail, SampleResponse
│   │   └── errors.py                    # Pydantic: ErrorEnvelope (D#10)
│   └── prompts/
│       ├── rule_from_schema.md          # Template committed, not called in Day 1
│       └── rule_from_nl.md             # Template committed, not called in Day 1
├── db/
│   ├── schema.sql                       # public schema: policyholders, policies, claims
│   ├── seed.sql                         # Clean sample data (D#2)
│   └── 001_dq_schema.sql                # dq schema: rules, runs, run_results tables
└── tests/
    ├── __init__.py
    ├── test_health.py
    └── test_tables.py
```

#### Frontend (`frontend/`)

```
frontend/
├── package.json
├── next.config.ts
├── tailwind.config.ts
├── tsconfig.json
├── .env.local.example                   # NEXT_PUBLIC_API_URL=http://localhost:8000
├── app/
│   ├── layout.tsx                       # Root layout: wraps with TanStack Query Provider
│   ├── page.tsx                         # Home page: redirects to /tables
│   ├── globals.css                      # Tailwind v4 entry
│   ├── tables/
│   │   ├── layout.tsx                   # Two-column layout: left sidebar + right children (D#5)
│   │   ├── page.tsx                     # /tables: right area shows empty state "Select a table"
│   │   └── [name]/
│   │       └── page.tsx                 # /tables/[name]: renders TableTabs[Schema|Rules|Results]
│   └── providers.tsx                    # TanStack QueryClient configuration (D#9)
├── components/
│   ├── TableSidebar.tsx                 # Left-side table list
│   ├── TableTabs.tsx                    # Schema/Rules/Results tab switcher (URL search param persistence)
│   ├── SchemaView.tsx                   # Schema tab content: column list + sample data preview
│   ├── ErrorState.tsx                   # D#10: full error component
│   └── LoadingSkeleton.tsx              # Loading skeleton
├── lib/
│   ├── api.ts                           # fetch wrapper; handles error envelope
│   └── queries.ts                       # TanStack Query hooks: useTables, useTableSchema, useTableSample
└── types/
    └── api.ts                           # Hand-written TypeScript interfaces matching backend responses
```

#### Docs (`docs/`)

```
docs/
├── day1-plan.md                         # This document
└── ai-tools-usage.md                    # AI tool usage log (updated daily from Day 1 onward)
```

---

### 3.3 Design Details

#### 3.3.1 Backend

**`app/config.py`** (Pydantic Settings — sole env var entry point)

Required fields:
- `DATABASE_URL: str`
- `LLM_PROVIDER: str = "anthropic"`
- `LLM_MODEL: str = "claude-sonnet-4-6"`
- `ANTHROPIC_API_KEY: str` (validated on startup even though Day 1 doesn't call the LLM)
- `CORS_ORIGINS: list[str] = ["http://localhost:3000"]` (parsed from comma-separated string)

Use `pydantic-settings` with `model_config = SettingsConfigDict(env_file=".env", extra="ignore")`. Provide a module-level singleton `settings = Settings()`. **No other file may read `os.environ` directly.**

**`app/services/db.py`**

- Create `create_engine(settings.DATABASE_URL, pool_pre_ping=True, future=True)`.
- Provide `get_session()` context manager and `get_db()` FastAPI dependency (yields a Session).
- Provide `list_public_tables() -> list[TableInfo]`: queries `information_schema.tables` with `table_schema='public' AND table_type='BASE TABLE'`; returns objects with `name`, `row_count`, `column_count`.
- Provide `get_table_columns(name: str) -> list[ColumnInfo]`: queries `information_schema.columns`; returns `name`, `data_type`, `is_nullable`, `column_default`.
- Provide `sample_table(name: str, limit: int = 50) -> list[dict]`: executes `SELECT * FROM public."{name}" LIMIT {limit}`. **Must whitelist-check `name`** against `list_public_tables()` results before executing to prevent SQL injection.

**`app/api/tables.py`**

```
GET /tables               → list[TableInfo]
GET /tables/{name}        → TableDetail (includes columns)
GET /tables/{name}/sample → SampleResponse { rows: list[dict[str, Any]], limit: 50 }
```

All endpoints use `def` (D#4). Obtain session via `Depends(get_db)`.

**`app/main.py`**

- Create the FastAPI app.
- Add `CORSMiddleware` using `settings.cors_origins_list`.
- Register routers: `health`, `tables` (rules and results are Day 2 — do not register yet).
- Register **global exception handlers** (D#10):
  - `HTTPException` handler → wraps as `{"error": {"code": ..., "user_message": ..., "technical_detail": ...}}`.
  - Catch-all `Exception` handler → `code="INTERNAL_ERROR"`, `user_message="An unexpected error occurred. Please try again."`, `technical_detail=traceback.format_exc()` (dev mode).
- `/health` returns `{"status": "ok", "llm_model": settings.LLM_MODEL}`.

**Error code table (Day 1 scope)**:
- `TABLE_NOT_FOUND` — user_message: "The requested table could not be found."
- `DATABASE_UNAVAILABLE` — user_message: "Unable to connect to the database. Please try again shortly."
- `INTERNAL_ERROR` — user_message: "An unexpected error occurred. Please try again."

**`db/schema.sql`** — Personal insurance domain

```sql
-- public schema (business data)
CREATE TABLE public.policyholders (
  id SERIAL PRIMARY KEY,
  national_id VARCHAR(10) UNIQUE NOT NULL,    -- national ID number (format: 1 letter + 9 digits)
  full_name VARCHAR(100) NOT NULL,
  birth_date DATE NOT NULL,
  gender VARCHAR(1) NOT NULL,                 -- 'M' or 'F'
  email VARCHAR(200),
  phone VARCHAR(20),
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE public.policies (
  id SERIAL PRIMARY KEY,
  policy_number VARCHAR(20) UNIQUE NOT NULL,
  holder_id INTEGER REFERENCES public.policyholders(id),
  product_type VARCHAR(30) NOT NULL,          -- 'life', 'health', 'accident'
  coverage_amount NUMERIC(14,2) NOT NULL,
  premium_monthly NUMERIC(10,2) NOT NULL,
  effective_date DATE NOT NULL,
  expiry_date DATE NOT NULL,
  status VARCHAR(10) NOT NULL,                -- 'active', 'lapsed', 'terminated'
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
  status VARCHAR(15) NOT NULL,                -- 'pending', 'approved', 'rejected', 'paid'
  rejection_reason TEXT,
  created_at TIMESTAMP DEFAULT NOW()
);
```

**`db/seed.sql`** — Pure clean data (D#2), ~30–80 rows per table. All values comply with business logic: `national_id` format is valid, `expiry_date` is after `effective_date`, `claim_amount` does not exceed `coverage_amount`, no dates in the future.

**`db/001_dq_schema.sql`** (created in Day 1; populated in Day 2):

```sql
CREATE SCHEMA IF NOT EXISTS dq;

CREATE TABLE dq.rules (
  id SERIAL PRIMARY KEY,
  table_name VARCHAR(100) NOT NULL,
  expectation_type VARCHAR(100) NOT NULL,
  kwargs JSONB NOT NULL,
  description TEXT,
  source VARCHAR(20) NOT NULL,                -- 'ai_schema', 'ai_nl', 'user'
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE dq.runs (
  id SERIAL PRIMARY KEY,
  table_name VARCHAR(100) NOT NULL,
  status VARCHAR(20) NOT NULL,                -- 'running', 'success', 'failed'
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
  unexpected_sample JSONB,                    -- 1–3 violating sample values
  observed_value JSONB,
  raw_result JSONB
);
```

---

#### 3.3.2 Frontend

**`app/providers.tsx`**

Exports a `Providers` component wrapping `QueryClientProvider`. `QueryClient` configured with `defaultOptions.queries.retry: 1` and `staleTime: 30_000`.

**`app/layout.tsx`**

Wraps with `<Providers>`. Sets global font and metadata.

**`app/tables/layout.tsx`** (D#5 two-column layout)

```tsx
<div className="flex h-screen">
  <aside className="w-72 border-r"><TableSidebar /></aside>
  <main className="flex-1 overflow-auto">{children}</main>
</div>
```

**`app/tables/[name]/page.tsx`**

- Reads `name` from URL params and `tab` from `useSearchParams` (default: `schema`).
- Renders `<TableTabs name={name} activeTab={tab} />`.

**`components/TableTabs.tsx`**

- Three tabs: Schema / Rules / Results.
- On tab switch, calls `router.replace(?tab=...)` to persist state in the URL.
- Day 1 content:
  - Schema tab → `<SchemaView />`
  - Rules tab → placeholder "Rule management coming in Day 2"
  - Results tab → placeholder "Results dashboard coming in Day 2"

**`components/SchemaView.tsx`**

- Uses `useTableSchema(name)` and `useTableSample(name)` queries.
- Top half: column list (name, type, nullable, default).
- Bottom half: first 50 rows rendered as an HTML table (show max 10 columns; overflow scrolls horizontally).
- Loading state: `<LoadingSkeleton />`.
- Error state: `<ErrorState />` (D#10).

**`components/ErrorState.tsx`**

Props: `error: ApiError`, `onRetry?: () => void`.

UI structure:
```
[Icon] Title (mapped from error.code to a human-readable heading)
       error.user_message

       Possible causes:
       • Cause 1 (2–3 bullets based on error.code)
       • Cause 2

       [Retry button] (rendered only if onRetry is provided)

       <details>Technical detail (collapsible; shows technical_detail)</details>
```

**`lib/api.ts`**

```typescript
const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  code: string;
  user_message: string;
  technical_detail: string;
}

export async function apiFetch<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(/* constructed from body.error */);
  }
  return res.json();
}
```

**`lib/queries.ts`**

```typescript
export const useTables = () =>
  useQuery({ queryKey: ["tables"], queryFn: () => apiFetch<TableInfo[]>("/tables") });

export const useTableSchema = (name: string) =>
  useQuery({ queryKey: ["tables", name], queryFn: () => apiFetch<TableDetail>(`/tables/${name}`) });

export const useTableSample = (name: string) =>
  useQuery({ queryKey: ["tables", name, "sample"], queryFn: () => apiFetch<SampleResponse>(`/tables/${name}/sample`) });
```

**`types/api.ts`**

Hand-written interfaces matching backend Pydantic schemas. Naming convention: same as backend class names (`TableInfo`, `ColumnInfo`, `TableDetail`, `SampleResponse`, `ApiError`).

---

#### 3.3.3 Prompts (Committed in Day 1, Not Called Until Day 2)

**`backend/app/prompts/rule_from_schema.md`** contains:
- Role: data quality expert in the personal insurance domain.
- Input variables: `{{table_name}}`, `{{columns_json}}`, `{{sample_rows_json}}`.
- Task: infer potential data quality issues from schema and business logic (per D#2) and propose 5–10 rules.
- Must use the `propose_rules` tool (D#7).

**`backend/app/prompts/rule_from_nl.md`** contains:
- Input variables: `{{table_name}}`, `{{columns_json}}`, `{{user_description}}`.
- If the description is too vague, return `needs_clarification` with a follow-up question.

---

### 3.4 Risks and Reversibility

| Risk | Severity | Reversibility | Mitigation |
|------|----------|---------------|------------|
| Supabase connection fails on some networks | High | Easy (swap connection string) | D#8 chose Session Pooler; README documents fallback |
| Sync SQLAlchemy blocks thread during large table sample | Medium | Medium (requires async rewrite) | Sample capped at 50 rows + query timeout; won't trigger at MVP traffic |
| Unexpected Supabase-internal system tables appear in `public` | Medium | Easy (add to filter list) | `list_public_tables` excludes known Supabase internal table names |
| pydantic-settings `extra="ignore"` silently hides env var typos | Low | Easy | Code review: check each var against `.env.example` |
| Global exception handler swallows stack traces during debugging | Medium | Easy | Include `traceback.format_exc()` in `technical_detail` (dev mode) |
| `ErrorState` has no fallback for unknown error codes | Low | Easy | Provide a default mapping; unknown codes render raw `user_message` |

**Hardest decisions to reverse**:
- **D#4 (full sync)**: Migrating to async requires changing all service and endpoint signatures — the highest effort change.
- **D#3 (schema separation)**: Reverting to all-public requires changing all SQL and dependency logic, but is scoped to the backend.

---

### 3.5 Rollout Phases (With Verification Steps)

> Each phase must pass its Verification step before the next phase begins.

#### Phase 1: Infrastructure and Skeleton (est. 2–3 hours)

Tasks:
1. `backend/pyproject.toml` — initialize with uv; add fastapi, uvicorn, sqlalchemy, psycopg[binary], pydantic-settings, ruff, pytest, pytest-mock, anthropic, great-expectations.
2. `backend/.env.example` and `backend/app/config.py`.
3. `backend/app/main.py` — FastAPI app with `/health`, CORS, global exception handler skeleton.
4. `frontend/` — scaffold with `npx create-next-app@latest frontend --typescript --app --tailwind --eslint`.
5. `frontend/.env.local.example` with `NEXT_PUBLIC_API_URL=http://localhost:8000`.

**Verification**:
- `uv run uvicorn app.main:app --reload --port 8000` starts successfully.
- `curl http://localhost:8000/health` returns `{"status":"ok","llm_model":"claude-sonnet-4-6"}`.
- `npm run dev` starts successfully; `http://localhost:3000` shows the Next.js default page.

#### Phase 2: Database and Schema Inspection (est. 2–3 hours)

Tasks:
1. Create a Supabase project; obtain the Session Pooler `DATABASE_URL`; fill in `backend/.env`.
2. Run `db/schema.sql`, `db/seed.sql`, `db/001_dq_schema.sql` in Supabase SQL editor.
3. Implement three helpers in `services/db.py`: `list_public_tables`, `get_table_columns`, `sample_table`.
4. Implement three endpoints in `api/tables.py`.
5. Write `tests/test_tables.py` (mocked session).

**Verification**:
- `curl http://localhost:8000/tables` returns 3 tables (`policyholders`, `policies`, `claims`).
- `curl http://localhost:8000/tables/policyholders` returns a column list.
- `curl http://localhost:8000/tables/policyholders/sample` returns `rows` with seed data.
- `curl http://localhost:8000/tables/nonexistent` returns `{"error":{"code":"TABLE_NOT_FOUND",...}}` with HTTP 404.
- `uv run pytest` passes.

#### Phase 3: Frontend Table Explorer (est. 3–4 hours)

Tasks:
1. Install `@tanstack/react-query`.
2. Create `app/providers.tsx`; update `app/layout.tsx`.
3. Create `app/tables/layout.tsx` (two-column), `app/tables/page.tsx` (empty state), `app/tables/[name]/page.tsx`.
4. Create all components: `TableSidebar`, `TableTabs`, `SchemaView`, `ErrorState`, `LoadingSkeleton`.
5. Create `lib/api.ts`, `lib/queries.ts`, `types/api.ts`.

**Verification**:
- Opening `http://localhost:3000` auto-redirects to `/tables`.
- Left sidebar lists 3 tables.
- Clicking `policyholders` sets URL to `/tables/policyholders?tab=schema`; right area shows column list and sample rows.
- Switching to Rules tab sets URL to `?tab=rules`; shows placeholder. Refreshing the page stays on Rules tab.
- Stopping the backend and refreshing shows `<ErrorState>` (human-readable title, possible causes, retry button). Restarting backend and clicking retry restores the view.

#### Phase 4: Prompt Templates and Docs Skeleton (est. 1 hour)

Tasks:
1. Write `backend/app/prompts/rule_from_schema.md` and `rule_from_nl.md` (ready to call in Day 2).
2. Create `docs/ai-tools-usage.md` and log the Day 1 AI tool usage.
3. Update README with a "5-minute demo" quick-start section.

**Verification**:
- Both prompt templates pass human review: role, input variables, and output format are all present.
- Following the README, a fresh clone can reproduce the Phase 3 demo within 5 minutes.

---

### 3.6 Day 2 Entry Conditions

All of the following must be true before Day 2 begins:

- [ ] Backend endpoints `/health`, `/tables`, `/tables/{name}`, `/tables/{name}/sample` all working.
- [ ] Frontend Table Explorer fully interactive (error state, tab switching, URL persistence).
- [ ] `dq` schema created; `dq.rules`, `dq.runs`, `dq.run_results` tables exist (ready for Day 2 writes).
- [ ] Prompt templates committed.
- [ ] `docs/ai-tools-usage.md` has at least one entry.
- [ ] README 5-minute demo is reproducible.
