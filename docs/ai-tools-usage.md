# AI Tools Usage Log

This document records how AI coding tools were used throughout the development of the AI-Powered Data Quality Assistant.

---

## Development Workflow

Each day follows an agent loop applied to every implementation phase. The core path is linear, but the reviewer can send work back to the implementer before a commit is allowed:

```
architect agent  →  implementer agent  →  reviewer agent
      ↑                    ↑                     |
      |                    |           issues found?
      |                    |                ↓ yes
      |                    └── implementer agent (fix)
      |                                     ↓
      |                          reviewer agent (re-audit)
      |                                     ↓ pass
      |                            /commit skill
      └──────────────── next phase ──────────┘
```

1. **architect agent** — Reads the codebase and CLAUDE.md, surfaces decision points to the developer, waits for answers, then produces a `docs/dayN-plan.md` with a Decision Log and Specification. Does not write production code.
2. **implementer agent** — Executes the Specification phase by phase. Runs the verification step defined in the Specification before reporting a phase complete. Escalates (does not silently resolve) any decision the Specification did not cover.
3. **reviewer agent** — Audits the implemented phase against the Specification and Decision Log. Checks that verification actually ran, that no unapproved decisions were smuggled in, and that the Implementation Note is honest. Issues a pass/fail verdict with specific findings.
4. **implementer agent (fix round)** — If the reviewer issues a conditional pass or explicit fail, the implementer is re-invoked with the reviewer's findings as input. It fixes only what was flagged — no scope creep.
5. **reviewer agent (re-audit)** — Re-audits the fix. Issues a final verdict before the commit is allowed.
6. **`/commit` skill** — Stages and commits the phase's changes with a structured commit message once the reviewer passes.

This loop creates a traceable chain: every line of code is linked to a Specification entry, every Specification entry is linked to a Decision Log item, and every Decision Log item records the tradeoff that was accepted. The reviewer → implementer correction cycle ensures that "implementer says it passed" and "it actually passed" are not conflated.

### Tooling — codebase-memory MCP (token efficiency)

Code discovery during development went through a **codebase-memory MCP server** instead of reading whole files into the agent's context. The server indexes the repository into a queryable knowledge graph, so the agent retrieves only the slice it needs for a given task:

- `search_graph` / `query_graph` — locate a function, class, route, or symbol by name or pattern.
- `get_code_snippet` — pull a single function's source by qualified name, rather than reading the entire file it lives in.
- `trace_path` — follow call chains / data flow across modules (e.g. "who calls this", "where does this value come from").
- `get_architecture` — get a structural overview without opening every file.

**Why it matters**: as the codebase grew across the three days, "read the file to find X" pulls progressively more irrelevant tokens into context on every lookup. Fetching targeted symbols and call chains from the graph keeps each query small, which lowers token cost per task and leaves more of the context budget for actual reasoning and review. A `SessionStart` hook enforces this — code-discovery prompts route to the graph tools first and fall back to plain file reads only for non-code or text content.

---

## Day 1 — Foundation & Core AI Integration

### Architecture Planning (architect agent)

- **Tool**: Claude Code (claude-sonnet-4-6) via **architect agent**
- **Task**: Translate the Day 1 scope in `CLAUDE.md` into an actionable plan. The architect surfaced 10 decision points (D#0-a through D#10), presented options with tradeoffs, and waited for developer answers before writing the Specification.
- **Key decisions resolved through dialogue**:
  - D#7: Anthropic Tool Use (not prompt-level JSON) for structured LLM output — prevents parse failures on complex schemas
  - D#8: Supabase Session Pooler over Transaction Pooler — Transaction Pooler breaks psycopg3's prepared statements
  - D#9: TanStack Query for frontend server state — eliminates per-component loading/error boilerplate
  - D#10: Full error envelope (`code` + `user_message` + `technical_detail`) — required for non-technical user UX
- **Outcome**: `docs/day1-plan.md` produced with 15 Decision Log entries (each with Problem Essence + Tradeoffs) and a 4-phase Specification
- **Notable**: The architect identified the pydantic-settings v2 CORS_ORIGINS list-parsing incompatibility as a known risk *before* implementation — it was flagged in the Decision Log and the implementer handled it with a `cors_origins_list` property workaround

---

### Phase 1 — Backend Skeleton + Frontend Scaffold

#### Implementation (implementer agent)

- **Tool**: Claude Code (claude-sonnet-4-6) via **implementer agent**
- **Task**: FastAPI app, Pydantic Settings config, CORS middleware, `/health` endpoint, error envelope schemas, Next.js 16 frontend scaffold with Tailwind
- **Outcome**: All Phase 1 verification checks passed — uvicorn starts, `/health` returns correct JSON, `npm run dev` starts
- **Notable**: Agent caught a `psyccopg` (3 c's) typo in `.env` that would have caused a SQLAlchemy `NoSuchModuleError` at engine init

#### Review (reviewer agent)

- **Tool**: Claude Code (claude-sonnet-4-6) via **reviewer agent**
- **Verdict**: Pass — verification steps confirmed to have run; no unapproved decisions; Implementation Note accurate

#### Commit (`/commit` skill)

- **Tool**: Claude Code `/commit` skill
- **Commit**: `feat(project): initialize monorepo with FastAPI backend and Next.js frontend`

---

### Phase 2 — Database and Schema Inspection

#### Implementation (implementer agent)

- **Tool**: Claude Code (claude-sonnet-4-6) via **implementer agent**
- **Task**: DB schema files (`schema.sql`, `seed.sql`, `001_dq_schema.sql`), `services/db.py`, `api/tables.py`, `tests/test_tables.py`
- **Outcome**: 5 unit tests passed (mocked DB); all 4 live curl verifications passed against Supabase
- **Notable**: Agent used `pg_stat_user_tables.n_live_tup` for approximate row counts (one query for all tables, no per-table `COUNT(*)`) — a performance choice appropriate for display purposes

#### Review (reviewer agent)

- **Tool**: Claude Code (claude-sonnet-4-6) via **reviewer agent**
- **Verdict**: Pass — live curl verifications confirmed; test coverage matched the Specification; no scope creep beyond Phase 2 boundaries

#### Commit (`/commit` skill)

- **Tool**: Claude Code `/commit` skill
- **Commit**: `feat(backend): implement Phase 2 database and schema inspection`

---

### Phase 3 — Frontend Table Explorer

#### Implementation (implementer agent)

- **Tool**: Claude Code (claude-sonnet-4-6) via **implementer agent**
- **Task**: TanStack Query provider, two-column layout, `TableSidebar`, `TableTabs`, `SchemaView`, `ErrorState`, `LoadingSkeleton`, `lib/api.ts`, `lib/queries.ts`, `types/api.ts`
- **Outcome**: `npm run build` passed cleanly; dev server starts; zero TypeScript errors
- **Notable**: Next.js 16 breaking change — `params` is now a `Promise<{name: string}>` in page components, and `useSearchParams` requires a `<Suspense>` boundary or the production build fails. The Specification was written against the Next.js 14 API. The implementer adapted to the correct Next.js 16 pattern (`useParams()` hook + Suspense wrapper) without changing the architectural intent.

#### Review (reviewer agent)

- **Tool**: Claude Code (claude-sonnet-4-6) via **reviewer agent**
- **Verdict**: Pass — reviewer confirmed that the behavioral outcome matched the Specification even though the code pattern differed from the Next.js 14 example in the spec. The adaptation was flagged as a valid in-scope implementation decision, not an unapproved architectural change.

#### Commit (`/commit` skill)

- **Tool**: Claude Code `/commit` skill
- **Commit**: `feat(frontend): implement Phase 3 Table Explorer`

---

### Phase 4 — Prompt Templates, Usage Log, README

#### Implementation (implementer agent)

- **Tool**: Claude Code (claude-sonnet-4-6) via **implementer agent**
- **Task**: LLM prompt templates (`rule_from_schema.md`, `rule_from_nl.md`), this usage log, root `README.md`
- **Outcome**: Both prompt templates created with role, input variables, tool-use instructions, output schema, and insurance-domain few-shot examples; README created with 5-minute demo quick-start and dirty-data demo SQL
- **Notable**: Prompt templates explicitly instruct the LLM that the tool call is the *only* acceptable output form. This prevents the LLM from prepending explanation text, which would not break JSON parsing but would indicate the model misunderstood the instruction — an early signal of prompt regression.

#### Review (reviewer agent)

- **Tool**: Claude Code (claude-sonnet-4-6) via **reviewer agent**
- **Verdict**: Pass — prompt templates confirmed to match the tool-use schema defined in D#7; README covers all Specification requirements; Implementation Notes honest

#### Commit (`/commit` skill)

- **Tool**: Claude Code `/commit` skill
- **Commit**: `docs(day1-phase4): add prompt templates, AI usage log, and README quick-start`

---

## Day 2 — Core Functionality

### Architecture Planning (architect agent)

- **Tool**: Claude Code (claude-sonnet-4-6) via **architect agent**
- **Task**: Translate the Day 2 scope in `CLAUDE.md` into an actionable plan. The architect surfaced 12 decision points (D#11–D#22), presented options with tradeoffs interactively via `AskUserQuestion`, and waited for developer answers before writing the Specification.
- **Key decisions resolved through dialogue**:
  - D#16: GE SQL Datasource over Pandas in-memory — production fidelity and "data never leaves the DB" security model
  - D#17: Synchronous blocking runs — GE execution < 2s at MVP scale; async complexity not justified
  - D#18: Three-state status (pass/fail/error) — distinguishes "fix your data" from "fix your rule" for non-technical users
  - D#19: Draft mode for Suggest — AI as collaborator, not overwriter; review-before-save trust model
  - D#21: One-shot NL clarification — stateless `from-nl` endpoint; chat history deferred to Day 3
  - D#22: Show duplicate suggestions with badge — transparent design over implicit filtering
- **Outcome**: `docs/day2-plan.md` produced with 12 Decision Log entries (D#11–D#22, each with Problem Essence + Tradeoffs) and a 6-phase Specification
- **Notable**: The architect flagged GE 1.x's SQL Datasource behavior as the highest-risk item before implementation — specifically that `partial_unexpected_list` and `exception_info.raised_exception` behave differently from the Pandas backend and would require special handling in `ge_engine.py`

---

### Phase 1 — Schemas + DB Migration

#### Implementation (implementer agent)

- **Tool**: Claude Code (claude-sonnet-4-6) via **implementer agent**
- **Task**: `db/002_run_results_status.sql`, `app/schemas/rules.py`, `app/schemas/runs.py`, `app/services/rules_store.py`
- **Outcome**: Three-state `status VARCHAR(10)` column added to `dq.run_results`; Pydantic models matched the existing `001_dq_schema.sql` columns without introducing an ORM layer; `rules_store.py` CRUD functions implemented with raw SQLAlchemy `text()` queries
- **Notable**: The `ALTER TABLE` migration used `DEFAULT 'pass'` so that any pre-existing rows in `dq.run_results` would not violate the NOT NULL constraint — a defensive choice since the migration runs against a live Supabase database where some rows may already exist. The D#22 `already_saved` comparison uses `json.dumps(kwargs, sort_keys=True)` to canonicalize JSONB before comparing — prevents false negatives from key-order differences in the same logical kwargs object.

#### Review (reviewer agent)

- **Tool**: Claude Code (claude-sonnet-4-6) via **reviewer agent**
- **Verdict**: Pass — psql verification of `status` column confirmed; `test_rules_store_crud` passed; Pydantic models round-trip to the DB schema without friction; no unapproved decisions

#### Commit (`/commit` skill)

- **Tool**: Claude Code `/commit` skill
- **Commit**: `feat(backend): implement Day 2 Phase 1 — schemas, rules store, and DB migration`

---

### Phase 2 — AI Generator + Rules API

#### Implementation (implementer agent)

- **Tool**: Claude Code (claude-sonnet-4-6) via **implementer agent**
- **Task**: `app/services/ai_generator.py` (Anthropic Tool Use integration), `app/api/rules.py` (six endpoints), register `rules_router` in `main.py`, `tests/test_rules.py`
- **Outcome**: All six `/rules` endpoints functional; Anthropic Tool Use forces structured output; `POST /rules/suggest` correctly marks already-saved rules; `POST /rules/from-nl` returns discriminated union (`{type: "rule"}` or `{type: "clarification"}`)
- **Prompt engineering — Tool Use schema design**: Two distinct forcing strategies were used for the two LLM call paths:
  - `suggest_rules`: `tool_choice={"type": "tool", "name": "propose_rules"}` — forces exactly one tool call to the named tool, eliminating the case where the model produces a text reply instead of structured output
  - `rule_from_nl`: `tool_choice={"type": "any"}` — allows the model to choose between `propose_rule` and `request_clarification`; the model selects based on whether the description is specific enough to translate. This implements D#21's one-shot clarification UX without any stateful session tracking.
- **Pydantic two-pass validation**: Tool Use guarantees the JSON schema is structurally valid, but not semantically valid (e.g., `expectation_type` could be a misspelled string that GE will reject at runtime). `_extract_and_validate_rules` runs each tool output through `GeRule.model_validate()` as a second gate — any failure raises `LlmOutputError` (mapped to `LLM_OUTPUT_INVALID` in the error envelope), giving the user a retryable error instead of a silent crash later during GE execution.

#### Review (reviewer agent)

- **Tool**: Claude Code (claude-sonnet-4-6) via **reviewer agent**
- **Verdict**: Pass — all curl verifications confirmed (suggest returns drafts, already_saved flips correctly, from-nl returns both union arms, mocked tests all green); tool-use schemas match D#7 design; no unapproved decisions

#### Commit (`/commit` skill)

- **Tool**: Claude Code `/commit` skill
- **Commit**: `feat(backend): implement Day 2 Phase 2 — AI generator and rules API`

---

### Phase 3 — GE Engine, Runs API, and Test Suite

#### Implementation (implementer agent)

- **Tool**: Claude Code (claude-sonnet-4-6) via **implementer agent**
- **Task**: `ge_engine.py`, `runs_store.py`, `api/results.py`, register `results_router`, `tests/test_runs.py`
- **Outcome**: Endpoints functional; store layer tested against live Supabase (transaction-rollback isolation); GE engine tested via mock in endpoint tests

#### Review — Coverage Gap Found (reviewer agent)

- **Tool**: Claude Code (claude-sonnet-4-6) via **reviewer agent**
- **Finding**: `GeEngine.run_rules` had no direct automated test coverage. The Specification required SQLite-backed GE smoke tests; the actual implementation mocked `GeEngine` at the endpoint layer and tested the store against live Supabase. The GE engine itself never executed in CI — the fail/error path was verified only by manual curl, leaving it non-reproducible.
- **Verdict**: Conditional pass; flagged adding a real GeEngine SQLite smoke test (pass / fail / nonexistent-column → error) as a required follow-up before commit

#### Bug Discovery During Fix (implementer agent)

- **Tool**: Claude Code (claude-sonnet-4-6) via **implementer agent**
- **Task**: Add the missing SQLite smoke tests for GeEngine
- **Bug discovered**: GE 1.x does **not** raise a Python exception when a rule references a nonexistent column. It returns `success=False` with `exception_info.raised_exception=True` inside the result object. The original `ge_engine.py` only caught Python exceptions in a `try/except` block — so a rule pointing to a missing column was normalized as `status="fail"` (red) instead of `status="error"` (yellow), violating D#18's three-state semantic.
- **Impact**: Wrong color shown to users. Red = data violates the rule; yellow = the rule itself is broken. Conflating them removes the user's ability to distinguish "go fix your data" from "go fix your rule."
- **Fix**: Added `_exception_was_raised` and `_first_exception_message` helpers that read `ge_result.exception_info`; `run_rules` now checks this before calling `_normalize_pass_fail`.
- **Process value**: The smoke test requirement surfaced a real semantic bug that the happy-path tests would never have caught. The reviewer → implementer loop turned a documentation note into a production fix.

#### Re-audit (reviewer agent)

- **Tool**: Claude Code (claude-sonnet-4-6) via **reviewer agent**
- **Verdict**: Pass — SQLite smoke tests added and confirmed passing (pass case, fail case, nonexistent-column → error case); `ge_engine.py` fix verified against D#18 three-state semantics; no new unapproved decisions introduced during the fix

#### Commit (`/commit` skill)

- **Tool**: Claude Code `/commit` skill
- **Commit**: `feat(backend): implement Day 2 Phase 3 — GE engine, runs API, and test suite`

---

### Phase 4 — Frontend Rule Management

#### Implementation (implementer agent)

- **Tool**: Claude Code (claude-sonnet-4-6) via **implementer agent**
- **Task**: `components/RulesView.tsx`, `components/RuleCard.tsx`, `components/NlRuleInput.tsx`, `lib/mutations.ts`, extend `lib/api.ts` to support POST/DELETE, `types/api.ts` additions
- **Outcome**: `/tables/[name]?tab=rules` fully interactive — Suggest → draft cards → Save/Discard, NL input with clarification display, optimistic delete with rollback
- **UI component design decisions**:
  - `RuleCard` renders two visual states: draft (blue border, Save + Discard buttons) and saved (gray border, Delete only). The `already_saved` badge disables Save without hiding the card — honoring D#22's transparency requirement.
  - `NlRuleInput` is a collapsible panel to keep the page uncluttered when NL input is not needed. Clarification text from the backend appears above the textarea in an amber alert box; the textarea is cleared so the user rewrites rather than appends — matching D#21's "user rewrites with more detail" mental model.
  - Draft state is held in React component state (`useState`), not in TanStack Query cache or localStorage. This means drafts disappear on page refresh — intentional per D#19's PII argument and the "AI is a collaborator, not a writer" trust model.
- **TanStack Query mutation patterns**:
  - `useDeleteRule` uses the full optimistic update cycle: `onMutate` cancels in-flight queries and applies the local filter, `onError` restores the snapshot from context, `onSettled` invalidates to reconcile with server state.
  - `useSuggestRules` and `useTriggerRun` do not use optimistic updates — their results are too unpredictable to pre-apply locally.

#### Review (reviewer agent)

- **Tool**: Claude Code (claude-sonnet-4-6) via **reviewer agent**
- **Verdict**: Pass — all Phase 4 verification steps confirmed (Suggest shows drafts, Save/Discard works, already_saved badge appears on re-suggest, NL clarification displays correctly, optimistic delete snaps back on error); component state decisions align with D#19 and D#22; no unapproved architectural decisions

#### Commit (`/commit` skill)

- **Tool**: Claude Code `/commit` skill
- **Commit**: `feat(frontend): implement Day 2 Phase 4 — Rule Management view`

---

### Phase 5 — Frontend Results Dashboard

#### Implementation (implementer agent)

- **Tool**: Claude Code (claude-sonnet-4-6) via **implementer agent**
- **Task**: `components/ResultsView.tsx`, `components/ResultRow.tsx`, `components/RunButton.tsx`, `useLatestRun` query, `useTriggerRun` mutation wired into UI
- **Outcome**: `/tables/[name]?tab=results` fully interactive — Run button triggers synchronous execution, three-color result rows with expand-to-sample, empty state on first load
- **Three-color UX mapping**:
  - `pass` → green (`text-green-600 bg-green-50`) with a checkmark — data is clean
  - `fail` → red (`text-red-600 bg-red-50`) with an X — data violates the rule; violating sample + count shown on expand
  - `error` → amber (`text-amber-600 bg-amber-50`) with a warning triangle — rule itself failed to execute; `error_message` shown with a "Check the rule configuration" prompt. This is the user-facing payoff of D#18: amber unambiguously tells the user "go fix the rule, not the data"
- **Run button loading state**: `useTriggerRun.isPending` drives a spinner and disabled state on the button. Because GE execution is synchronous (D#17, < 2s for seed data), the loading state is brief but still necessary — without it the button appears unresponsive on first click.
- **Results persistence**: `useLatestRun` fetches `GET /runs?table_name={name}&limit=1` on tab mount. If a previous run exists, results are shown immediately without re-running. This matches the CLAUDE.md requirement that "results are cached in Postgres so the UI can re-display without re-executing GE."

#### Review (reviewer agent)

- **Tool**: Claude Code (claude-sonnet-4-6) via **reviewer agent**
- **Verdict**: Pass — all Phase 5 verification steps confirmed (empty state on first load, Run triggers < 2s response, three-color rows visible, expand shows sample, deleted rules excluded from re-run, ErrorState on backend shutdown); three-color mapping matches D#18 spec; no unapproved decisions

#### Commit (`/commit` skill)

- **Tool**: Claude Code `/commit` skill
- **Commit**: `feat(frontend): implement Day 2 Phase 5 — Results Dashboard view`

---

### Phase 6 — Documentation and README

#### Implementation (implementer agent)

- **Tool**: Claude Code (claude-sonnet-4-6) via **implementer agent**
- **Task**: Update `docs/ai-tools-usage.md` with Day 2 entries (Phases 1–5), expand `README.md` with full 6-step demo flow and dirty-row INSERT, check off Day 2 items in `CLAUDE.md`, translate `docs/day2-plan.md` to English
- **Outcome**: Usage log updated with per-phase entries for all Day 2 work including the reviewer → implementer correction loop; README now covers the full Suggest → Save → NL → Run flow with three-color results explained; CLAUDE.md Task Breakdown fully checked off for Day 2
- **Notable**: The Development Workflow section was updated to reflect the reviewer → implementer correction loop as a first-class path in the diagram, not an exception — documenting that "implementer says it passed" and "it actually passed" are distinct claims. The Phase 3 bug discovery (GE 1.x `exception_info.raised_exception` semantics) is the concrete example that validates this workflow design.

#### Review (reviewer agent)

- **Tool**: Claude Code (claude-sonnet-4-6) via **reviewer agent**
- **Verdict**: Pass — ai-tools-usage.md contains at least 4 Day 2 entries covering prompt engineering, Tool Use schema design, GE 1.x debugging, and UI component design; README 5-minute demo is self-contained and reproducible; CLAUDE.md checklist fully reflects completed work

#### Commit (`/commit` skill)

- **Tool**: Claude Code `/commit` skill
- **Commit**: `docs(day2-phase6): update usage log, README demo flow, and CLAUDE.md checklist`

---

## Day 3 — Polish & Enhancement

### Architecture Planning (architect agent)

- **Tool**: Claude Code (claude-sonnet-4-6) via **architect agent**
- **Task**: Extend the Day 2 plan into Day 3 scope — revisit "start-from-simple" decisions made under Day 2 time pressure, and add the polish / documentation items from `CLAUDE.md`. The architect surfaced 16 decision points (D#23–D#38), presented options with tradeoffs, and waited for developer answers before writing the Specification.
- **Key decisions resolved through dialogue**:
  - D#23: Async runs via `BackgroundTasks` + frontend 1-second polling (over synchronous run or WebSocket) — simpler infra, no extra dependency, polling overhead negligible at demo scale
  - D#24: LLM response cache in Postgres (`dq.llm_cache`) with sha256 key including a `PROMPT_VERSION_*` constant — keeps state in one place; manual version bump is the invalidation SOP
  - D#25: Stateless multi-turn NL backend — full `ChatMessage[]` history sent each request, rebuilt into Anthropic blocks server-side; conversation lives only in the browser (privacy + simplicity trade-off)
  - D#29: Parallel rule execution via `ThreadPoolExecutor(max_workers=4)` — IO-bound GE SQL releases the GIL; bounded by SQLAlchemy pool size
  - D#30: Bonus "explain failure" LLM path — non-technical user gets a plain-English reason + suggested action without ever seeing GE jargon
  - D#33–D#38: Full violating-row display (full row table, violating column highlighted) + CSV download (streaming, cap 1000) — enables the inspect-and-understand loop without dropping to SQL
- **Phase rollout strategy**: 8 phases ordered by must-have → should-have → nice-to-have, with an explicit "cut order" so the developer knows what to drop if time runs short; Phase 8 (docs) is marked must-have alongside Phase 1 and Phase 2
- **Outcome**: `docs/day3-plan.md` produced with 16 Decision Log entries (each with Problem Essence + Tradeoffs), an 8-phase Specification, and a final demo checklist

---

### Phase 1 — Backend Foundations and Error Infrastructure

#### Implementation (implementer agent)

- **Tool**: Claude Code (claude-sonnet-4-6) via **implementer agent**
- **Task**: Lay the Day 3 backend groundwork (D#24, D#25, D#28, D#30, D#31) before feature phases build on it
- **Outcome**:
  - `app/api/errors.py` — centralised `raise_error(code)` helper plus a single `CODE_MAP` holding every D#31 error code (`LLM_TIMEOUT`, `LLM_OUTPUT_INVALID`, `LLM_RATE_LIMITED`, `DB_TIMEOUT`, `GE_EXECUTION_FAILED`, `INVALID_RULE_IDS`, `CACHE_CORRUPTED`, `RUN_STILL_RUNNING`, plus the existing 404 codes). `main.py`'s global handler reads the code from `exc.detail` and rebuilds the error envelope so distinct errors sharing one HTTP status keep their own machine-readable code.
  - `app/schemas/explain.py` — `ChatMessage` and `ExplainResponse` models, shared ahead of time by Phase 4 (multi-turn NL) and Phase 6 (explain failure).
  - `app/schemas/runs.py` — `RunStatus = Literal["running", "success", "failed"]` and the optional `CreateRunRequest.rule_ids` field (D#28).
  - `db/003_llm_cache.sql` — `dq.llm_cache` table with an `expires_at` index (D#24).
  - Frontend mirror: `lib/errorMessages.ts` (code → `{title, possible_causes, retry_label}`, with a dev-mode `console.warn` for unknown codes), `ErrorState.tsx` delegating to `getErrorMessage()`, and `types/api.ts` gaining `RunStatus`, `ChatMessage`, `ExplainResponse`.
- **End-to-end error flow**: API handler calls `raise_error(code)` → `HTTPException` carries the code as `detail` → `main.py` global handler looks it up in `CODE_MAP` → returns the error envelope → frontend `ErrorState` reads `error.code` → `getErrorMessage(code)` renders title + possible causes. The single map on each side is what keeps backend raise sites and frontend messages from drifting (D#31).

#### Review (reviewer agent)

- **Tool**: Claude Code (claude-sonnet-4-6) via **reviewer agent**
- **Verdict**: Pass — `uv run pytest` confirmed 29 passing; `CODE_MAP` covers every D#31 code; the explain/runs schema additions and the `003_llm_cache.sql` migration match the spec; no feature endpoints yet (these foundations are consumed by later phases); no unapproved decisions.

#### Commit

- `feat(day3): implement Phase 1 — backend foundations and error infrastructure`

---

### Phase 2 — LLM Cache and Parallel Rule Execution

#### Implementation (implementer agent)

- **Tool**: Claude Code (claude-sonnet-4-6) via **implementer agent**
- **Task**: DB-backed LLM response cache (D#24) and parallel GE execution (D#29)
- **Outcome**:
  - `app/services/llm_cache.py` — `make_cache_key` (sha256 of prompt name + version + sorted-JSON payload), `get_cached` (increments `hit_count`), and `set_cached` (upsert with TTL). Repeated Suggest / NL calls on identical input now skip the LLM and return in well under 200 ms.
  - `PROMPT_VERSION_SCHEMA` / `_NL` / `_EXPLAIN` constants in `ai_generator.py` — bumping any constant invalidates only that prompt's stale cache entries, which is the deliberate "prompt change SOP" invalidation mechanism from D#24.
  - `_nl_to_cache` / `_nl_from_cache` helpers serialize the `NlRuleResponse` discriminated union (`NlRuleSuccess | NlRuleClarification`) so the NL path is cacheable too.
  - `GeEngine.run_rules` refactored to `ThreadPoolExecutor(max_workers=4)` with `as_completed`, plus a one-time retry on `OperationalError` to absorb Supabase Session Pooler connection recycling. A `progress_callback: Callable[[RunResult], None] | None` parameter lets the caller write each result to the DB as its future completes — the hook Phase 3's async runs depend on.
- **Why `max_workers=4`**: connection-pool ceiling. SQLAlchemy's default `pool_size=5` holds exactly 4 workers plus the main thread (per D#29); IO-bound `batch.validate` SQL releases the GIL, so threads give real wall-clock speedup.

#### Review (reviewer agent)

- **Tool**: Claude Code (claude-sonnet-4-6) via **reviewer agent**
- **Verdict**: Pass — 5 new tests in `test_llm_cache.py` (hit, miss, expire, upsert reset, multi-key isolation) confirmed, full suite **34 passed**; cache key includes `PROMPT_VERSION_*` so prompt changes invalidate correctly (D#24); `ThreadPoolExecutor(max_workers=4)` stays within the SQLAlchemy pool size and the one-time `OperationalError` retry matches D#29; no unapproved decisions.

#### Commit

- `feat(backend): implement LLM cache and parallel rule execution`

---

### Phase 3 — Async Runs, Per-Rule Filter, and Polling UI

#### Implementation (implementer agent)

- **Tool**: Claude Code (claude-sonnet-4-6) via **implementer agent**
- **Task**: Async run execution (D#23), per-rule filter (D#28), frontend polling UI
- **Outcome**:
  - `POST /runs` now returns HTTP 202 immediately after creating the run record; `BackgroundTasks` dispatches `_execute_run` which writes per-result rows incrementally via `progress_callback` and calls `finalize_run` with an atomic guard to prevent double-finalization
  - `list_rules` in `rules_store.py` accepts an optional `rule_ids` list to filter which rules are executed in a run
  - Frontend uses `refetchInterval` in `useRunDetail` to poll the active run every 1 s; polling stops automatically when `status !== 'running'`
  - `RuleFilter` component (collapsible, collapsed by default) lets users select a subset of saved rules before triggering a run
  - `tests/test_runs_async.py` added — 10 tests covering: 202 status, immediate `running` state, background completion, and invalid rule_ids rejection

#### Review — Two Findings (reviewer agent)

- **Tool**: Claude Code (claude-sonnet-4-6) via **reviewer agent**
- **Finding 1**: The spec (day3-plan.md §3.5 Phase 3 Task 4) required a `「Running... N/total rules」` progress counter in the UI during `status='running'`. The implementation showed a generic spinner with no count.
- **Finding 2**: `POST /runs` handler was annotated `-> RunDetail` but decorated with `response_model=RunSummary`. Serialization behavior was correct (FastAPI uses `response_model`), but the type hint misled readers and static analyzers.
- **Verdict**: Conditional pass; both findings flagged as required fixes before commit

#### Reviewer Findings Fixed (implementer agent)

- **Tool**: Claude Code (claude-sonnet-4-6) via **implementer agent**
- **Reviewer finding 1 fix**: `ResultsView.tsx` — the component already holds `rulesQuery` from `useRules(tableName)`. Added `rulesQuery.data?.length` as the total. Three display locations updated: the header status line, the initial spinner (no results yet), and the in-progress caption above the growing results list. When `rulesQuery.data` is not yet loaded, falls back to `{N} rules completed` format — no new query required.
- **Reviewer finding 2 fix**: `results.py` line 50 — changed `-> RunDetail` to `-> RunSummary`. One-character-class change; no behavioral impact.
- **Notable**: The `progress_callback` mechanism is what makes the N/total counter meaningful. Each rule writes its result to the DB as soon as GE finishes evaluating it; the frontend polls every 1 s and receives the partial `results` array. The counter reflects actual incremental progress — not a fake animation — because `run.results.length` grows by 1 each time a rule completes.

#### Re-audit — Additional Findings (reviewer agent)

- **Tool**: Claude Code (claude-sonnet-4-6) via **reviewer agent**
- **Finding 1 (doc inaccuracy)**: The Implementation section stated the polling interval was 1.5 s. The actual code (`frontend/lib/queries.ts`) uses `1000` ms (1 s), matching the spec exactly.
- **Finding 2 (doc overclaim)**: The Implementation section claimed `tests/test_runs_async.py` covered `finalize_run` atomic guard semantics, `list_rules` rule_ids filter at the store layer, and empty `rule_ids = []` behavior. None of the three assertions were present in the file.
- **Verdict**: Conditional pass; both documentation inaccuracies required fixes before commit

#### Findings Fixed — Round 2 (implementer agent)

- **Tool**: Claude Code (claude-sonnet-4-6) via **implementer agent**
- **Finding 1 fix**: Corrected "1.5 s" → "1 s" in the Implementation and Notable sections of this document.
- **Finding 2 fix**: Added three tests to `tests/test_runs_async.py` (10 → 13 tests total):
  - `test_finalize_run_atomic_guard` — integration test using `db_session`: creates a run, finalizes it as `'success'`, calls `finalize_run` again with `'failed'`, and verifies the second call is a no-op (status stays `'success'`, error_message unchanged). Directly asserts the `WHERE status = 'running'` guard in the SQL.
  - `test_list_rules_empty_rule_ids_short_circuits` — unit test with a mock session: verifies `list_rules(session, rule_ids=[])` returns `[]` and never calls `session.execute`.
  - `test_list_rules_filter_by_rule_ids` — integration test: inserts a rule via `create_rule`, then verifies `list_rules(rule_ids=[id])` returns only that rule, and `list_rules(rule_ids=[id+999999])` returns `[]`.

#### Re-audit — Approved (reviewer agent)

- **Tool**: Claude Code (claude-sonnet-4-6) via **reviewer agent**
- **Verdict**: **Approved** — `uv run pytest tests/test_runs_async.py` passes with 13 tests; all three previously-missing assertions are now present; documentation interval corrected; no new scope creep introduced during the fix.

---

### Phase 4 — Multi-turn NL Chat (D#25)

#### Implementation (implementer agent)

- **Tool**: Claude Code (claude-sonnet-4-6) via **implementer agent**
- **Task**: Convert `POST /rules/from-nl` from a single description string to a full `ChatMessage[]` history; build the chat-thread UI
- **Outcome**:
  - Backend stays **stateless** — no chat session table. Each request calls `_build_anthropic_messages` to reconstruct Anthropic-native `tool_use` / `tool_result` block pairs from the JSON-serialized assistant messages the client sends back. This leans directly on the Anthropic Messages API's own stateless design (D#25).
  - `PROMPT_VERSION_NL` bumped to `v2`, which invalidates every single-turn cache entry from earlier phases — a concrete demonstration of the D#24 prompt-versioning invalidation contract.
  - 5-user-turn cap enforced in two places: React (`MAX_USER_TURNS`) and Pydantic (`max_length=10` on the `messages` field) — UI guidance and a hard server guarantee.
  - Frontend: `NlChatThread` (conversation bubbles, scroll-to-bottom, clarification display, optimistic rollback on error, "Start over" reset); `NlRuleInput` reduced to a ~32-line thin wrapper. Conversation lives only in React state — refresh clears it, which is intentional because NL prompts may contain PII (D#25).
- **Why stateless**: a server-side session would just re-wrap the "assemble messages" work the client already has to do, adding a table, expiry, and auth for no demo benefit. Treating the conversation as client-side state (like a form draft) is the lighter, more API-native choice.

#### Review (reviewer agent)

- **Tool**: Claude Code (claude-sonnet-4-6) via **reviewer agent**
- **Verdict**: Pass — 10 new tests in `test_rules_multi_turn.py` (history round-trip, cap boundary, malformed-assistant fallback) confirmed and `test_rules.py` updated for the new request shape; the 5-user-turn cap is enforced in both React and Pydantic; `PROMPT_VERSION_NL` bump to `v2` correctly invalidates single-turn cache entries (D#25); backend stays stateless as specified; no unapproved decisions.

#### Commit

- `feat(day3-phase4): implement multi-turn NL chat (D#25)`

---

### Phase 5 — PUT Edit Modal, Diff View, and Error Polish

#### Implementation (implementer agent)

- **Tool**: Claude Code (claude-sonnet-4-6) via **implementer agent**
- **Task**: D#26 `RuleEditModal` + `DiffLines` components, `RuleCard` [Edit] button, `useUpdateRule` mutation; D#31 backend HTTPException → `raise_error()` migration across `tables.py`, `rules.py`, `results.py`
- **Outcome**:
  - `RuleEditModal` renders a two-column layout: left side shows the original rule as read-only JSON; right side has an `expectation_type` select, a `kwargs` textarea with live `JSON.parse` validation, and a `description` textarea
  - `DiffLines` is a self-contained ~66-line component that renders field-level before/after comparison at the bottom of the modal — no external diff library introduced
  - Save is disabled whenever `kwargs` contains invalid JSON; an inline red error message explains the format requirement
  - All three backend API files now use `raise_error()` from `app/api/errors.py` rather than constructing `HTTPException` directly, consolidating error code definitions in one place
- **Component architecture note**: `RuleEditModal` is rendered inside a `<>…</>` fragment alongside the existing `RuleCard` div rather than portal-mounted. This keeps the component tree local to the card but still works correctly because the overlay uses `fixed inset-0` positioning — the stacking context does not depend on DOM position at MVP scale.

#### Review (reviewer agent)

- **Tool**: Claude Code (claude-sonnet-4-6) via **reviewer agent**
- **Verdict**: **Approved with notes** — all D#26 and D#31 spec requirements met; `DiffLines` is 66 lines (spec guideline was ≤60, spirit satisfied); diff uses uniform red/green treatment for all fields rather than the spec's literal `▶` glyph for `expectation_type` (functionally equivalent); `INTERNAL_ERROR` is a frontend-synthesised code with no corresponding backend `CODE_MAP` entry (intentional — `lib/api.ts` generates it on network failure — but worth noting for future SOP documentation)

#### Commit (`/commit-push` skill)

- **Tool**: Claude Code `/commit-push` skill
- **Commit**: `feat(day3-phase5): implement rule edit modal with diff view and error polish (D#26, D#31)`

---

#### Developer-Initiated Fixes

These two changes were noticed by the developer after the implementer–reviewer cycle completed and were folded into the same commit. They are recorded here because they reflect the developer's own product instincts rather than spec-driven work.

**Input text color fix**

- **Observation**: After the Edit modal was first rendered, the text inside the `select`, kwargs `textarea`, and description `textarea` appeared light-coloured. The browser's default text colour on form elements is system-defined and can render as near-invisible on certain OS appearance settings.
- **Fix**: Added `text-gray-900` to all three form element class lists in `RuleEditModal.tsx`. No architectural change; one-line addition per element.
- **Why it matters**: A modal where you cannot clearly read what you are editing defeats the purpose of the edit flow. This is the kind of gap that unit and type-checking tools cannot catch — it requires actually looking at the rendered UI.

**`docs/day3-plan.md` cleanup**

- **Observation**: `day3-plan.md` still contained the full D#27 mobile drawer decision (decision text, spec section, component pseudocode, risk table entry, rollout phase task, and demo checklist item) even though mobile layout had been descoped before Day 3 implementation began.
- **Fix**: Removed all D#27 references from the plan document so the written spec matches what was actually built. The descoped item is now listed only in the Future Enhancements section of `docs/architecture.md`.
- **Why it matters**: A plan document that describes features that were never built is misleading to any reader using it as the authoritative record of what the system does.

---

### Phase 6 — Bonus: LLM Explain Failure (D#30)

#### Implementation (implementer agent)

- **Tool**: Claude Code (claude-sonnet-4-6) via **implementer agent**
- **Task**: On-demand LLM plain-English explanation for failed run results (D#30) — new endpoint, generator method, prompt template, and frontend panel
- **Outcome**:
  - `POST /results/{result_id}/explain` — guards `404 RESULT_NOT_FOUND` and `400 RESULT_NOT_FAILED` (explanations only apply to `fail` results, D#35), fetches the result + rule via `runs_store.get_result_with_table()` (a join over `dq.run_results` + `dq.runs`), and returns `{explanation, possible_causes, suggested_action}`.
  - `AiGenerator.explain_failure()` — passes the rule kwargs + violating sample to Claude under an `EXPLAIN_FAILURE_TOOL` schema (structured output), Pydantic-validates the `ExplainResponse`, and routes through the D#24 cache (key = `hash(prompt_name + version + rule_id + unexpected_sample)`), so repeated clicks on the same row return in <200 ms.
  - `explain_failure.md` prompt template added.
  - Frontend: `ResultExplainPanel` (explanation + possible-causes bullets + suggested action), `useExplainFailure` mutation, and a 💡 "Why did this fail?" button revealed when a `fail` `ResultRow` is expanded. The result is held in `useState` so it persists while the row stays open.
- **On-demand by design**: explanations are not pre-generated during a run — the user clicks to generate one, which keeps token cost proportional to what is actually inspected (D#30).

#### Review (reviewer agent)

- **Tool**: Claude Code (claude-sonnet-4-6) via **reviewer agent**
- **Verdict**: **Approved with notes** — `uv run pytest tests/test_explain.py` confirmed 4 passing (404, 400, response shape, cache hit); the endpoint correctly guards non-`fail` results and the cache key includes `rule_id` + sample so stale explanations invalidate (D#24/D#30). Note flagged for follow-up: `test_returns_explain_response_shape` used a fragile name-mangled `_AiGenerator__init__` mock and dynamic `__import__` calls that could break on a Python version bump or class refactor — recommended hardening before relying on the test long-term.

#### Implementer-initiated fix (reviewer finding from Phase 6 audit)

- **Tool**: Claude Code (claude-sonnet-4-6) via **implementer agent**
- **Trigger**: The Phase 6 reviewer audit (Approved with notes) flagged that `test_returns_explain_response_shape` in `tests/test_explain.py` used a name-mangled mock — `patch.object(..., "_AiGenerator__init__", ..., create=True)` and dynamic `__import__` calls to obtain `AiGenerator` and `ExplainResponse`. The reviewer noted this pattern could silently break on Python version changes or class refactors.
- **Fix applied**:
  - Added module-level imports for `AiGenerator`, `PROMPT_VERSION_EXPLAIN`, `ExplainResponse`, `get_cached`, `make_cache_key`, `set_cached` at the top of the test file.
  - Replaced the name-mangled `patch.object(..., "_AiGenerator__init__", ...)` with `patch.object(AiGenerator, "__init__", lambda self: None)` — the standard public-attribute form.
  - Collapsed the nested `with patch(...)` for `explain_failure` into the same `with (...)` block using `patch.object(AiGenerator, "explain_failure", return_value=ExplainResponse(...))` — cleaner and no functional difference.
  - Removed the three redundant local re-imports inside `test_explain_uses_llm_cache` (now covered by module-level imports).
- **Outcome**: 4/4 tests pass; no production code touched; mock semantics identical to pre-fix.

#### Review (reviewer agent)

- **Tool**: Claude Code (claude-sonnet-4-6) via **reviewer agent**
- **Verdict**: **Approved with notes** — fix is correctly scoped to test internals; `patch.object(AiGenerator, "__init__", ...)` correctly stubs the constructor's Anthropic client instantiation; `patch.object(AiGenerator, "explain_failure", ...)` correctly intercepts the bound method on the instance created in the endpoint; `create=True` kwarg correctly dropped (attribute exists); all 4 tests pass on re-verification. Note recorded: the redundant local re-imports inside `test_explain_uses_llm_cache` were also cleaned up in the same pass.

---

### Phase 7 — Violating Row Full Display + CSV Download (D#33–D#38)

#### Implementation (implementer agent)

- **Tool**: Claude Code (claude-sonnet-4-6) via **implementer agent**
- **Task**: Upgrade failed-result display from GE's scalar `partial_unexpected_list` to complete violating rows, persisted and downloadable as CSV
- **Outcome**:
  - `pk_inspector.get_pk_columns()` — resolves a table's primary key (single or composite) via `pg_index` / `pg_attribute`; returns `None` for tables with no PK.
  - `GeEngine` now runs each expectation with `result_format=COMPLETE` and `unexpected_index_column_names=pk_cols`, then `_fetch_full_rows()` reverse-looks up complete rows via a single- or composite-PK `IN`-clause `SELECT`. This is the D#36 "trust GE for the index list, fetch the full row ourselves" boundary — predictable behaviour without trusting GE's COMPLETE row payload.
  - `db/004_run_results_rows.sql` adds `unexpected_rows` (JSONB) + `truncated` (BOOLEAN); `runs_store.write_result` persists rows capped at 1000 and sets `truncated` when exceeded (D#37 snapshot semantics — a run_id always returns the same rows).
  - `GET /results/{result_id}/violations.csv` — `StreamingResponse` + `csv.DictWriter`, with a `400 RESULT_NOT_FAILED` guard so `error`/`pass` results can't request a CSV (D#35).
  - Frontend `ViolatingRowsTable` — table of up to 10 full rows, violating column red-highlighted (derived from rule kwargs in `ResultsView`), horizontal scroll, Download CSV button, and a no-PK fallback message.
  - `db/005_dirty_data.sql` — test fixture inserting intentional violations across all three tables so the feature is demoable on the live UI.
- **Spike confirmed first**: per the day3-plan risk table, composite-PK support in GE 1.x's `unexpected_index_column_names` was validated before building on it; the demo tables all use a single-column `id` PK, and the composite/no-PK paths are covered by tests.

#### Review (reviewer agent)

- **Tool**: Claude Code (claude-sonnet-4-6) via **reviewer agent**
- **Verdict**: Pass — 14 tests in `test_violating_rows.py` confirmed (PK detection single / composite / no-PK, `_fetch_full_rows` paths, CSV streaming, the `RESULT_NOT_FAILED` boundary); the GE-index-plus-reverse-SELECT approach matches D#36, the 1000-row cap + `truncated` flag matches D#37, and `error`/`pass` results correctly bypass the CSV path (D#35); no unapproved decisions.

#### Commit

- `feat(day3-phase7): implement violating row full display + CSV download (D#33–D#38)`

---

### Phase 8 — Documentation

#### Implementation (implementer agent)

- **Tool**: Claude Code (claude-opus-4-7) via **implementer agent**
- **Task**: Bring the deliverable docs up to the final Day 3 state (D#32)
- **Outcome**:
  - `README.md` rewritten as a Day 3 5-minute demo walkthrough — async-polling run flow, multi-turn NL chat, rule edit + diff, violating-row table, CSV download, and the explain-failure step; Database Setup now lists migrations `003`–`005`; the manual dirty-row `INSERT` was replaced by the `005_dirty_data.sql` fixture.
  - This usage log gained the four previously-undocumented Day 3 phases (1, 2, 4, 7) reconstructed from commit history.
  - `docs/architecture.md` written — system overview, request-flow diagram (control flow + data-flow sequence diagrams), the API / Service / Store layering, a D# decision index, and a categorised Future Enhancements section (Product / Scalability / Maintainability / Security), including the cache-GC and no-PK-row debts called out in D#37 / D#36.
  - `docs/ai-integration.md` written — AI design rationale: Tool Use structured output + Pydantic second pass (D#7), the four tool schemas and their two `tool_choice` strategies, the three prompt templates' design choices, stateless multi-turn history reconstruction (D#25), the explain-failure prompt (D#30), and the cache-key strategy + prompt-change SOP (D#24).
  - `CLAUDE.md` Day 3 checklist, the "LLM auto-explains failures" bonus, and the "Diff view when editing a suggested rule" bonus checked off.
- **Scope note (developer instruction)**: the **token-cost section** specified for `ai-integration.md` (D#32) was omitted by developer decision rather than fabricated, because no measured numbers from a real demo run were available.

#### Review (reviewer agent)

- **Tool**: Claude Code (claude-sonnet-4-6) via **reviewer agent**
- **Verdict**: Approved with notes — all four deliverable docs exist and are substantive; `CLAUDE.md` Day 3 checklist fully checked (two optional bonus items left unchecked are both "only if time permits"). Two non-blocking findings:
  1. `ai-integration.md` missing the token-cost section specified in D#32 ("token cost 估算以 demo 完整跑一次的實測值") — the implementer honestly disclosed this in the Phase 8 note as a developer-authorized omission; no measured numbers were available. Recorded as a future-hardening item.
  2. `ai-tools-usage.md` Day 3 lacked an `### Architecture Planning (architect agent)` entry — Day 1 and Day 2 both open with this entry; Day 3 jumped straight to Phase 1. The spec verification criterion explicitly required "ultrareview/architect" in the Day 3 log.

#### Post-Review Developer Improvements

- **By**: developer (manual)
- **Triggered by**: developer
- **Changes**: After reviewing the AI-generated docs, the developer injected their own perspective and domain knowledge into each deliverable — adding paragraph that the agent couldn't derive from prompt, code or commit history first.

#### Commit

- `docs(day3-phase8): write architecture overview, demo README, and Day 3 usage log`