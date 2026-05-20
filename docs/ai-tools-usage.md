# AI Tools Usage Log

This document records how AI coding tools were used throughout the development of the AI-Powered Data Quality Assistant.

---

## Development Workflow

Each day follows a four-agent loop applied to every implementation phase:

```
architect agent  →  implementer agent  →  reviewer agent  →  /commit skill
      ↑                                                              |
      └──────────────── next phase ─────────────────────────────────┘
```

1. **architect agent** — Reads the codebase and CLAUDE.md, surfaces decision points to the developer, waits for answers, then produces a `docs/dayN-plan.md` with a Decision Log and Specification. Does not write production code.
2. **implementer agent** — Executes the Specification phase by phase. Runs the verification step defined in the Specification before reporting a phase complete. Escalates (does not silently resolve) any decision the Specification did not cover.
3. **reviewer agent** — Audits the implemented phase against the Specification and Decision Log. Checks that verification actually ran, that no unapproved decisions were smuggled in, and that the Implementation Note is honest. Issues a pass/fail verdict.
4. **`/commit` skill** — Stages and commits the phase's changes with a structured commit message once the reviewer passes.

This loop creates a traceable chain: every line of code is linked to a Specification entry, every Specification entry is linked to a Decision Log item, and every Decision Log item records the tradeoff that was accepted.

---

## Day 1 — Foundation & Core AI Integration

### Step 1 — Architecture Planning (architect agent)

- **Tool**: Claude Code (claude-sonnet-4-6) via **architect agent**
- **Task**: Translate the Day 1 scope in `CLAUDE.md` into an actionable plan. The architect surfaced 10 decision points (D#0-a through D#10), presented options with tradeoffs, and waited for developer answers before writing the Specification.
- **Key decisions resolved through dialogue**:
  - D#7: Anthropic Tool Use (not prompt-level JSON) for structured LLM output — prevents parse failures on complex schemas
  - D#8: Supabase Session Pooler over Transaction Pooler — Transaction Pooler breaks psycopg3's prepared statements
  - D#9: TanStack Query for frontend server state — eliminates per-component loading/error boilerplate
  - D#10: Full error envelope (`code` + `user_message` + `technical_detail`) — required for non-technical user UX
- **Outcome**: `docs/day1-plan.md` produced with 15 Decision Log entries (each with Problem Essence + Tradeoffs) and a 4-phase Specification
- **Notable**: The architect identified the pydantic-settings v2 CORS_ORIGINS list-parsing incompatibility as a known risk *before* implementation — it was flagged in the Decision Log and the implementer handled it with a `cors_origins_list` property workaround

### Step 2a — Phase 1 Implementation (implementer agent)

- **Tool**: Claude Code (claude-sonnet-4-6) via **implementer agent**
- **Task**: Backend skeleton (FastAPI app, Pydantic Settings config, CORS middleware, `/health` endpoint, error envelope schemas) + Next.js 16 frontend scaffold
- **Outcome**: All Phase 1 verification checks passed — uvicorn starts, `/health` returns correct JSON, `npm run dev` starts
- **Notable**: Agent caught a `psyccopg` (3 c's) typo in `.env` that would have caused a SQLAlchemy `NoSuchModuleError` at engine init

### Step 2b — Phase 2 Implementation (implementer agent)

- **Tool**: Claude Code (claude-sonnet-4-6) via **implementer agent**
- **Task**: DB schema files (`schema.sql`, `seed.sql`, `001_dq_schema.sql`), `services/db.py`, `api/tables.py`, `tests/test_tables.py`
- **Outcome**: 5 unit tests passed (mocked DB); all 4 live curl verifications passed against Supabase
- **Notable**: Agent used `pg_stat_user_tables.n_live_tup` for approximate row counts (one query for all tables, no per-table `COUNT(*)`) — a performance choice appropriate for display purposes

### Step 2c — Phase 3 Implementation (implementer agent)

- **Tool**: Claude Code (claude-sonnet-4-6) via **implementer agent**
- **Task**: Frontend Table Explorer — TanStack Query provider, two-column layout, `TableSidebar`, `TableTabs`, `SchemaView`, `ErrorState`, `LoadingSkeleton`, `lib/api.ts`, `lib/queries.ts`, `types/api.ts`
- **Outcome**: `npm run build` passed cleanly; dev server starts; zero TypeScript errors
- **Notable**: Next.js 16 breaking change — `params` is now a `Promise<{name: string}>` in page components, and `useSearchParams` requires a `<Suspense>` boundary or the production build fails. The Specification was written against the Next.js 14 API. The implementer adapted to the correct Next.js 16 pattern (`useParams()` hook + Suspense wrapper) without changing the architectural intent.

### Step 2d — Phase 4 Implementation (implementer agent)

- **Tool**: Claude Code (claude-sonnet-4-6) via **implementer agent**
- **Task**: LLM prompt templates (`rule_from_schema.md`, `rule_from_nl.md`), this usage log, root `README.md`
- **Outcome**: Both prompt templates created with role, input variables, tool-use instructions, output schema, and insurance-domain few-shot examples; README created with 5-minute demo quick-start and dirty-data demo SQL
- **Notable**: Prompt templates explicitly instruct the LLM that the tool call is the *only* acceptable output form. This prevents the LLM from prepending explanation text, which would not break JSON parsing but would indicate the model misunderstood the instruction — an early signal of prompt regression.

### Step 3 — Phase Review (reviewer agent)

- **Tool**: Claude Code (claude-sonnet-4-6) via **reviewer agent**
- **Task**: Audit each completed phase against `docs/day1-plan.md` — verify that the Specification was followed, verification steps actually ran, and no unapproved architectural decisions were introduced
- **Outcome**: Phases reviewed; Implementation Notes confirmed accurate
- **Process value**: Reviewer catches the gap between "implementer says it passed" and "it actually passed" — particularly important for the Next.js 16 adaptation in Phase 3, where the reviewer confirmed the behavioral outcome matched the spec even though the code pattern differed

### Step 4 — Commit (\/commit skill)

- **Tool**: Claude Code `/commit` skill
- **Task**: Stage and commit each phase's changes with a structured commit message linking to the phase and Specification
- **Process value**: Each commit corresponds to exactly one verified phase — the git log mirrors the implementation plan, making it easy to bisect regressions or review scope
