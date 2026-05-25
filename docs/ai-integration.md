# AI Integration — AI-Powered Data Quality Assistant

This document explains **why the AI parts of the system are designed the way they
are**. It is the companion to [`architecture.md`](./architecture.md) (which covers
*how the system runs*) — here the focus is the prompt design, the structured-output
mechanism, the multi-turn conversation model, and the response cache. Decisions are
referenced as `D#n`; their full reasoning lives in the Decision Logs of
[`day1-plan.md`](./day1-plan.md), [`day2-plan.md`](./day2-plan.md), and
[`day3-plan.md`](./day3-plan.md).

All LLM calls go through one place: `app/services/ai_generator.py`. There are three
AI capabilities — **suggest rules from a schema**, **translate plain English into a
rule (multi-turn)**, and **explain a failure** — and they share the same three
design pillars: Tool Use for structured output, Markdown prompt templates, and a
DB-backed response cache.

## 1. Structured output via Anthropic Tool Use (D#7)

Every LLM call uses **Anthropic Tool Use** rather than asking the model to "reply
with JSON." The model is forced to emit a tool call whose `input` matches a JSON
Schema, so the response is machine-readable by construction — no markdown fences,
no prose preamble, no trailing-comma parse failures.

Tool Use guarantees the output is *structurally* valid but not *semantically*
valid (e.g. the model could return a misspelled `expectation_type` that GE will
later reject). So there is a **second validation pass**: every tool output is run
through a Pydantic model (`GeRule`, `ExplainResponse`, …). A failure raises
`LlmOutputError`, which the API layer maps to the `LLM_OUTPUT_INVALID` error code —
the user gets a clean retryable error instead of a crash deep inside GE execution.

```
LLM → tool_use block (schema-valid JSON)  →  Pydantic.model_validate()  →  use / persist
                                              └─ on failure: LlmOutputError → LLM_OUTPUT_INVALID
```

### The four tool schemas

All four are defined inline in `ai_generator.py` (not in separate files) so a schema
edit lives next to the code that calls it.

| Tool | Used by | Shape | `tool_choice` |
|------|---------|-------|---------------|
| `propose_rules` | suggest rules | `{rules: [{expectation_type, kwargs, description}]}`, `minItems 5, maxItems 10` | `{"type":"tool","name":"propose_rules"}` — force this one tool |
| `propose_rule` | NL → rule | a single `{expectation_type, kwargs, description}` | `{"type":"any"}` — model picks (see below) |
| `request_clarification` | NL → rule | `{question}` | `{"type":"any"}` |
| `explain_failure` | explain | `{explanation, possible_causes[2-4], suggested_action}` | `{"type":"tool","name":"explain_failure"}` |

Two different forcing strategies, on purpose:

- **Single forced tool** (`suggest_rules`, `explain_failure`): there is exactly one
  valid output shape, so we name the tool and require it. This removes the failure
  mode where the model returns a text answer instead of structured output.
- **`tool_choice: any` over two tools** (`rule_from_nl`): the model must call *one
  of* `propose_rule` or `request_clarification`, and it chooses based on whether the
  user's description is specific enough to translate. This is how the
  "ask a clarifying question when too vague" UX is implemented **without** any
  stateful branching logic on the backend — the decision lives in the model, and the
  backend just dispatches on which tool came back (`_dispatch_nl_response`).

## 2. Prompt templates

Prompts are Markdown files in `app/prompts/` with `{{variable}}` placeholders.
`_load_template()` reads the file and does plain string substitution — no template
engine, because the substitution need is trivial and a dependency would not earn its
keep. Keeping prompts as standalone `.md` files (rather than Python string literals)
means they are diff-friendly and reviewable as prose.

There are three templates, one per capability.

### `rule_from_schema.md` — suggest rules

- **Role framing**: "a data quality expert with deep knowledge of the personal
  insurance domain." The domain anchoring (D#1) is what makes suggestions look like
  genuine insight (`premium must not be negative`, `expiry after effective date`)
  rather than generic `not_null` checks.
- **Reason from first principles, not just the sample**: the prompt explicitly says
  *do not limit yourself to what looks dirty in the sample* — think about what must
  always be true. This is the core of D#2: the seed data is clean, so the value on
  display is the model *inferring* rules, not pattern-matching visible dirt.
- **Guardrails that keep output runnable**: single-table only (no cross-table joins,
  which GE can't do on one batch), standard GE expectations only ("do not invent
  expectation names"), plain-English descriptions aimed at a compliance officer, no
  duplicate dimensions.
- **Inputs**: `{{table_name}}`, `{{columns_json}}`, and `{{sample_rows_json}}` (capped
  at 20 rows in the caller). Three few-shot examples show the exact rule shape.
- **Output**: "You MUST call the `propose_rules` tool. Do not write free text."

### `rule_from_nl.md` — translate plain English (system prompt)

- Used as the **system prompt** for a multi-turn conversation (see §3), so it carries
  the persistent instructions while the turn-by-turn content rides in `messages`.
- Same guardrails as above (standard expectations only, single-table only, map only
  to columns that exist) plus an explicit instruction to use `request_clarification`
  when the rule needs a cross-table join or references a non-existent column.
- **Concision instruction**: "Keep responses concise. Do not repeat earlier
  explanations." This is a deliberate token-control measure for multi-turn (D#25),
  where history accumulates each turn.
- Documents the two output tools and ends with "You MUST call either `propose_rule`
  or `request_clarification`. Do not return free text."

### `explain_failure.md` — explain a failure (D#30)

- **Audience framing is the whole point**: "helping a **non-technical domain
  expert**… Keep your response brief and jargon-free. Do not mention Great
  Expectations, SQL, or internal technical details." The three-colour result already
  tells the user *that* something failed; this prompt's job is *why* and *what to do*
  in language they can act on.
- **Inputs**: `{{table_name}}`, `{{expectation_type}}`, `{{kwargs_json}}`,
  `{{unexpected_sample_json}}`, `{{observed_value_json}}` — the rule plus the actual
  violating values, so the explanation is concrete.
- **Three-part output** via the `explain_failure` tool: `explanation` (1–2 sentences),
  `possible_causes` (2–4 bullets), `suggested_action` (1 sentence).
- Carries an explicit PII note: "Demo data is fake; production deployments should mask
  PII before sending to the LLM" — see the PII-masking item in `architecture.md` §9.

## 3. Multi-turn NL conversation (D#25)

The NL endpoint is a real multi-turn chat, but the **backend is stateless** — it
stores no conversation. The full history is sent on every request and the backend
rebuilds it into the Anthropic Messages format each time. This leans on the Anthropic
API's own stateless design instead of inventing a server-side session resource.

- **Wire shape**: the request carries `messages: ChatMessage[]`, where a
  `ChatMessage` is `{role: "user" | "assistant", content: str}`. Assistant turns
  store the **JSON-serialised `NlRuleResponse`** from the previous reply (the proposed
  rule or the clarification question).
- **Reconstruction** (`_build_anthropic_messages`): assistant turns are turned back
  into proper `tool_use` blocks, and the following user turn is wrapped so it opens
  with the matching `tool_result` block before the new user text. Anthropic requires a
  `tool_use` to be answered by a `tool_result`, so this pairing is what makes the API
  accept replayed history.

  ```
  stored assistant msg (JSON)         → assistant turn: [tool_use  id=tu_00N name=propose_rule input=…]
  next user msg                       → user turn:      [tool_result tool_use_id=tu_00N "OK", text="…"]
  ```

- **Malformed-history fallback**: if a stored assistant message can't be parsed as
  the expected JSON, it is passed through as plain assistant text rather than dropped —
  the conversation degrades gracefully instead of erroring.
- **Turn cap**: 5 user turns (10 messages), enforced both in the UI and as a Pydantic
  `max_length=10` on the request — a UI nudge plus a hard server guarantee.
- **Privacy**: history lives only in the browser (no persistence), which is also a
  privacy feature because NL prompts may contain PII. See the cross-device chat item
  in `architecture.md` §9 for the deferred server-side-persistence path.

## 4. Response cache and the prompt-change SOP (D#24)

Every LLM path is cached in the `dq.llm_cache` Postgres table so repeated calls on
identical input skip the model. (Why a DB table rather than Redis, and the GC story,
are in `architecture.md` §9.2 — this section is about the *key*.)

### Cache key

`make_cache_key(prompt_name, prompt_version, **payload)` builds a canonical JSON of
`{prompt_name, prompt_version, …payload}` with `sort_keys=True`, then takes its
sha256. Sorting keys makes the key independent of dict ordering, so the same logical
input always hashes the same way.

The payload differs per path so the key captures exactly what the output depends on:

| Path | Key payload |
|------|-------------|
| `rule_from_schema` | `table_name`, `columns`, `sample` (first 20 rows) |
| `rule_from_nl` | `table_name`, `columns`, full `messages` history |
| `explain_failure` | `rule_id`, `unexpected_sample` |

Consequences worth noting:

- For suggestion, the key includes the **sample rows** — so if the underlying data
  changes, the sample changes, the key changes, and the cache correctly misses and
  re-generates. The cache only short-circuits when the input is genuinely identical.
- For NL, the key includes the **whole conversation**, so each distinct turn sequence
  is its own entry. A long shared system prompt with a short new user turn still
  benefits because identical earlier turns reuse nothing — but the design favours
  correctness (never serve a stale answer for a different conversation) over maximal
  hit rate.
- For explain, the key is just `rule_id` + the violating sample, so re-opening the
  same failed row is instant while a different rule or different violating values
  generate a fresh explanation.

### Prompt-change SOP

There is no automatic prompt-version detection. Note that the version does **not**
live in the prompt `.md` file — it is a plain constant in `ai_generator.py`, one per
prompt path:

```python
# backend/app/services/ai_generator.py
PROMPT_VERSION_SCHEMA  = "v1"
PROMPT_VERSION_NL      = "v2"   # bumped when NL moved single-shot → multi-turn
PROMPT_VERSION_EXPLAIN = "v1"
```

These constants are part of the cache key. **The rule: whenever you edit a prompt
`.md` file (or change the model), bump the matching constant.** Because the version is
in the key, bumping it makes every old entry for that path unreachable, so stale
responses are never served after a prompt change. `PROMPT_VERSION_NL` is already at
`v2` — it was bumped when the NL prompt moved from single-shot to multi-turn, which
correctly invalidated all single-turn entries.

The known weakness of this manual SOP is that a developer can edit a prompt and
forget to bump the constant, causing stale cached responses to be served. A possible
hardening is to derive the version automatically from a hash of the prompt file's
contents, so the version always tracks the prompt.

### Storage and lifetime

`set_cached` upserts `(cache_key, prompt_name, response JSONB, expires_at)` with a
24-hour TTL and resets `hit_count` to 0 on conflict; `get_cached` returns a non-expired
entry and increments `hit_count`. `prompt_name` and `hit_count` make the cache
observable — e.g. `SELECT prompt_name, hit_count FROM dq.llm_cache ORDER BY hit_count
DESC` quantifies how often each path is being served from cache.
