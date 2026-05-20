# Day 2 Architecture Plan — AI-Powered Data Quality Assistant

This document is the complete Day 2 architecture plan, covering all resolved decisions (Decision Log), no pending decisions (Decision Points), and the implementation specification (Specification). Treat this document as the single source of truth for Day 2.

Day 1 decisions (D#0–D#10) are in [day1-plan.md](./day1-plan.md).

---

## Day 2 Scope

From `CLAUDE.md`:

**Backend**
- `schemas/rules.py` — Pydantic models for GE rules and API request/response shapes
- `services/ai_generator.py` — Anthropic client wrapper, Tool Use structured output (D#7), Pydantic second-pass validation
- `services/ge_engine.py` — Great Expectations execution against Postgres
- `services/rules_store.py` — `dq.rules` CRUD
- `services/runs_store.py` — `dq.runs` + `dq.run_results` write/read
- `api/rules.py` — `POST /rules/suggest`, `POST /rules/from-nl`, `GET/POST /rules`, `PUT/DELETE /rules/{id}`
- `api/results.py` — `POST /runs`, `GET /runs/{id}`, `GET /runs/`
- Register `rules` and `results` routers in `main.py`
- `db/002_run_results_status.sql` — add `status VARCHAR(10)` three-state column

**Frontend**
- Rule Management view (`/tables/[name]?tab=rules`)
- Results Dashboard view (`/tables/[name]?tab=results`)

**Out of Day 2 scope** (deferred to Day 3): LLM response caching (hash-based), parallel rule execution, mobile layout, true chat conversation history, PUT rule edit UI (Day 2 only supports Delete + recreate).

---

## Section 1: Decision Log (Resolved Decisions)

Each decision includes a **Problem Essence** section (why this is a real decision, not trivial) and a **Tradeoff** section (what is given up by choosing this option).

---

### D#11: Library Versions Locked by Day 1 `pyproject.toml`

- **Decision**: Use the versions already in `backend/pyproject.toml`; do not upgrade in Day 2:
  - `anthropic>=0.103.1` (Messages API + Tool Use)
  - `great-expectations>=1.17.2` (**GE 1.x**, incompatible with 0.x API)
  - `sqlalchemy>=2.0.49`, `psycopg[binary]>=3.3.4`
- **Why It Matters**: GE 1.x replaces the 0.x Expectation Suite YAML workflow with an entirely new `gx.Context` + `Validator` + `BatchDefinition` model. Almost all blog posts and StackOverflow answers before 2024 are inapplicable. Writing `ge_engine.py` requires reading the official GE 1.x documentation directly.
- **Options Considered**: Downgrade GE to 0.18.x (more ecosystem content but officially deprecated). Rejected: rolling back the lockfile in Day 2 amounts to invalidating all Day 1 validation.
- **How Chosen**: Constrained by the existing Day 1 lockfile.
- **Problem Essence**: GE's major version break is not just an API rename — the entire data representation model changed. In 0.x: "Suite is a file, Checkpoint is YAML, Datasource is a text config." In 1.x: "Everything is a Python object, Context holds all metadata, Validator and Batch are two separate concepts." Writing 1.x code while accidentally copying a 0.x example produces errors like `AttributeError: 'Context' object has no attribute 'add_expectation_suite'` — where the syntax looks right but fails at runtime.
- **Tradeoff**: Gives up the large body of GE 0.x tutorials and StackOverflow content; must rely on official documentation only, which increases initial debug time. Any future GE Cloud integration is also locked to the 1.x path.

---

### D#12: API Shape Locked by `CLAUDE.md`

- **Decision**: API paths and HTTP methods follow the `CLAUDE.md` table exactly; no redesign:
  - `POST /rules/suggest`, `POST /rules/from-nl`
  - `GET /rules`, `POST /rules`, `PUT /rules/{id}`, `DELETE /rules/{id}`
  - `POST /runs`, `GET /runs/{id}`, `GET /runs/`
- **Why It Matters**: The frontend is being built in parallel during Day 2; any API path change forces a second round of frontend/backend alignment.
- **Options Considered**: A more RESTful nested path (`POST /tables/{name}/rules/suggest`). Rejected: CLAUDE.md has already decided.
- **How Chosen**: Constrained by the existing specification.
- **Problem Essence**: REST style tends toward over-design when resource nesting is ambiguous. CLAUDE.md places `/rules` as a top-level resource rather than nested under `/tables/{name}/rules`, meaning a rule is a first-class entity (can be listed or deleted without table context). For the Day 2 "Rule Management" UX this is a good fit — it just means `GET /rules` accepts a `?table_name=` query param instead of using a path segment.
- **Tradeoff**: Gives up the implicit `table_name` context from a nested path; `GET /rules` must accept `?table_name=` to scope the list. The frontend must remember to include it.

---

### D#13: DB Schema Already Created in Day 1

- **Decision**: Use the `dq.rules`, `dq.runs`, `dq.run_results` tables already built in `backend/db/001_dq_schema.sql`. The only new addition in Day 2 is `002_run_results_status.sql` (for D#18's three states).
- **Why It Matters**: Implementation of the store layer can begin immediately without interrupting the flow to run a migration.
- **Constraints**: `dq.rules` already has columns `(id, table_name, expectation_type, kwargs JSONB, description, source, created_at, updated_at)`; all Pydantic models in `schemas/rules.py` must round-trip to this structure without friction.
- **Problem Essence**: "Write schema first, then ORM" vs "write ORM first, then generate schema" have completely different development tradeoffs. At MVP scale with a manually designed schema, "SQL as source of truth, Pydantic models align to schema" is the shorter path. When schema churn increases, switching to Alembic-driven migrations is straightforward.
- **Tradeoff**: Any structural change (e.g., D#18 adding the `status` column) requires writing a `00N_*.sql` file and running it manually — one more step than Alembic auto-generated migrations, but acceptable at small scale.

---

### D#14: Frontend Write Path Unified with TanStack Query Mutations

- **Decision**: All Day 2 write operations (save rule, delete rule, trigger run) use `useMutation`; on success, `queryClient.invalidateQueries({ queryKey: [...] })` triggers refetch of related queries.
- **Why It Matters**: Continues the Day 1 `useQuery` server-state management style; avoids mixing `useState + fetch + manual refetch` inside components, which produces boilerplate.
- **Options Considered**: Calling `apiFetch` directly inside `onClick` handlers. Rejected: loses cache invalidation; every component must re-implement loading/error state.
- **Problem Essence**: In React, "server state" and "local UI state" are two separate problems. `useState` fits local state, but managing server state forces the developer to handle caching, refetching, stale-while-revalidate, and error retry manually. TanStack Query's `useMutation` abstracts these into a single pattern: "mutation completes → invalidate related query key → UI refetches automatically," giving correct behavior without extra thought.
- **Tradeoff**: Requires learning `useMutation`'s lifecycle (`onMutate` / `onSuccess` / `onError` / `onSettled`), which has an initial ramp-up cost. Optimistic updates also require `onMutate` + `onError` rollback — Day 2 defers optimistic updates except for rule card deletion.

---

### D#15: Error Envelope Carried Over from Day 1

- **Decision**: All Day 2 endpoints use the Day 1 `ErrorEnvelope` (`{error: {code, user_message, technical_detail}}`). New error codes (see 3.3.3) are additive entries to `code_map` — the envelope structure is unchanged.
- **Why It Matters**: The frontend `ApiError` class and `<ErrorState>` component already handle this format; new error codes work without any changes.
- **Problem Essence**: API error contracts should be stabilized as early as possible. Changing the envelope structure is a cross-cutting change requiring all endpoints and the frontend `apiFetch` to be updated together; adding to `code_map` is just a dictionary entry. Day 1's design passed D#10 verification — no reason to change it.
- **Tradeoff**: None — purely additive.

---

### D#16: GE Execution Mode = SQL Datasource

- **Decision**: `services/ge_engine.py` uses Great Expectations 1.x's **Postgres SQL Datasource**. The flow is `Context → Datasource → TableAsset → BatchDefinition → Batch → batch.validate(expectation)`. Data stays entirely in Postgres; GE generates the SQL.
- **Why It Matters**: This is Day 2's most load-bearing decision — it determines the overall shape of `ge_engine.py`, the memory footprint of execution, and how results are mapped to `dq.run_results`. The most painful to change after the fact.
- **Options Considered**:
  - Pandas DataFrame in-memory (simpler, but loads the entire table into Python memory; would OOM on real large tables in the future).
  - Write a custom SQL emulator (full control over result format, but violates CLAUDE.md's "don't reinvent the wheel" principle).
- **How Chosen**: User selected SQL Datasource for production fidelity and the "data never leaves the DB" security model.
- **Problem Essence**: The central tension in data quality tooling is "where should validation logic live?" — The Pandas path means "pull data to the application layer, compute in Python." The SQL path means "push validation down to the DB, compute in SQL." The former has a better developer experience (everything is a DataFrame, printable and debuggable) but no defense against real large tables; the latter has a higher upfront learning cost (GE 1.x's Datasource/Validator/Batch hierarchy) but is inherently scalable. We chose the latter, betting that "production fidelity and the security narrative during the demo" justify the learning curve.
- **Tradeoff**: Gives up Pandas's "print DataFrame, interactive debug" workflow. GE 1.x SQL Datasource error messages are harder to understand when the schema doesn't match (double stack trace from SQLAlchemy + GE). The `DATABASE_URL` format (`postgresql+psycopg://`) differs from the format GE's `add_postgres(connection_string=...)` expects (plain `postgresql://`) — requires a one-time string replacement in `ge_engine.py`.

---

### D#17: Run Execution Mode = Synchronous Blocking

- **Decision**: `POST /runs` executes all rules synchronously, writes to `dq.runs` + `dq.run_results`, and returns a complete `{run_id, status, results: [...]}`. `dq.runs.status` only ever holds `success` / `failed` (no `running` state).
- **Why It Matters**: Determines the API contract shape (synchronous = response includes `results` array; asynchronous = response includes only `run_id`, requiring polling) and the frontend loading UX.
- **Options Considered**: FastAPI BackgroundTasks + frontend polling GET (more responsive, but BackgroundTasks has no real worker isolation); Server-Sent Events (best UX, but TanStack Query doesn't handle streaming well).
- **How Chosen**: User selected synchronous; async complexity is not justified at MVP scale where GE execution takes < 2 seconds.
- **Problem Essence**: The HTTP sync vs async choice is not a technical preference question — it's a UX question about how long the user is willing to stare at the screen. Experience: < 5s is fine synchronous; 5–15s is acceptable synchronous with a loading state; > 15s must be async (otherwise browser timeout / proxy 502 / user starts refreshing). The MVP seed data is roughly 50 rows × 8 rules; each GE SQL rule takes < 100ms, totaling around 1 second — well within the synchronous comfort zone. If the Day 3 polish phase introduces a large-table demo scenario, upgrade to async then.
- **Tradeoff**: Gives up "see per-rule progress in real time during execution" UX. If the same API is later pointed at a million-row table (where a single expectation may take 10 seconds), HTTP will time out — refactoring to a background job is estimated at one day of work.

---

### D#18: Result Status Model = Three States (pass / fail / error)

- **Decision**: `dq.run_results` adds `status VARCHAR(10) NOT NULL` (values: `'pass'` / `'fail'` / `'error'`). Added via `002_run_results_status.sql` migration. Frontend color coding: green = pass, red = fail (data violates the rule), yellow = error (rule itself failed to execute, e.g., column does not exist, type mismatch, GE internal exception).
- **Why It Matters**: CLAUDE.md explicitly requires red/yellow/green color coding; clarity of user experience is a Product Thinking scoring criterion.
- **Options Considered**: Two states (keep existing `success BOOLEAN`, normalize exceptions as fail); DB two-state + API-inferred three-state (avoids migration but creates implicit coupling between store and API).
- **How Chosen**: User selected three states for clear Product Thinking value.
- **Problem Essence**: "A rule didn't pass" has two fundamentally different root causes: (1) the rule is correct, but the data violates it (business insight — the data has a problem); (2) the rule itself couldn't execute (technical error — the rule is broken). Collapsing these into one red state makes it impossible for a non-technical user to distinguish "go tell the data administrator to fix the data" from "go tell the engineer to fix the rule." The value of three states is not in database design, not in API design — it's in "what the user knows to do when they see a yellow light." That is exactly what the Product Thinking criterion is looking for.
- **Tradeoff**: Adds a schema migration (one `002_*.sql` file + ALTER TABLE), a third value to write in the store layer, a `status` enum to expose in the API response model, and three-color mapping in the frontend. Estimated 1.5 hours of additional work. The `success BOOLEAN` column is retained (for backward compatibility and dual verification), but reads use `status` as the source of truth.

---

### D#19: Rule Suggestion Flow = Draft Mode (Suggest Does Not Write DB)

- **Decision**: `POST /rules/suggest` does **not** write to the DB; it returns an in-memory draft array. The frontend displays drafts as cards, each with `[Save]` and `[Discard]` buttons. Pressing Save calls `POST /rules` to persist, setting `source='ai_schema'`.
- **Why It Matters**: Determines the API shape of `POST /rules/suggest` (returns array vs returns id list), the semantic of `dq.rules.source`, the frontend "review-before-save" UI, and the undo behavior model.
- **Options Considered**: Auto-save all, let the user delete unwanted ones; Hybrid (drafts + Save all batch button).
- **How Chosen**: User selected draft mode; AI as collaborator, not overwriter — aligns with Product Thinking goals.
- **Problem Essence**: AI "making" decisions for the user (writing to DB) vs "proposing" decisions (showing drafts) are two completely different trust models. The former declares "AI is always right; you just proofread." The latter declares "AI proposes; you decide." The MVP's target users are non-technical domain experts — "proofread what AI wrote into the DB" is a higher cognitive load (read, judge correctness, decide to delete); "view AI's proposals and select what you want" is more intuitive and less mentally taxing for non-technical users. This choice defines the product's entire AI relationship model, not just a technical design.
- **Tradeoff**: Each rule requires two clicks (suggest → save). The frontend must manage draft state (cannot use localStorage because LLM output may contain PII; disappearing on page refresh is a feature, not a bug).

---

### D#20: Run Scope = All Rules for the Table

- **Decision**: `POST /runs` request body accepts only `{table_name: string}`. The backend SELECTs all rules from `dq.rules WHERE table_name=:name` and executes them. No `rule_ids` subset parameter.
- **Why It Matters**: Determines the request body shape, re-run UX (one Run button per table; no per-rule "re-run failed" button), and the historical retention semantics of `dq.run_results.rule_id` when a rule is deleted (`ON DELETE SET NULL` preserves historical results).
- **Options Considered**: Accept a `rule_ids` subset; dual-mode (optional `rule_ids`, defaulting to run all).
- **How Chosen**: User selected run-all for MVP simplicity; per-rule re-run deferred to Day 3.
- **Problem Essence**: "Execution granularity" is a long-term divergence point in data quality tooling. Coarse-grained (per-table) has a simple mental model — "I care about this table's health" is a holistic judgment. Fine-grained (per-rule) has higher engineering efficiency — "I only changed one rule; I don't want to re-run the whole batch." At MVP scale, total execution time is < 2 seconds (D#17), so the time saved by fine-grained execution is imperceptible — making fine-grained's costs (frontend must track checked state, URL must encode selection, results must merge with history) pure overhead. In Day 3, if the demo scenario becomes "100 rules, each taking 5 seconds," adding `rule_ids` is just changing the parameter from required to optional — backward compatible.
- **Tradeoff**: Gives up per-rule re-run; re-running a single rule requires re-running the entire table (not painful at MVP scale). Results Dashboard will have no per-rule "↻" button.

---

### D#21: NL Clarification UX = One-Shot Communication

- **Decision**: `POST /rules/from-nl` request body is `{table_name, description}`. Response is a discriminated union:
  - `{type: "rule", rule: {expectation_type, kwargs, description}}`
  - `{type: "clarification", question: string}`
  - When the frontend receives `clarification`, it displays the question above the input box; the user re-enters a more detailed description (the original description is not pre-populated in the textarea).
- **Why It Matters**: Determines whether `from-nl` is stateless or stateful; determines whether the frontend NL input component is single-shot or a dialog; determines whether the prompt needs to support message history.
- **Options Considered**: Full chat (messages history); Hybrid (allow one follow-up).
- **How Chosen**: User selected one-shot communication; conversational chat deferred to Day 3 bonus.
- **Problem Essence**: CLAUDE.md describes the interface as "chat-style," but "chat-style visuals" and "stateful conversation backend" are two different things. Chat visuals require only stacking an input box with message bubbles; truly stateful conversation requires message history, a prompt that handles history, exponentially growing token costs, and a prompt eviction strategy. The MVP needs only the former; the engineering investment in the latter has no proportional return against the core scoring criteria (AI-First, Product Thinking, Technical Implementation). Day 3 chat is a bonus item.
- **Tradeoff**: Gives up multi-turn conversation UX; users who receive a clarification must retype. The `request_clarification` prompt already requires the LLM to give a "specific follow-up question," so users can usually complete the description in one retry without many cycles.

---

### D#22: Rule Deduplication = Backend Flag, Frontend Disable Save

- **Decision**: Each draft returned by `POST /rules/suggest` includes an `already_saved: bool` flag — the backend compares against existing `dq.rules` for the table; if `(expectation_type, kwargs)` already exists, `already_saved=true`. Frontend display: cards with `already_saved=true` show an "Already saved" badge and have Save disabled (but the card is still shown, so the user can see which suggestions AI repeated). The backend `POST /rules` write path does not deduplicate and adds no UNIQUE constraint (allowing users to intentionally create seemingly duplicate rules).
- **Why It Matters**: Determines whether `dq.rules` schema needs a UNIQUE constraint (no); whether `/rules/suggest` response needs an additional field (yes — add `already_saved`); and the disabled state UI on the frontend draft card component.
- **Options Considered**: Backend filters out duplicates (frontend never sees them); `POST /rules` returns 409; ignore entirely.
- **How Chosen**: User selected "show but mark" for high transparency — users can see what old suggestions AI repeated and won't mistakenly think they missed a new rule.
- **Problem Essence**: Software design often carries the misconception that "duplication is wrong and must be eliminated." But for users, "why didn't this suggestion appear?" is harder to debug than "why did this suggestion appear again?" — implicit filtering leads users to think "AI couldn't think of that rule," when in reality "AI suggested it but we hid it." Transparently showing duplicates (marked as already saved) is "honest design" — users see AI's complete proposals and which ones already exist, making decisions with complete information. This also avoids the technical difficulty of a DB UNIQUE constraint on JSONB (which would require an `md5(kwargs::text)` expression index, fragile to key order and whitespace).
- **Tradeoff**: Suggest response gains one field (frontend types must align); frontend card component needs a disabled state; DB allows duplicates (if a user were to PUT two originally different rules into identical state, it would not be blocked — Day 2 does not support a PUT UI, so this cannot happen).

---

## Section 2: Decision Points (Pending)

**(Empty — all decisions resolved.)**

If new architectural choices surface during implementation, stop, add a Decision Point, wait for an answer, then continue.

---

## Section 3: Specification

### 3.1 Problem Statement

The Day 2 goal is to upgrade the Day 1 skeleton into a usable closed loop: user selects a table → clicks Suggest to see AI-proposed rules → selects rules to save to DB → adds custom rules via natural language → clicks Run to see red/yellow/green results and violating samples → results persist after page refresh.

**Minimum demo bar for Day 2 completion**: The user can complete the full "Suggest → Save 5 rules → Add 1 via NL → Run → See red/yellow/green + violating samples" flow on the `policyholders` table, with no unhandled exceptions in the backend console.

**Ambiguities and assumptions**:
- "Demo seeing red failure results" requires manually INSERTing one dirty row beyond the seed data (D#2) — Day 2's README adds this command.
- Day 2 does not build a PUT `/rules/{id}` frontend UI (the backend endpoint is implemented, but the frontend supports only Delete + recreate) — avoids the design burden of an edit form and GE schema editor.

---

### 3.2 Scope (File Paths)

#### Backend (`backend/`)

```
backend/
├── pyproject.toml                         # unchanged (GE and Anthropic locked in Day 1)
├── app/
│   ├── main.py                            # + register rules_router, results_router
│   ├── schemas/
│   │   ├── rules.py                       # new: GE rule, suggest/from-nl request/response
│   │   └── runs.py                        # new: run, run_result request/response
│   ├── services/
│   │   ├── ai_generator.py                # new: Anthropic client + Tool Use + prompt injection + Pydantic validation
│   │   ├── ge_engine.py                   # new: GE 1.x SQL Datasource execution
│   │   ├── rules_store.py                 # new: dq.rules CRUD (including already_saved comparison)
│   │   └── runs_store.py                  # new: dq.runs + dq.run_results write/read
│   └── api/
│       ├── rules.py                       # new: 5 endpoints
│       └── results.py                     # new: 3 endpoints
├── db/
│   └── 002_run_results_status.sql         # new: ALTER TABLE add status VARCHAR(10)
└── tests/
    ├── test_rules.py                      # new: rules endpoints + ai_generator (mocked)
    └── test_runs.py                       # new: runs endpoints + ge_engine (in-memory)
```

#### Frontend (`frontend/`)

```
frontend/
├── app/tables/[name]/page.tsx             # unchanged (tab switching already supported)
├── components/
│   ├── TableTabs.tsx                      # modified: rules/results tabs replaced with real components
│   ├── RulesView.tsx                      # new: Rule Management main view
│   ├── RuleCard.tsx                       # new: single rule card (draft/saved two states + already_saved badge)
│   ├── NlRuleInput.tsx                    # new: natural language input + clarification message
│   ├── ResultsView.tsx                    # new: Results Dashboard main view
│   ├── ResultRow.tsx                      # new: single result row (pass/fail/error three colors + expand violating samples)
│   └── RunButton.tsx                      # new: Run button + loading state
├── lib/
│   ├── queries.ts                         # + useRules / useRun / useLatestRun
│   └── mutations.ts                       # new: useSuggestRules / useSaveRule / useDeleteRule / useNlRule / useTriggerRun
└── types/
    └── api.ts                             # extended: Rule, RuleDraft, RunSummary, RunResult, ResultStatus
```

#### Docs (`docs/`)

```
docs/
├── day2-plan.md                           # this document
└── ai-tools-usage.md                      # updated daily with Day 2 entries
```

---

### 3.3 Design Details

#### 3.3.1 Backend — Schemas

**`app/schemas/rules.py`**

```python
class GeRule(BaseModel):
    """Standard structure for a single GE rule (used in store, API, ai_generator output)"""
    expectation_type: str           # e.g. "expect_column_values_to_not_be_null"
    kwargs: dict[str, Any]          # e.g. {"column": "national_id"}
    description: str                # plain-language description for non-technical users

class RuleRecord(GeRule):
    """Rule read from DB, including id / table_name / source / timestamps"""
    id: int
    table_name: str
    source: Literal["ai_schema", "ai_nl", "user"]
    created_at: datetime
    updated_at: datetime

class RuleDraft(GeRule):
    """Draft returned by LLM suggest, including already_saved comparison result (D#22)"""
    already_saved: bool

class SuggestRequest(BaseModel):
    table_name: str

class SuggestResponse(BaseModel):
    drafts: list[RuleDraft]
    # raw LLM response not returned — already structured via Tool Use

class NlRuleRequest(BaseModel):
    table_name: str
    description: str = Field(min_length=3, max_length=500)

class NlRuleSuccess(BaseModel):
    type: Literal["rule"] = "rule"
    rule: GeRule

class NlRuleClarification(BaseModel):
    type: Literal["clarification"] = "clarification"
    question: str

NlRuleResponse = NlRuleSuccess | NlRuleClarification  # discriminated union

class CreateRuleRequest(GeRule):
    table_name: str
    source: Literal["ai_schema", "ai_nl", "user"] = "user"

class UpdateRuleRequest(GeRule):
    pass  # PUT can only change expectation_type / kwargs / description; cannot change table_name / source
```

**`app/schemas/runs.py`**

```python
ResultStatus = Literal["pass", "fail", "error"]

class RunResult(BaseModel):
    id: int
    rule_id: int | None              # None when rule has been deleted; historical results are preserved
    expectation_type: str
    status: ResultStatus              # D#18 three states
    success: bool                     # retained field; pass=True, fail/error=False
    unexpected_count: int | None
    unexpected_sample: list[Any] | None   # 1–3 sample values (CLAUDE.md constraint)
    observed_value: Any | None
    error_message: str | None         # populated when status=error

class RunSummary(BaseModel):
    id: int
    table_name: str
    status: Literal["success", "failed"]  # whether the overall run completed (not individual rule pass/fail)
    started_at: datetime
    completed_at: datetime | None
    error_message: str | None
    pass_count: int
    fail_count: int
    error_count: int

class RunDetail(RunSummary):
    results: list[RunResult]

class CreateRunRequest(BaseModel):
    table_name: str
```

#### 3.3.2 Backend — Services

**`app/services/rules_store.py`**

Pure SQL helpers (via SQLAlchemy `text()`); no ORM declarative model (avoids writing a model class for just 4 columns at MVP scale).

```
list_rules(session, table_name: str | None) -> list[RuleRecord]
get_rule(session, rule_id: int) -> RuleRecord | None
create_rule(session, table_name: str, source: str, rule: GeRule) -> RuleRecord
update_rule(session, rule_id: int, rule: GeRule) -> RuleRecord
delete_rule(session, rule_id: int) -> bool
mark_drafts_already_saved(session, table_name: str, drafts: list[GeRule]) -> list[RuleDraft]
    # D#22: compare (expectation_type, kwargs) — kwargs comparison uses canonical JSON dump (sort_keys=True)
```

**`app/services/runs_store.py`**

```
create_run(session, table_name: str) -> int  # returns run_id, status='running' (transitional state, internal use)
finalize_run(session, run_id: int, status: 'success'|'failed', error_message: str | None) -> None
write_result(session, run_id: int, rule_id: int, result: RunResult) -> None
get_run(session, run_id: int) -> RunDetail | None
list_runs(session, table_name: str | None, limit: int = 20) -> list[RunSummary]
get_latest_run_for_table(session, table_name: str) -> RunDetail | None  # for Results Dashboard initial load
```

**`app/services/ai_generator.py`**

```python
class AiGenerator:
    def __init__(self): self.client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    def suggest_rules(self, table_name: str, columns: list[ColumnInfo], sample_rows: list[dict]) -> list[GeRule]:
        prompt = load_template("rule_from_schema.md", {
            "table_name": table_name,
            "columns_json": json.dumps([c.model_dump() for c in columns], indent=2),
            "sample_rows_json": json.dumps(sample_rows[:20], default=str, indent=2),  # cap at 20 rows (existing prompt constraint)
        })
        response = self.client.messages.create(
            model=settings.LLM_MODEL,
            max_tokens=4096,
            tools=[PROPOSE_RULES_TOOL],
            tool_choice={"type": "tool", "name": "propose_rules"},
            messages=[{"role": "user", "content": prompt}],
        )
        return self._extract_and_validate_rules(response)

    def rule_from_nl(self, table_name: str, columns: list[ColumnInfo], description: str) -> NlRuleResponse:
        prompt = load_template("rule_from_nl.md", {...})
        response = self.client.messages.create(
            tools=[PROPOSE_RULE_TOOL, REQUEST_CLARIFICATION_TOOL],
            tool_choice={"type": "any"},  # force calling one of the tools
            ...
        )
        return self._dispatch_nl_response(response)
```

Tool schemas defined inline in `ai_generator.py` (not in a separate file, for ease of modification):

```python
PROPOSE_RULES_TOOL = {
    "name": "propose_rules",
    "description": "Return between 5 and 10 GE expectation rules",
    "input_schema": {
        "type": "object",
        "properties": {
            "rules": {
                "type": "array",
                "minItems": 5,
                "maxItems": 10,
                "items": {
                    "type": "object",
                    "required": ["expectation_type", "kwargs", "description"],
                    "properties": {
                        "expectation_type": {"type": "string"},
                        "kwargs": {"type": "object"},
                        "description": {"type": "string"},
                    },
                },
            }
        },
        "required": ["rules"],
    },
}
# PROPOSE_RULE_TOOL (single rule) and REQUEST_CLARIFICATION_TOOL follow the same structure
```

**Pydantic second-pass validation**: Tool Use guarantees structural correctness, but not semantic correctness. `_extract_and_validate_rules` must:
1. Extract `input.rules` from the tool_use block
2. Feed each rule into `GeRule.model_validate(...)` (raise `LlmOutputError` on failure)
3. Return `list[GeRule]`

**`app/services/ge_engine.py`**

```python
class GeEngine:
    def __init__(self):
        # GE 1.x ephemeral context (does not write to GE's built-in store)
        self.context = gx.get_context(mode="ephemeral")
        # DATABASE_URL conversion: postgresql+psycopg:// → postgresql:// (GE does not recognize SQLAlchemy dialect prefix)
        pg_url = settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)
        self.datasource = self.context.data_sources.add_postgres(
            name="dq_pg",
            connection_string=pg_url,
        )

    def run_rules(self, table_name: str, rules: list[RuleRecord]) -> list[RunResult]:
        """Run a set of rules against a single table; return structured results (does not write DB — runs_store is responsible)"""
        asset = self.datasource.add_table_asset(name=f"asset_{table_name}", table_name=table_name)
        batch_def = asset.add_batch_definition_whole_table(name=f"batch_{table_name}")
        batch = batch_def.get_batch()

        results: list[RunResult] = []
        for rule in rules:
            try:
                expectation = self._build_expectation(rule.expectation_type, rule.kwargs)
                ge_result = batch.validate(expectation)
                results.append(self._normalize_pass_fail(rule, ge_result))
            except Exception as e:
                results.append(self._normalize_error(rule, e))
        return results

    def _build_expectation(self, expectation_type: str, kwargs: dict) -> gx.expectations.Expectation:
        # Use getattr to retrieve the class from gx.expectations (e.g. ExpectColumnValuesToNotBeNull)
        # GE expectation_type is snake_case; class name is CamelCase — use a simple mapping table or inflection function
        ...
```

**Result normalization**:
- `_normalize_pass_fail`: derives `status` from `ge_result.success`; `unexpected_count` from `result.result.get("unexpected_count")`; `unexpected_sample` from `result.result.get("partial_unexpected_list", [])[:3]`
- `_normalize_error`: `status="error"`, `error_message=str(e)`, `unexpected_*=None`, `success=False`

**Potential pitfall**: In GE 1.x with a SQL backend, `partial_unexpected_list` behavior for some expectations differs from the Pandas backend — may need to set `result_format={"result_format": "SUMMARY", "partial_unexpected_count": 3}` in the `validate()` call.

#### 3.3.3 Backend — API Endpoints

**`app/api/rules.py`**

```
POST /rules/suggest                     body: SuggestRequest        → SuggestResponse
POST /rules/from-nl                     body: NlRuleRequest         → NlRuleResponse
GET  /rules?table_name={name}           query                        → list[RuleRecord]
POST /rules                             body: CreateRuleRequest      → RuleRecord
PUT  /rules/{id}                        body: UpdateRuleRequest      → RuleRecord
DELETE /rules/{id}                                                   → {ok: True}
```

**`app/api/results.py`**

```
POST /runs                              body: CreateRunRequest       → RunDetail
GET  /runs/{id}                                                       → RunDetail
GET  /runs?table_name={name}            query                         → list[RunSummary]
```

**New error codes (extensions to `main.py`'s `code_map`)**:
- `LLM_TIMEOUT` — Anthropic API unresponsive for > 60s. user_message: "The AI service is temporarily unresponsive. Please try again later."
- `LLM_OUTPUT_INVALID` — Tool use structure passes but Pydantic validation fails. user_message: "The AI returned an invalid rule format. Please retry."
- `RULE_NOT_FOUND` — PUT/DELETE on a non-existent rule_id.
- `RUN_NOT_FOUND` — GET on a non-existent run_id.
- `GE_EXECUTION_FAILED` — `run_rules()` fails entirely (not an individual rule error). user_message: "Rule execution failed. Please check the table name or column configuration."

#### 3.3.4 Frontend — Components

**`RulesView`** (root of the rules tab)

```
─────────────────────────────────────────
│ [✨ Suggest rules]  [✏️ Add rule by description ▼]
─────────────────────────────────────────
│ Suggested (drafts)                    │  ← only appears after suggest
│ ┌──────────────────────────────────┐  │
│ │ expect_column_values_to_not_be_null │
│ │ Every policyholder must have...    │
│ │ Already saved                      │  ← if already_saved=true
│ │                  [Save][Discard]    │  ← Save disabled if already_saved
│ └──────────────────────────────────┘  │
│                                        │
│ Saved rules (8)                        │
│ ┌──────────────────────────────────┐  │
│ │ expect_column_values_to_be_in_set  │
│ │ Gender must be one of M/F/U.       │
│ │                          [Delete]   │
│ └──────────────────────────────────┘  │
─────────────────────────────────────────
```

**`NlRuleInput`** — collapsible; when expanded shows a textarea + Submit button. When the backend returns `clarification`, the `question` is shown in a red alert box above the textarea; the textarea is not pre-populated with the previous input (D#21).

**`ResultsView`**

```
─────────────────────────────────────────
│ [▶️ Run checks]    Last run: 5 min ago │
│                    8 pass · 2 fail · 1 error
─────────────────────────────────────────
│ ✅ National ID is never null            │
│    Pass                                  │
│ ❌ Gender must be M/F/U                 │
│    3 violating rows. Sample: ["X","Q","Z"] │
│    ▼ See more                            │
│ ⚠️  Premium between 0 and 100000        │
│    Error: column "premium" does not exist
│    Check the rule configuration.         │
─────────────────────────────────────────
```

Color palette: green = `text-green-600 bg-green-50`, red = `text-red-600 bg-red-50`, yellow = `text-amber-600 bg-amber-50`.

**`lib/mutations.ts`**

```typescript
export const useSuggestRules = (tableName: string) =>
  useMutation({
    mutationFn: () => apiFetch<SuggestResponse>("/rules/suggest", { method: "POST", body: { table_name: tableName }}),
  });

export const useSaveRule = (tableName: string) =>
  useMutation({
    mutationFn: (rule: CreateRuleRequest) => apiFetch<RuleRecord>("/rules", { method: "POST", body: rule }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["rules", tableName] }),
  });

export const useDeleteRule = (tableName: string) =>
  useMutation({
    mutationFn: (id: number) => apiFetch(`/rules/${id}`, { method: "DELETE" }),
    onMutate: async (id) => {  // Optimistic UI
      await queryClient.cancelQueries({ queryKey: ["rules", tableName] });
      const prev = queryClient.getQueryData<RuleRecord[]>(["rules", tableName]);
      queryClient.setQueryData<RuleRecord[]>(["rules", tableName], (old) => old?.filter(r => r.id !== id) ?? []);
      return { prev };
    },
    onError: (_e, _id, ctx) => ctx?.prev && queryClient.setQueryData(["rules", tableName], ctx.prev),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["rules", tableName] }),
  });

export const useTriggerRun = (tableName: string) =>
  useMutation({
    mutationFn: () => apiFetch<RunDetail>("/runs", { method: "POST", body: { table_name: tableName }}),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["runs", tableName] }),
  });
```

`apiFetch` requires a small extension to support `method` and `body` (Day 1 only supported GET).

---

### 3.4 Risks and Reversibility

| Risk | Severity | Reversibility | Mitigation |
|------|----------|---------------|------------|
| GE 1.x SQL Datasource behaves differently from Pandas backend for some expectations (e.g., `partial_unexpected_list` is empty) | High | Medium | `_normalize_pass_fail` handles `None` samples + set `result_format={"result_format": "SUMMARY", "partial_unexpected_count": 3}` in `validate()` call |
| Anthropic Tool Use returns `kwargs` with unexpected types (e.g., numeric string instead of number) | Medium | Easy | Pydantic `ConfigDict(strict=False)` + GeRule.kwargs has no strict typing; GE will route to `status=error` (D#18) if type is wrong — no crash |
| DATABASE_URL conversion to GE format drops query string (e.g., `?sslmode=require`) | Medium | Easy | `replace("postgresql+psycopg://", "postgresql://")` only touches the scheme, not the rest — add a test to cover this |
| Repeated Suggest calls waste tokens | Low | Easy | Add hash-based cache in Day 3; not defended in Day 2 |
| Optimistic delete race condition on backend failure (user quickly clicks delete on two different rules) | Low | Easy | `onError` rollback uses `ctx.prev`; TanStack Query provides serialization guarantees |
| GE exception `error_message` contains sensitive information (DB structure, connection string) | Medium | Easy | `_normalize_error` truncates message to 200 characters and removes any substring containing `postgresql://` |
| Three-state migration `002` run on Supabase forgets NOT NULL default | Medium | Easy | `002_*.sql` uses `ALTER TABLE ... ADD COLUMN status VARCHAR(10) NOT NULL DEFAULT 'pass'`; subsequent writes will overwrite the default |

**Hardest decisions to reverse**:
- **D#16 (GE SQL Datasource)**: Switching to Pandas path requires rewriting most of `ge_engine.py`; estimated 4–6 hours.
- **D#18 (three states)**: Rolling back to two states requires changing migration + store + API + frontend; estimated 2 hours.

---

### 3.5 Rollout Phases (Each Phase with Verification)

> Each phase's Verification must pass before entering the next phase.

#### Phase 1: Schemas + DB Migration (est. 1 hour)

**Outcome**: DB gains the `status` three-state column; Pydantic models and `rules_store` CRUD are in place; the backend's "data shape" is finalized.

Tasks:
1. Write `db/002_run_results_status.sql` and run it in the Supabase SQL editor.
2. Write `app/schemas/rules.py`, `app/schemas/runs.py`.
3. Write `app/services/rules_store.py` (pure CRUD, no AI).

**Verification**:
- `psql` query `SELECT column_name FROM information_schema.columns WHERE table_schema='dq' AND table_name='run_results';` includes `status`.
- `uv run pytest tests/test_rules.py::test_rules_store_crud` passes (write one row via fixture, read it back, delete it).

#### Phase 2: AI Generator + Rules Endpoints (est. 3–4 hours)

**Outcome**: All six `/rules` endpoints are live; Anthropic Tool Use integration is complete; the full "Suggest → mark duplicates → NL-to-rule → CRUD" flow can be tested with curl.

Tasks:
1. Implement `suggest_rules` and `rule_from_nl` in `services/ai_generator.py`, including Tool Use schemas.
2. Five endpoints in `api/rules.py`.
3. Register `rules_router` in `main.py`.
4. Add mocked Anthropic client endpoint tests in `tests/test_rules.py`.

**Verification**:
- `curl -X POST http://localhost:8000/rules/suggest -d '{"table_name":"policyholders"}'` returns 5–10 drafts, each with `already_saved: false` (DB is empty).
- Then `curl -X POST http://localhost:8000/rules -d '<one rule from above>'` persists it; calling suggest again shows the same rule with `already_saved: true`.
- `curl -X POST .../rules/from-nl -d '{"table_name":"policies","description":"premium cannot be negative"}'` returns `{type:"rule",...}`.
- Vague input `{"description": "data must be good"}` returns `{type:"clarification", question:"..."}`.
- `uv run pytest tests/test_rules.py` all green.

#### Phase 3: GE Engine + Runs Endpoints (est. 3–4 hours)

**Outcome**: GE 1.x SQL Datasource runs against Postgres; `POST /runs` synchronously executes all rules for a table; results are written to DB with three states (pass/fail/error); `GET /runs` reads historical results.

Tasks:
1. Implement `GeEngine.run_rules` in `services/ge_engine.py`.
2. Write/read logic in `services/runs_store.py`.
3. Three endpoints in `api/results.py`.
4. Register `results_router` in `main.py`.
5. `tests/test_runs.py` — use in-memory SQLite + GE against SQLite datasource to validate the flow (no Supabase hit).

**Verification**:
- Manually `INSERT INTO public.policyholders (national_id, full_name, birth_date, gender) VALUES (NULL, 'dirty', '2020-01-01', 'X');` in Supabase to create a dirty row.
- `curl -X POST http://localhost:8000/runs -d '{"table_name":"policyholders"}'` returns `RunDetail` with at least 1 result with `status="fail"` (gender not in set) and 1 with `status="fail"` (national_id is null).
- `curl http://localhost:8000/runs/<id>` returns the same result.
- Intentionally INSERT a rule pointing to a non-existent column `nonexistent_col`; after a run, that rule has `status="error"` with `error_message` containing "does not exist."

#### Phase 4: Frontend Rule Management (est. 4–5 hours)

**Outcome**: The `/tables/[name]?tab=rules` page is usable — Suggest produces draft cards, Save/Discard works, the NL input box works, and Delete has optimistic UI.

Tasks:
1. `components/RulesView.tsx`, `RuleCard.tsx`, `NlRuleInput.tsx`.
2. `lib/mutations.ts`; extend `lib/api.ts` to support POST/PUT/DELETE.
3. Replace the rules tab placeholder in `TableTabs.tsx` with `<RulesView />`.
4. Extend `types/api.ts`.

**Verification**:
- Open `/tables/policyholders?tab=rules`, click Suggest, see 5–10 draft cards within 3 seconds.
- Click Save on one card; the card disappears (or disables), and the rule appears in the "Saved rules" section below.
- Click Suggest again; the same rule's card shows an "Already saved" badge with Save disabled.
- In the NL input, type "premium cannot be negative" — see a draft card; type "data must be good" — see a clarification message.
- Click Delete on any saved rule; the card disappears immediately (optimistic), and after backend confirmation the list refetches.

#### Phase 5: Frontend Results Dashboard (est. 3–4 hours)

**Outcome**: The `/tables/[name]?tab=results` page is usable — the Run button triggers execution, results display in three colors (red/yellow/green), expandable rows show violating samples, and the full demo loop is closed.

Tasks:
1. `components/ResultsView.tsx`, `ResultRow.tsx`, `RunButton.tsx`.
2. `useTriggerRun` mutation, `useLatestRun` query.
3. Replace the results tab in `TableTabs.tsx` with `<ResultsView />`.

**Verification**:
- `/tables/policyholders?tab=results` initial load: if `dq.runs` has no history, show empty state "Click Run to start checking."
- Click Run; button enters loading state; results appear within 2 seconds — green/red/yellow colored rows visible.
- Expand any red row; see violating sample and count.
- Switch to Rules tab, delete a rule, return to Results tab and refresh — previous run results still display (read from DB); clicking Run again produces new results that exclude the deleted rule.
- Shut down the backend, refresh — see `<ErrorState>` (reusing Day 1 D#10).

#### Phase 6: Documentation and README (est. 1 hour)

**Outcome**: `ai-tools-usage.md` updated with Day 2 entries; README "5-minute demo" includes the INSERT dirty row command; CLAUDE.md checklist is checked off; anyone who clones the repo can complete the full flow on their own.

Tasks:
1. Update `docs/ai-tools-usage.md` with Day 2 entries (including prompt template iteration, Tool Use schema design tradeoffs).
2. Update `README.md` "5-minute demo" section to include:
   - SQL to manually INSERT a dirty row (for demo fail results)
   - Step-by-step "Suggest → Save → NL → Run" flow
3. Update `CLAUDE.md` Task Breakdown, checking off Day 2 items.

**Verification**:
- Fresh clone of the repo; following the README, complete the demo in under 5 minutes.
- `docs/ai-tools-usage.md` has at least 4 Day 2 entries (covering prompt iteration, Tool Use schema design, GE 1.x debugging, UI component design).

---

### 3.6 Day 3 Entry Conditions

All of the following must be true before entering Day 3:

- [x] `POST /rules/suggest` returns a draft array containing `already_saved`.
- [x] `POST /rules/from-nl` supports both rule and clarification responses.
- [x] `GET/POST/PUT/DELETE /rules` full CRUD passes curl tests.
- [x] `POST /runs` executes synchronously and returns `RunDetail`; `dq.run_results.status` writes three-state values.
- [x] `GET /runs/{id}` and `GET /runs?table_name=X` work correctly.
- [x] Frontend Rule Management: Suggest / Save / Discard / NL input / Delete all operable.
- [x] Frontend Results Dashboard: Run / three-color display / expand violating samples all operable.
- [x] `db/002_run_results_status.sql` has been run on Supabase. ← cannot verify from code; confirm manually in Supabase SQL Editor
- [x] `docs/ai-tools-usage.md` contains at least 4 Day 2 entries.
- [x] README 5-minute demo can reproduce the full flow (including INSERT dirty row).
