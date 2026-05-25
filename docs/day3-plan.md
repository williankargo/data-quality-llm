# Day 3 Architecture Plan — AI-Powered Data Quality Assistant

本文件是 Day 3 的完整規劃，承接 [day1-plan.md](./day1-plan.md) 與 [day2-plan.md](./day2-plan.md) 的決策（D#0–D#22 仍然有效）。Day 3 在解 `CLAUDE.md` 列出的 polish 項目之餘，**主動 revisit 了 Day 2 為了「先求有」做的多項 start-from-simple 決策**——目的是讓最終交付品在 AI-First / Product Thinking / Technical Implementation 三大評分項都站得住腳。

---

## Day 3 範圍與優先級

Day 3 範圍同時來自三個來源：

1. **`CLAUDE.md` Day 3 checklist**：error handling、input validation、LLM caching、UI polish、performance（parallel exec / sample cap）、4 份 docs。
2. **Bonus 選定**：LLM 自動解釋 failure（最高 AI-First 加分；見 D#30）。
3. **Day 2 revisit**：D#17 async runs、D#21 multi-turn NL chat、D#20 per-rule run、PUT UI（兼解 bonus diff view）。

實作時間估計 22–28 小時、單日不夠。採用**「全數寫進規劃，按 Phase 優先順序執行，時間不夠就從尾端 Phase 砍」**的策略，並把優先級明確標在 §3.5 Rollout Phases：

| 優先級 | 標記 | 砍除順序 |
|--------|------|----------|
| Must-have | M | 必須完成（沒有就無法 demo / 交付） |
| Should-have | S | 高機率影響評分（performance / Product Thinking / AI-First） |
| Nice-to-have | N | UX 完整性與 future-scalability，可酌情捨棄 |

**範圍以外**（明列於 `docs/architecture.md` 的 Future Enhancements）：
- D#19 Draft persistence（refresh 即失，影響輕微）
- D#22 改加 UNIQUE constraint on rules
- 一鍵「修正資料」與 Export GE checkpoint YAML 兩個 bonus
- Production-grade PII masking 與 multi-user auth
- Celery / 分散式 worker（Day 3 仍用 FastAPI BackgroundTasks）

---

## Section 1: Decision Log (Resolved Decisions)

每個決策都包含 **Problem Essence**（為何這是真決策而非瑣碎選擇）與 **Tradeoff**（這個選擇放棄了什麼）。

---

### D#23: Run Execution 升級為 Async — FastAPI BackgroundTasks + 前端輪詢

- **Decision**: `POST /runs` 改為非同步：
  - 立即建立 `dq.runs` 紀錄（`status='running'`）並回傳 `202 Accepted` body `{run_id, status:'running'}`。
  - GE 執行透過 `BackgroundTasks.add_task(...)` 在背景跑完，寫入 `dq.run_results` 並把 `dq.runs.status` flip 成 `success` / `failed`。
  - 前端用 `useQuery({queryKey:['runs',id], refetchInterval: q => q.state.data?.status === 'running' ? 1000 : false})` 輪詢 `GET /runs/{id}` 直到 status 結束。
  - 輪詢上限：客戶端持續 polling 沒有硬上限，但超過 60 秒會在 UI 顯示「Run is taking longer than expected — refresh to check later」提示，但仍繼續輪詢。
- **Why It Matters**: 顛覆 D#17 的 API 合約形狀；前端 `useTriggerRun` 從「mutation 直接拿 results」變成「mutation 拿 run_id → query 輪詢拿 results」，所有 results loading state 都要重寫。
- **Options Considered**:
  - 純同步 + timeout cap：簡單但對未來大表必爆 502，且無法支撐 D#30 bonus（LLM 解釋會疊加延遲）。
  - Celery / RQ + Redis broker：完整解耦但要新增 worker process、Procfile、Redis 服務，MVP 過重。
  - Server-Sent Events：UX 最順但 TanStack Query 不擅長 streaming，前端要繞 `useEffect + EventSource`。
- **How Chosen**: BackgroundTasks 是 FastAPI 內建、無新依賴；對 single-process MVP 已足夠；未來搬 Celery 只需把 `background_tasks.add_task()` 換成 `celery_task.delay()`，service layer 不動。
- **Problem Essence**: HTTP 請求模型從「同步阻塞」升級為「立即回應 + 背景作業 + 客戶端輪詢」是 web app 最常見的架構轉折，但兩種模式的 API contract 不可調和——同步 API 回完整 results，async API 只回 run_id + status，client 端的 state machine 必須翻新。如果在 Day 3 留半套（前端兩種 hook 並存），長期一定爛尾。一次性切換是「短痛勝長痛」。同時，這個升級提供了 architecture.md 中「可擴展性」段落的具體支撐：demo 時即便資料還是小，這條故事線講得通。
- **Tradeoff**: 失去「按 Run 立刻看到結果」的直覺感（會有 1–2 秒 spinner）；新增 `dq.runs.status='running'` 中間狀態，`finalize_run` 必須 atomic（用 `UPDATE ... WHERE status='running'` 避免 race condition）；BackgroundTasks 在 process 重啟時不保證 in-flight task 完成——MVP 可接受（重新觸發即可），production 必須換 Celery，此點在 `architecture.md` Future Enhancements 明列。

---

### D#24: LLM Response Cache — DB 表 `dq.llm_cache`

- **Decision**: 新增 `dq.llm_cache` 表（schema 見 §3.3.1）。`AiGenerator` 在每次 LLM call 前計算 `cache_key`，命中且未過期則直接返回；未命中則呼叫 LLM 並 INSERT。三條被快取的 prompt path：`rule_from_schema`、`rule_from_nl`、`explain_failure`（後者見 D#30）。
- **Why It Matters**: D#7 把 LLM call 包成 Tool Use；但每次 demo 同一張表多次按 Suggest 都會重打 LLM，浪費 token + 增加延遲；同時讓 D#30 bonus 的 explain 功能變得實際可用（同一個 fail row 被多次展開時不重打）。
- **Options Considered**:
  - `functools.lru_cache` / in-memory dict：最簡單但 dev hot-reload 即失效，等同沒做；多 process 不共享。
  - Redis：適合多實例但 MVP 是 single process，過重。
  - DB 表：與 `dq.rules` / `dq.runs` 一致的維運心智模型，可查詢、可觀察 `hit_count`、可手動清空。
- **How Chosen**: 不引入新依賴；可直接 SQL `SELECT hit_count, prompt_name FROM dq.llm_cache ORDER BY hit_count DESC` 量化快取效益、寫進 `ai-integration.md`。
- **Problem Essence**: 快取系統真正的設計挑戰不在「要不要快取」而在 cache invalidation。LLM 對相同 prompt 是接近 deterministic（temperature 預設為 1，但小變動不影響規則結構），所以同樣輸入 → 同樣輸出的快取假設成立。挑戰是：prompt template 改動或 LLM model 升級時，舊快取必須失效。`cache_key = sha256(prompt_name || prompt_version || table_name || columns_json || sample_rows_json || extra_user_input)`，其中 `prompt_version` 是 prompt 檔頂端的硬編碼字串（每次改 prompt 時手動 bump），是最簡單且足夠的失效機制。`expires_at` 提供時間性失效避免無限累積。
- **Tradeoff**: 多一張表的 migration（`003_llm_cache.sql`）與 store 層；suggest / nl / explain 三支 prompt 改動必須記得 bump `prompt_version`——在 `architecture.md` 留「Prompt change SOP」；hit 時是 SELECT、miss 時多一個 INSERT；JSONB 索引未加（`cache_key` 是 PRIMARY KEY 已足夠）。

---

### D#25: Multi-turn NL Chat — Stateless Backend + Frontend In-Memory State

- **Decision**: `POST /rules/from-nl` 的 request body 改為：
  ```json
  {
    "table_name": "policyholders",
    "messages": [
      { "role": "user", "content": "Premium cannot be negative." },
      { "role": "assistant", "content": "<previous assistant tool_use JSON>" },
      { "role": "user", "content": "Actually also no zero." }
    ]
  }
  ```
  Backend 完全 stateless（不存 chat history），每次把整段 messages 餵 Anthropic Messages API（這是 Anthropic 原生格式）。前端在 `RulesView` 的 React state 維護 `messages: ChatMessage[]`（**不存 sessionStorage / localStorage**，refresh 即清空）。對話上限：5 輪 user message（10 messages）；超過則 disable input 並提示「Conversation too long — please reset」。
- **Why It Matters**: D#21 Day 2 的 one-shot 模式無法應對「rule 需要進一步精細化」的真實場景，且 `CLAUDE.md` 描述為 "chat-style interface" 也需要真正的對話能力。但 stateful chat 涉及 backend session、token 管理、prompt 改寫等多個面向。
- **Options Considered**:
  - 維持 one-shot（D#21）：簡單但無法滿足 spec 對「chat-style」的期待。
  - Backend 存 session（新增 `dq.chat_sessions` 表 + CRUD + 過期機制）：過重，跨裝置續寫並非 demo 訴求。
  - Frontend in-memory React state + stateless backend：對齊 Anthropic Messages API 原生設計，無 schema 改動。
- **How Chosen**: Anthropic Messages API 本來就是 stateless（每次都送完整 history），順著用最自然；用 React state 而非 storage 是因為 LLM 對話可能含 PII（policyholder 姓名等），refresh 清空是 feature 而非 bug。
- **Problem Essence**: Multi-turn LLM application 的 state 邊界在哪？傳統 web app 直覺把 conversation 視為 server-side resource（像 GitHub issue），但 LLM API 本身是 stateless 的——server-side session 只是在重複包裝「組合 messages」這件本來該 client 做的事，徒增 schema 與生命週期管理。把 conversation 視為 client-side state（像 React form draft）省掉 session table、過期清理、認證授權，是更符合 LLM API 原生設計的選擇。同時也釐清了 product trust 模型——「對話不會被記錄到 server」對於含 PII 的 prompt 而言反而是賣點。
- **Tradeoff**: 失去「跨裝置續寫對話」（手機開的 chat 不能在電腦繼續，但這非 demo 訴求）；refresh 即清空（將「Start over」按鈕做顯式化，讓重置變成主動 UX 而非偶發 bug）；前端 `NlChatThread` 元件複雜度上升（messages state、render conversation bubbles、scroll-to-bottom）；token 成本隨對話輪數線性累積，需要 prompt 注入「請保持 concise、不重複前文」+ 5 輪 cap；Day 2 的 `NlRuleInput` 從「單欄輸入框」演進為 chat thread UI，工作量約 4 小時。

---

### D#26: PUT /rules/{id} Edit Modal + Diff View

- **Decision**: `RuleCard` 加上 `[Edit]` 按鈕；點擊開啟 `RuleEditModal`：
  - **左半**：原始 rule（read-only JSON pretty-print）。
  - **右半**：可編輯表單——`expectation_type` (select)、`kwargs` (textarea + JSON.parse 即時校驗)、`description` (textarea)。
  - **底部**：簡易 `<DiffLines>` 元件，逐欄標示變更（`expectation_type` 變了標 ▶、`kwargs` 顯示 unified diff、`description` 同左）。
  - 按 `[Save]` 觸發 `PUT /rules/{id}`；按 `[Discard]` 關閉。
- **Why It Matters**: 完整化 CRUD 的最後一塊（D#22 已決定 PUT 後端存在但 Day 2 沒做 UI）；同時直接兌現 `CLAUDE.md` bonus 第三項「Diff view when editing a suggested rule」——一石二鳥。
- **Options Considered**:
  - Inline edit（直接在 card 上面改）：UI 擁擠、JSON 沒地方放。
  - 獨立路由 `/rules/{id}/edit`：對 SPA 流程過重，新增頁面。
  - Modal + Diff：符合「review-then-confirm」的非技術 user UX 直覺。
- **How Chosen**: Modal 對流程友好（不離開當前列表）；Diff view 同時對齊 AI-First（讓 user 看清 AI 提的原始 rule vs 我改成的版本）。
- **Problem Essence**: 編輯 AI 提案是「AI 與人類協作」的關鍵互動點：AI 提建議、人類微調並保留調整紀錄。Diff view 不只是 UI 裝飾，它在告訴 user「你正在修改 AI 的輸出，這是有意識的決定」——這種「修改前後對比」本身就是 product trust 的視覺呈現。如果沒有 diff，user 改完只看到新版本，AI 的原始建議就被靜悄悄抹除，違反 D#22 的「honest design」精神。
- **Tradeoff**: `kwargs` 是 JSON object，要編輯需要 JSON editor（用 textarea + JSON.parse 校驗即可，不引入 monaco-editor）；JSON 格式錯誤的容錯——顯示 inline 紅字而非阻塞 modal；diff 計算對非常長的 `kwargs` 性能可能不佳，但 MVP 範圍 kwargs 通常 < 200 字元，自製字串 diff 足夠（不引入 `react-diff-view`）。

---

### D#28: Per-rule Run — `rule_ids` 為 Optional 參數

- **Decision**: `POST /runs` request body 加上 optional 欄位 `rule_ids?: number[]`：
  - **缺省（不傳）**：跑該 table 全部 rules（向後相容 D#20）。
  - **傳入**：只跑 `rule_ids` 列出的 rules；後端驗證它們都屬於 `table_name`，否則 `400 INVALID_RULE_IDS`。
  - 前端 `ResultsView` 新增 `<RuleFilter>`：預設折疊（demo 主流程不打擾）；展開後是每個 rule 的 checkbox + 「Run selected (N)」按鈕；預設全部勾選。
- **Why It Matters**: 兌現 D#20 預留的 hook；對「user 改完一條 rule 想立刻測它」的 review-iterate workflow 必要。
- **Options Considered**:
  - 維持 run-all（D#20）：簡單但對未來不友好。
  - 新增 `POST /runs/{table}/rules/{id}`：路由膨脹。
  - Optional `rule_ids`：完全向後相容、最少新增 API surface。
- **How Chosen**: Optional 參數是 API evolution 的標準做法，且 D#20 已預留此路徑。
- **Problem Essence**: 「執行粒度」是 data quality 工具長期分歧點。Day 2 已論證 MVP 規模不需要 per-rule。Day 3 加上的真正動機不是性能，而是「使用者修改一個 rule 後想立刻測它」——沒有 per-rule re-run，user 改完 rule 為了驗證得跑整批，從心智上會抑制「實驗」行為。`<RuleFilter>` 折疊預設收起避免干擾「按 Run 看結果」的主流程。
- **Tradeoff**: 後端要驗證 `rule_ids` 都屬於該 table（多一個 query）；前端新增 collapsible filter；新增 `INVALID_RULE_IDS` 錯誤 code 與對應 possible causes。

---

### D#29: Parallel Rule Execution — `ThreadPoolExecutor(max_workers=4)`

- **Decision**: 在 D#23 的 BackgroundTask 內部，`GeEngine.run_rules` 用 `concurrent.futures.ThreadPoolExecutor(max_workers=4)` 平行執行每個 rule 的 `batch.validate(...)`。Workers 是 sync 的（GE 1.x + SQLAlchemy 是 sync API）。Results 用 `as_completed` 收集，每完成一筆就 `write_result` 寫 DB，前端輪詢時可逐步看到累積結果（雖然 MVP 規模不會明顯）。
- **Why It Matters**: `CLAUDE.md` 明確列「parallel rule execution where independent」為 Day 3 performance 項目；對 10 條 rule × 0.5 秒場景，從 5 秒降到 1.5 秒，是「Performance」可量化的指標。
- **Options Considered**:
  - `asyncio.gather + asyncio.to_thread`：要全面改 async，與 D#4 整體 sync 模型衝突。
  - 不平行：對 MVP 影響小但 Day 3 失分。
  - `ThreadPoolExecutor`：sync 世界的標準解法。
- **How Chosen**: ThreadPoolExecutor 對 sync GE engine 最自然；`max_workers=4` 避免對 Supabase 開過多 connection。
- **Problem Essence**: Parallelism 在 Python 受 GIL 限制，但 IO-bound work（SQL query 等 Postgres 回應）會 release GIL，所以 ThreadPoolExecutor 對「多 SQL query 平行」是真有效果；CPU-bound 部分（解析 result、normalize）佔比小可忽略。重點是 connection pool size 必須 ≥ max_workers，否則 thread 會卡在等 connection——Day 1 SQLAlchemy 預設 `pool_size=5` 剛好可容納 4 worker + 主 thread。
- **Tradeoff**: ThreadPoolExecutor + Supabase Session Pooler 偶爾會出現 "connection terminated" 偽錯（連線被回收），需要在 `GeEngine` 內 retry 一次；`max_workers=4` 是硬編碼（沒 settings 控制），未來要調得改 code；rule 之間互相沒依賴是預設假設（MVP 範圍成立——未來若有 cross-rule expectations，此假設要重估）。

---

### D#30: Bonus — LLM 自動解釋 Failure（新 endpoint `POST /results/{result_id}/explain`）

- **Decision**: 為 `status='fail'` 的 `RunResult` 加上 on-demand 解釋：
  - 新 endpoint：`POST /results/{result_id}/explain` → `{ explanation: string, possible_causes: string[], suggested_action: string }`。
  - `AiGenerator.explain_failure(rule, unexpected_sample, observed_value, table_name) -> ExplainResponse`，prompt template `explain_failure.md`，用 Anthropic Tool Use 強制結構化，走 D#24 cache（cache_key 含 rule_id + unexpected_sample hash）。
  - 前端 `ResultRow` 展開後顯示 `💡 Why did this fail?` 按鈕；點擊呼叫 endpoint；返回後 inline render 解釋（含 possible_causes 子彈點 + suggested_action 行）。
- **Why It Matters**: 4 個 bonus 中對 AI-First 加分最高的一項——把 AI 從「生成規則」延伸到「協助診斷」，是非技術 user 從 demo 收場後仍會用上的功能。
- **Options Considered**:
  - 預先在 Run 時生成所有解釋：浪費 LLM call（user 可能只看 1 個 fail）。
  - On-demand button + cache：user 點才生成，cache 防止重複（user 重複展開同一 row）。
  - 自動 fetch on row expand：UX 順但 token 成本翻倍。
- **How Chosen**: On-demand button + cache 是最務實組合；user 帶著「有控制感」（不是 LLM 偷偷在背景跑）。
- **Problem Essence**: AI-First 評分的核心是「AI 解決使用者真實痛點」。Day 2 的紅黃綠 colour coding 告訴 user「有問題」，但沒告訴 user「為什麼有問題」與「該怎麼辦」——這是非技術 user 從 demo 收場後仍會 stuck 的地方。LLM 對 (rule, violating_values) 做 plain English 解釋，是把 AI 從「生成規則」延伸到「協助診斷」的自然進化，且不需重新訓練模型，只要再寫一個 prompt。同時 D#24 cache 讓「user 反覆展開同一 row」不會重打 LLM。
- **Tradeoff**: 新增 prompt template + tool schema + endpoint；每次解釋是一次 LLM call（成本 + 延遲），靠 D#24 cache 降低重複；如果 `unexpected_sample` 含 PII（national_id、姓名）會被送進 LLM——在 `architecture.md` 與 `ai-integration.md` 明確說「demo 用 fake data，production 上要先 mask」。

---

### D#31: Error Handling 補齊 — 每個 code 都有 possible_causes

- **Decision**: `ErrorState` 元件依 `error.code` 渲染對應的「Possible causes」清單。前端在 `lib/errorMessages.ts` 集中定義 `code → { title, possible_causes: string[], retry_label?: string }`。後端在 `app/api/errors.py` 提供 raise helper：
  ```python
  def raise_error(code: str, technical_detail: str, http_status: int = 500): ...
  ```
  Day 3 新增的 error codes（除 Day 2 已有）：

  | Code | HTTP | user_message |
  |------|------|--------------|
  | `LLM_TIMEOUT` | 504 | The AI service is temporarily unresponsive. |
  | `LLM_OUTPUT_INVALID` | 502 | The AI returned an invalid response. |
  | `LLM_RATE_LIMITED` | 429 | Too many AI requests. Please wait a moment. |
  | `DB_TIMEOUT` | 504 | The database is taking too long to respond. |
  | `GE_EXECUTION_FAILED` | 500 | Rule execution failed. Please check the rule configuration. |
  | `INVALID_RULE_IDS` | 400 | Some rule IDs don't belong to this table. |
  | `CACHE_CORRUPTED` | 500 | Cached response is corrupted and was discarded. |
  | `RUN_STILL_RUNNING` | 409 | This run is still in progress. |

- **Why It Matters**: D#10 Day 1 已建立 ErrorState 元件骨架；Day 3 是把它「填滿」的時候。Product Thinking 評分明確要求 error handling。
- **Options Considered**:
  - 維持 Day 1 通用 fallback：簡單但 Product Thinking 失分。
  - 每個 code 一個獨立 React 元件：過度設計。
  - 集中 `errorMessages` map：直接、易擴充。
- **How Chosen**: 對齊 D#10 已決定的 envelope + 集中 mapping 設計方向。
- **Problem Essence**: 錯誤訊息的設計成本不在 UI，而在「逐一檢視每個錯誤路徑、想清楚 user 該採取什麼行動」。例如 `LLM_TIMEOUT` 的可能原因是「Anthropic 服務忙線 / 你的網路慢 / prompt 太長」——這三條都是 user 能採取行動的方向，不是技術描述。寫出這份清單的過程本身就是 product thinking 的具體呈現。
- **Tradeoff**: 每加一個 code 都要同時改 backend raise + frontend mapping 兩處（drift 風險）；mapping 集中後若漏寫對應 message 會落入 fallback 灰色卡片，因此 dev mode 在 `console.warn` 標記未知 code。

---

### D#32: Documentation Scope — 4 份文件的分工

- **Decision**: Day 3 產出 4 份文件，內容嚴格分工避免互抄：

  - **`docs/architecture.md`** — 系統總覽、Mermaid 圖、3 層架構（API / Service / Store）、所有 D# 索引、Future Enhancements（明列 D#19/D#22/Celery/PII masking/multi-user auth）。
  - **`docs/ai-integration.md`** — Prompt template 設計理由、Tool Use schemas、cache key 策略（含「prompt change SOP」）、multi-turn history 結構、Explain Failure 的 prompt 設計、token cost 估算（以 demo 完整跑一次的實測值）。
  - **`docs/ai-tools-usage.md`** — Day 1/2/3 的所有 AI 工具使用記錄（Claude Code session 摘要、prompt iteration、debug 過程的關鍵時刻、ultrareview / architect 使用）。
  - **`README.md`** — Quick start、5-minute demo walkthrough（含 INSERT dirty row 指令 + 完整 click-through path）。

- **Why It Matters**: Documentation 直接占 Technical Implementation 評分；`ai-tools-usage.md` 是 AI-First Development 的直接證據；architecture + ai-integration 是「Bonus: clear AI tool usage documentation」的兌現。
- **Problem Essence**: 三份 docs 重疊範圍大（都會提到 Tool Use、prompts），不事先分工會內容互抄。明確分工：architecture 是「系統怎麼跑」、ai-integration 是「為什麼 AI 部分這樣設計」、ai-tools-usage 是「我用了哪些 AI 工具與遇到什麼困難」、README 是「使用者怎麼跑」。順序上先寫 README（demo 必要）→ ai-tools-usage（直接從 git log + 對話歷史摘要）→ architecture（評分主力）→ ai-integration（評分主力）。
- **Tradeoff**: 4 份加起來預估 3–4 小時；Day 3 末段時間壓力高；若時間不夠，ai-integration 可裁剪到只剩 prompt design + cache strategy 兩段、其餘併入 architecture.md。

---

### D#33: 違規 Row 顯示粒度 = 整列完整資料（不限於 PK + 違規欄位）

- **Decision**: 當 `RunResult.status='fail'` 時，UI 與後端持久化的「違規樣本」從目前的「純值陣列」（例如 `[-100, -50, 0]`，由 GE `partial_unexpected_list` 提供）升級為「完整 row 的所有欄位 dict 陣列」（例如 `[{id:42, policy_number:'P0001', premium_monthly:-100, ...}, ...]`）。`status='error'` 維持只顯示 `error_message`（見 D#35）。
- **Why It Matters**: 顛覆 Day 2 D#18 三色 status 與 Day 3 D#30 Explain Failure 共同依賴的 `unexpected_sample: list[Any]` 形狀——從純量陣列變為 dict 陣列，schema、normalize、前端展示、Explain prompt 的 sample 序列化全部要連動。
- **Options Considered**:
  - 維持純值 sample（Day 2 現狀）：對 user 無從定位「哪一筆」，違背 Product Thinking 評分項。
  - 只回 PK + 違規欄位（兩欄）：足以定位但 user 看不到上下文（例如「premium 是 -100，但 holder 是誰、保單何時生效？」這些診斷線索全失）。
  - 整列完整 row：給 user 最完整的診斷脈絡，與 Explain Failure (D#30) 的 LLM context 也更豐富。
- **How Chosen**: 由 user 在 Day 3 後段需求釐清中明確決定。判準是「非技術 user 看到一筆紅 row 後能否直接行動」——只有完整 row 提供足夠脈絡。
- **Problem Essence**: 「sample 樣本」與「violating row」是兩個層級的概念。GE 的原生輸出 `partial_unexpected_list` 只回違規欄位的「值」——這是統計式診斷工具的思維（看分佈、看離群值）。但本產品的 target user 是 domain expert，他們的診斷流程是「找出這一筆 row → 看上下文 → 決定怎麼處理」——他們要的是 row 不是值。把 sample 從「列」回升到「整 row」其實是把工具從「分析師看的報表」改成「業務人員看的工單」。這個改動同時打開了「download CSV、Explain Failure 帶 row context、未來 link 到原始記錄」等下游能力。
- **Tradeoff**: 放棄「sample size 極小、storage 廉價」的特性——`dq.run_results.unexpected_rows` JSONB 從幾十 bytes 漲到每 row 數 KB × 多筆；放棄「sample 可以直接 deserialize 成統計工具吃的數值陣列」的便利性（如果未來想接 distribution chart 會比較麻煩）；新增「row 含 PII」的隱私風險面——但這個風險本來就存在於現有 `partial_unexpected_list`（只是欄位變多放大了影響），與 D#30 共用同一 mitigation（demo data is fake，production 必須 mask）。

---

### D#34: UI 預設顯示上限 = 10 筆 + 提供完整 CSV 下載

- **Decision**: UI 在展開 `status='fail'` row 時預設顯示 **10 筆**完整違規 row（視覺形態見 D#38），並提供「Download all violations (CSV)」按鈕。CSV 內含所有違規 row（不只前 10 筆，上限見 D#37 cap 1000）。`status='pass'` 與 `status='error'` 不出現此 UI。
- **Why It Matters**: 直接影響後端要不要在 run 階段就抓所有違規 row、`dq.run_results` 是否要存全量資料、CSV endpoint 形狀（見 D#37）。
- **Options Considered**:
  - UI 顯示全部 + 無 CSV：違規 row 數可能上千，DOM 爆炸。
  - UI 預設 3 筆 + 「Load more」分頁 + 無 CSV：對 user 來說「看 row」與「分析全量」兩個任務都不順手。
  - UI 預設 10 筆 + CSV 下載：10 筆足夠 user 在 UI 內辨識 pattern，CSV 處理「我要把這份違規清單交給資料管理員」的工單場景。
- **How Chosen**: 由 user 明確決定。判準是「UI 提供 quick scan，CSV 提供 actionable artifact」——分工讓兩個任務都有對應工具。
- **Problem Essence**: 「呈現多少」這件事在 data quality 工具有兩種典型 user intent：(a) **scan**：快速判斷有沒有 systemic pattern（例如「全部都是同一個 product_type」），10 筆已足；(b) **action**：把違規清單交給下游處理（寄信給資料管理員、貼進 ticket、批次修正），需要全量。把 (a) 留在 UI、(b) 用 CSV，是用「資料形態 vs. 任務目的」對齊的設計——比「都塞進 UI 加分頁」或「都塞進 CSV 不顯示」都更貼合 user 心智模型。10 而非 5 或 20 是經驗值：5 偶爾不足以看出 pattern，20 在表格模式下會超出一個螢幕。
- **Tradeoff**: 放棄「在 UI 直接看完所有違規」的可能性（如果違規 < 10 筆其實沒差，> 10 筆 user 必須下載 CSV 才能看全貌）；新增一個 CSV download path 的工程負擔；放棄「single UI 體驗一條路走到底」的簡潔感——但這是必要的拆分。

---

### D#35: `status='error'` 不適用整列違規邏輯

- **Decision**: `status='error'` 的結果不適用 D#33 / D#34 的「整列違規 row + CSV」機制。UI 維持目前「顯示 `error_message` + 'Check the rule configuration' 提示」；後端不為 error 結果撈任何 row 資料；CSV endpoint 對 error 結果回 `400 RESULT_NOT_FAILED`。
- **Why It Matters**: 釐清「整列違規 row」這個功能的範圍邊界——避免後端誤把 error 結果（規則本身爛掉）當成「有違規資料」去硬撈 row 而再次炸。
- **Options Considered**:
  - error 也撈 row：邏輯上不通（規則無法執行就不知道誰違規），且實作上要 fallback 到「撈整表」，毫無意義。
  - error 顯示「最近一筆執行過的 row」當參考：誤導性高，user 會以為這 row 真的有問題。
  - 維持現狀：與 D#18 三色 status 的原始設計精神一致——error 是「rule 的問題」，要 user 去改 rule，不是去處理 row。
- **How Chosen**: 由 user 明確決定。判準同 D#18：error 與 fail 兩個狀態的 user 行動方向根本不同（修規則 vs. 修資料），不能混用同一套 UI 元件。
- **Problem Essence**: 此決策的價值不在「省工」，而在「守住 D#18 三色 status 的語意純度」。若 error 也走 D#34 的 CSV 路徑，UI 上 user 會以為「download CSV 看哪些 row 有問題」——但 error 的 row 一個都沒有實質「有問題」（規則根本沒跑成功）。三色 status 的設計初衷是「user 看到顏色就知道找誰」——error 顯示「整列違規」反而毀掉這個指引。
- **Tradeoff**: 無實質 tradeoff——這是 alignment 決策，唯一成本是要在 D#33 / D#34 的條目與後端程式碼中明確標記「僅適用 fail」。

---

### D#36: GE 違規 Row 取法 = `unexpected_index_column_names` + 反查 PK

- **Decision**: 後端用 GE 1.x 的 `unexpected_index_column_names` 取 PK index list，再以 `SELECT * FROM ... WHERE pk IN (...)` 補完整列；流程：
  1. **PK Inspector**（新模組 `app/services/pk_inspector.py`）查 `pg_index`/`pg_attribute`，回 table 的 PK 欄位清單（單欄或複合）。
  2. **GE Engine** 在 `batch.validate(expectation, result_format={"result_format":"COMPLETE", "unexpected_index_column_names": pk_cols, "partial_unexpected_count": 1000})`。
  3. GE 回 `partial_unexpected_index_list = [{"id":42}, ...]`，後端用這些 PK 撈完整 row。
  4. 整列寫進 `dq.run_results.unexpected_rows` JSONB（見 D#37）。
- **Why It Matters**: 直接決定整個需求的後端底座——schema、storage、CSV endpoint、Explain Failure context 都疊在它上面。
- **Options Considered**:
  - **GE `result_format='COMPLETE'` + `include_unexpected_rows=True` 直接拿整列**：1-2 小時收工，但 GE 1.x SQL backend 對「整列」的支援度未經驗證，某些 expectation_type（特別是 column-pair 或 multi-column）可能只回違規欄位的值不回整列；GE 內部對 COMPLETE 可能 load 整個 result set 進 memory（大表 OOM 風險）。
  - **跳過 GE、自行用反向 SQL**：每個 expectation_type 寫對應的「違規 WHERE clause」（例如 `expect_column_values_to_not_be_null` → `WHERE col IS NULL`）；8-12 小時，可控性最高但偏離 D#16「擁抱 GE SQL Datasource」的設計方向，長期技術債高。
  - **`unexpected_index_column_names` + 反查**：4-6 小時，依賴 GE 文件明確支援的功能，行為可預測；多一次 SELECT 但對 demo 規模無感。
- **How Chosen**: User 從三個 Decision Point 選項中選定。判準是「對齊 GE 抽象 + 行為可預測 + PK Inspector 可重用」——後續 Explain Failure 想加「跳到原始 row」連結時，PK Inspector 直接派上用場。
- **Problem Essence**: 「如何拿到整列」表面是工程實作選擇，本質是「對 GE 這個第三方抽象的信任程度」。`COMPLETE` 全信任 GE 黑盒、反向 SQL 完全不信任、`unexpected_index_column_names + 反查`是「信任 GE 給 index、不信任 GE 給整列」的折衷——把可預測性的部分（index list）留給 GE，把可控性的部分（整列資料 shape）拿回自己手中。這是一個「在抽象的縫隙處設邊界」的設計，比全信或全不信都成熟。
- **Tradeoff**: 放棄「1-2 小時收工」的開發速度，多 4 小時換來「行為可預測」；多一次 SELECT 撈整列的 SQL round-trip（每個 fail 規則一次）；**無 PK 表 fallback**：若 PK Inspector 偵測到 table 無 PK，`unexpected_rows=null`，UI 顯示「This table has no primary key — row data unavailable」，列為已知限制（示範表 policyholders / policies / claims 都有單欄 PK `id SERIAL`，demo 不受影響；架構文件明列為 Future Enhancement）；**複合 PK 邊界**：`unexpected_index_column_names=["a","b"]` 是 GE 1.x 支援的形式，IN clause 用 tuple `WHERE (a,b) IN ((1,2),(3,4),...)`——但 GE 1.x SQL backend 對複合 PK 的實際支援度需 Phase 7 第一個 task spike 驗證，不通則該 table 走無 PK fallback。

---

### D#37: CSV Download = `unexpected_rows` JSONB 持久化 + cap 1000；stale GC 為 Future Enhancement

- **Decision**: 違規 row 在 run 完成時就持久化到 `dq.run_results.unexpected_rows` JSONB（新欄位，migration `004_run_results_rows.sql`），cap **1000 rows/result**（超過則只存前 1000 + 設 `truncated:true` flag，UI 提示「Showing 1000 of N violations」）。新 endpoint `GET /results/{result_id}/violations.csv` 用 FastAPI `StreamingResponse` + `csv.DictWriter` 從 JSONB 串流回 CSV。**stale `unexpected_rows` 與整體 run history 的清除策略列為 Future Enhancement**：MVP 範圍不做 GC job，但於 `docs/architecture.md` 與本 plan 3.7 節明列為已知債務。
- **Why It Matters**: 決定資料生命週期——影響 `dq.run_results` schema、storage 用量、re-download 是否要重 run、是否需要 cap row 數量；同時是「快照語意」的承諾基礎（同一 run_id 重複下載結果一致）。
- **Options Considered**:
  - **執行時不持久化、CSV download 時重 run**：省 storage，但破壞「同一 run_id 應為不可變快照」的語意——user 隔天下載可能與 UI 看到的不一致（資料變動時），對非技術 user 是反直覺的 bug。
  - **執行時全量持久化、無 cap**：對大表會撐爆 JSONB（PostgreSQL TOAST 機制下 > 8KB 壓縮儲存，效能下降）。
  - **執行時全量持久化 + cap 1000 + 無 GC**：取得快照語意，cap 防止單筆 row 撐爆 JSONB；GC 列為 Future Enhancement 延後處理。
  - **同上 + PII filter**（national_id / email / phone 自動 redact）：多 2-3 小時、Product Thinking 加分點，但 demo 用 fake data 已不需要。
- **How Chosen**: User 選定「持久化 + cap」方案並明確要求「文件必須註明 stale 資料清除策略為 Future Enhancement」。
- **Problem Essence**: 「快照」是 run 這個 resource 的核心語意——run_id 不該指向動態結果，否則 user 無法信任歷史記錄（demo 中今天看到的 50 筆違規，明天若資料被修就只剩 30 筆，user 會懷疑是不是 bug）。把違規 row 在 run 完成時凍結進 JSONB 是「資料庫快照」最自然的實作。Cap 1000 是「避免理論上的撐爆 + 對 demo 規模實質無限」的甜蜜點。GC 不在 MVP 範圍是有意識的延後（與 D#24 LLM cache 共用「容忍累積、文件標記」的策略）——MVP 用戶不會跑數千個 run，production 必須處理但那是 future scope。
- **Tradeoff**: 放棄「不長存違規 row」的隱私乾淨感（含 PII 的 row 會永久存在 DB，與 D#30 共用 demo-data-is-fake 的 mitigation）；**`dq.run_results.unexpected_rows` 無 GC job，MVP 範圍接受長期累積；於 `docs/architecture.md` Future Enhancements 明列「定期清除 stale unexpected_rows / 整理 run history 的 cron job 或手動 SOP」為已知債務**；放棄「PII filter 加分點」（多 2-3 小時不對等）；cap 1000 對 demo 表（< 100 rows）實質無感，對真實大表會有「Showing 1000 of N」的 UX 切割，但是必要的保險。

---

### D#38: 違規 Row 視覺形態 = 表格 + 違規欄位 highlight + 橫向 scroll

- **Decision**: `ResultRow` 展開區的違規 row 用「表格 (Table)」呈現：每 row 一列、欄位橫向排（與 `SchemaView` 風格一致）；違規欄位（kwargs 中的 `column` 名稱）以紅色背景 highlight；欄位數多時用 `overflow-x-auto` 橫向 scroll；表格右上角放「Download all violations (CSV)」按鈕。
- **Why It Matters**: 直接決定非技術 user 的閱讀體驗——CLAUDE.md 強調 target user 是 domain expert，UI 要「hide GE jargon, surface plain-language descriptions」。
- **Options Considered**:
  - **卡片 (Card) 形態**：單筆細看舒服，但跨筆找 pattern 費勁（要垂直跳讀同一欄位）。
  - **JSON pretty-print**：實作最快但偏離「hide jargon」原則，非技術 user 一定 bounce。
  - **表格 + 預設只顯示違規欄位、toggle 展開全部**：UX 最聰明但與 D#33「整列」的明示承諾微衝突——預設藏起其他欄位後 user 要多按一次才看到完整 row；留為 Future Enhancement。
  - **表格 + 違規欄位 highlight + 橫向 scroll**：對齊 Excel 直覺、與 `SchemaView` 視覺一致、跨筆比較快。
- **How Chosen**: User 選定。判準是「domain expert 的母語是 Excel」與「跨筆比較找 systemic pattern 的能力」。
- **Problem Essence**: D#33 已決定「顯示什麼」、D#34 已決定「顯示多少」，D#38 處理「怎麼排版」——三者拆開後每個都有乾淨的 problem essence，併在一起 Tradeoff 段會混。表格 vs. 卡片不只是視覺偏好，是「user 完成什麼任務」的對應：表格服務「掃 pattern」、卡片服務「細看單筆」——兩個任務都重要但表格更貼近 domain expert 在 Excel 中的本能流程。違規欄位 highlight 是「在表格中還能精準告訴 user 規則指向哪欄」的視覺指引，補上表格在「特定欄位」訊號上的弱點。
- **Tradeoff**: 放棄「單 row 細看時的閱讀舒適度」（卡片在縱向滑動友好）；放棄「最快實作」（JSON pretty-print）；放棄「智能聚焦」加分點（預設藏欄位 toggle 展開）——留為 Future Enhancement；表格欄位多時橫向 scroll 有學習成本，但 `SchemaView` 已是同套 pattern，user 已熟悉。

---

## Section 2: Decision Points (Pending)

**（空——所有決策已解決。）**

若實作過程中浮現新的架構選擇，停下、在此新增 Decision Point、等待回答後再繼續。

---

## Section 3: Specification

### 3.1 問題重述

Day 3 把 Day 2 的「跑得起來」推到「值得 demo 與評分」的水準。重點：

1. **修補可擴展性短板**：D#17 sync runs 與 D#21 one-shot NL 是 Day 2 的兩條「先求有」捷徑——Day 3 把它們升級成可講可信的架構故事（async + 真 chat）。
2. **兌現 Day 3 polish**：LLM caching、parallel execution、error handling 擴充、UI polish。
3. **拿下高槓桿 bonus**：LLM Explain Failure 對 AI-First 加分最高，且能與 D#24 cache 相互佐證設計成熟度。
4. **完成 4 份文件**：是評分必交項，也是 AI tool usage 的書面證據。
5. **違規 row 整列展示 + CSV 下載**（D#33–D#38）：Day 3 後段補強的 actionability 需求——`status='fail'` 的展示從「值 sample」升級為「完整 row 表格 + 可下載 CSV」，讓非技術 user 從「看到有問題」躍升到「能直接行動」；同時為 D#30 Explain Failure 提供更豐富的 row context。

**Day 3 完成的最低 demo bar**：在 `policyholders` 表上能完整跑「Suggest → Save → 多輪 NL（產 rule、refine）→ 編輯 rule（看 diff）→ Run（觀察輪詢 + parallel）→ 紅黃綠結果 → 展開 fail row → 點 💡 看 LLM 解釋」完整流程，過程中無 unhandled exception，5 分鐘內可在新環境重現（README）。

**模糊處與假設**：
- Demo 需要 dirty row（Day 2 README 已加 INSERT 指令）。
- 不做行動裝置布局；demo 一律在桌機 ≥ 1024px 寬度進行。
- Parallel execution 在 MVP 規模下時間差不明顯，所以 demo 重點在「Run 結果顯示是 async / parallel」的故事性，不是 stopwatch 比較。

---

### 3.2 影響範圍（檔案路徑）

#### Backend (`backend/`)

```
backend/
├── pyproject.toml                          # 無新依賴
├── app/
│   ├── main.py                             # + register explain endpoint, 新 error handlers
│   ├── schemas/
│   │   ├── runs.py                         # 修改: RunSummary.status 加 'running'; CreateRunRequest 加 rule_ids?; RunResult 加 unexpected_rows + truncated (D#33/D#37)
│   │   ├── rules.py                        # 修改: NlRuleRequest.messages: list[ChatMessage]
│   │   └── explain.py                      # 新: ExplainRequest, ExplainResponse, ChatMessage
│   ├── services/
│   │   ├── ai_generator.py                 # 修改: 包 LlmCache; multi-turn 處理; + explain_failure()
│   │   ├── ge_engine.py                    # 修改: ThreadPoolExecutor 平行驗證; _RESULT_FORMAT 升 COMPLETE + unexpected_index_column_names; 新增 _fetch_full_rows (D#36)
│   │   ├── pk_inspector.py                 # 新 (D#36): 查 pg_index/pg_attribute 偵測 table PK; 支援單欄/複合; 無 PK 回 None
│   │   ├── runs_store.py                   # 修改: create_run 寫 status='running'; finalize_run atomic; write_result 寫 unexpected_rows + truncated (D#37)
│   │   ├── llm_cache.py                    # 新: hash key 計算、get/set/expire
│   │   └── rules_store.py                  # 不動
│   ├── api/
│   │   ├── results.py                      # 修改: POST /runs 改非同步; + POST /results/{id}/explain; + GET /results/{id}/violations.csv (StreamingResponse + csv.DictWriter, D#37)
│   │   ├── rules.py                        # 修改: from-nl 接 messages
│   │   └── errors.py                       # 新: raise_error helper + 集中 code map
│   └── prompts/
│       ├── rule_from_nl.md                 # 修改: prompt 改寫支援 history; bump prompt_version
│       ├── rule_from_schema.md             # 不動 (僅 prompt_version 維持原 hash)
│       └── explain_failure.md              # 新: D#30 explain prompt
├── db/
│   ├── 003_llm_cache.sql                   # 新: CREATE TABLE dq.llm_cache + index
│   └── 004_run_results_rows.sql            # 新 (D#37): ALTER TABLE dq.run_results ADD COLUMN unexpected_rows JSONB, truncated BOOLEAN
└── tests/
    ├── test_runs_async.py                  # 新: BackgroundTasks 行為 + polling 邏輯
    ├── test_llm_cache.py                   # 新: hit / miss / expire
    ├── test_explain.py                     # 新: explain endpoint + cache 互動
    ├── test_rules_multi_turn.py            # 新: messages history serialization
    └── test_violating_rows.py              # 新 (D#36/D#37): PK 偵測 (單/複合/無 PK) + GE index 取法 + 反查 SQL + CSV 串流 + RESULT_NOT_FAILED 邊界
```

#### Frontend (`frontend/`)

```
frontend/
├── components/
│   ├── NlRuleInput.tsx                     # 修改: 重構為 chat thread wrapper
│   ├── NlChatThread.tsx                    # 新: messages bubble + scroll-to-bottom + Start over
│   ├── RuleCard.tsx                        # 修改: + [Edit] 按鈕
│   ├── RuleEditModal.tsx                   # 新: 編輯 + DiffLines
│   ├── DiffLines.tsx                       # 新: 簡易字串 diff (60 行內自製)
│   ├── ResultsView.tsx                     # 修改: polling logic; + RuleFilter (折疊)
│   ├── RuleFilter.tsx                      # 新: rule checkbox + Run selected
│   ├── ResultRow.tsx                       # 修改: + 💡 Why? 按鈕; explanation panel; 展開區改用 ViolatingRowsTable (D#38)
│   ├── ResultExplainPanel.tsx              # 新: 顯示 explanation + causes + action
│   ├── ViolatingRowsTable.tsx              # 新 (D#38): 表格 + 違規欄位 highlight + 橫向 scroll + Download CSV 按鈕; 無 PK 表 fallback 訊息
│   ├── RunButton.tsx                       # 修改: loading 狀態接 polling status
│   ├── ErrorState.tsx                      # 修改: 接 errorMessages map; possible_causes 渲染
│   └── ... (其他元件不動)
├── lib/
│   ├── api.ts                              # 修改: PUT body 支援; 處理 202 Accepted
│   ├── queries.ts                          # 修改: useRunStatus(refetchInterval); + useRuleById
│   ├── mutations.ts                        # 修改: useTriggerRun 只回 run_id; + useUpdateRule, useExplainFailure
│   └── errorMessages.ts                    # 新: code → {title, possible_causes, retry_label}
└── types/
    └── api.ts                              # 擴: ChatMessage, ExplainResponse, RunStatus='running'; RunResult.unexpected_rows + truncated (D#33/D#37)
```

#### Docs (`docs/`)

```
docs/
├── day1-plan.md                            # 既有
├── day2-plan.md                            # 既有
├── day3-plan.md                            # 本文件
├── architecture.md                         # 新 (D#32)
├── ai-integration.md                       # 新 (D#32)
└── ai-tools-usage.md                       # 既有, 每日續寫
```

頂層 `README.md` 改寫為 5-minute demo walkthrough（D#32）。

---

### 3.3 設計細節

#### 3.3.1 Backend Schemas

**`app/schemas/runs.py`**（修改）

```python
RunStatus = Literal["running", "success", "failed"]   # 新增 'running'
ResultStatus = Literal["pass", "fail", "error"]        # D#18 維持

class CreateRunRequest(BaseModel):
    table_name: str
    rule_ids: list[int] | None = None       # D#28 optional

class RunSummary(BaseModel):
    id: int
    table_name: str
    status: RunStatus                        # 'running' / 'success' / 'failed'
    started_at: datetime
    completed_at: datetime | None
    error_message: str | None
    pass_count: int
    fail_count: int
    error_count: int

class RunDetail(RunSummary):
    results: list[RunResult]                 # status='running' 時為空陣列
```

**`app/schemas/explain.py`**（新）

```python
class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str                              # assistant 訊息儲存上一次 tool_use 的 JSON 字串

class ExplainResponse(BaseModel):
    explanation: str                          # 1-2 句 plain English
    possible_causes: list[str]                # 2-4 條子彈點
    suggested_action: str                     # 1 句行動建議
```

**`app/schemas/rules.py`**（修改）

```python
class NlRuleRequest(BaseModel):
    table_name: str
    messages: list[ChatMessage] = Field(min_length=1, max_length=10)  # 5 user + 5 assistant
```

#### 3.3.2 Backend Services

**`app/services/llm_cache.py`**（新）

```python
def make_cache_key(prompt_name: str, prompt_version: str, **payload) -> str:
    """sha256(prompt_name || version || sorted JSON of payload)"""
    canonical = json.dumps({"_p": prompt_name, "_v": prompt_version, **payload},
                           sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()

def get_cached(session, cache_key: str) -> dict | None:
    """SELECT response FROM dq.llm_cache WHERE cache_key=:k AND expires_at > NOW()
       UPDATE hit_count += 1"""
    ...

def set_cached(session, cache_key: str, prompt_name: str, response: dict,
               ttl_hours: int = 24) -> None:
    """INSERT ON CONFLICT (cache_key) DO UPDATE"""
    ...
```

**`app/services/ai_generator.py`**（修改）

每支 prompt 在檔頂宣告 `PROMPT_VERSION_*`：

```python
PROMPT_VERSION_SCHEMA = "v1"      # bump 時 cache 自動失效
PROMPT_VERSION_NL = "v2"          # Day 3 改寫 (multi-turn)
PROMPT_VERSION_EXPLAIN = "v1"     # 新增

class AiGenerator:
    def suggest_rules(self, session, table_name, columns, sample_rows):
        cache_key = make_cache_key(
            "rule_from_schema", PROMPT_VERSION_SCHEMA,
            table_name=table_name,
            columns=[c.model_dump() for c in columns],
            sample=sample_rows[:20],
        )
        if (cached := get_cached(session, cache_key)) is not None:
            return [GeRule.model_validate(r) for r in cached["rules"]]
        # ... existing logic ...
        set_cached(session, cache_key, "rule_from_schema", {"rules": [r.model_dump() for r in result]})
        return result

    def rule_from_nl(self, session, table_name, columns, messages: list[ChatMessage]):
        # cache key 對應整段 messages (因為對話接續 = 不同 prompt 內容)
        # 但短 user message + 長 system prompt 命中率仍可觀
        ...

    def explain_failure(self, session, rule_id, expectation_type, kwargs,
                        unexpected_sample, table_name) -> ExplainResponse:
        cache_key = make_cache_key(
            "explain_failure", PROMPT_VERSION_EXPLAIN,
            rule_id=rule_id,                          # rule 改了 -> 不同 key
            unexpected_sample=unexpected_sample,      # sample 變了 -> 不同 key
        )
        # ...
```

**`app/services/ge_engine.py`**（修改）

```python
def run_rules(self, table_name: str, rules: list[RuleRecord],
              progress_callback: Callable[[RunResult], None] | None = None
              ) -> list[RunResult]:
    asset = self.datasource.add_table_asset(name=f"asset_{table_name}", table_name=table_name)
    batch_def = asset.add_batch_definition_whole_table(name=f"batch_{table_name}")
    batch = batch_def.get_batch()

    def _run_one(rule: RuleRecord) -> RunResult:
        try:
            expectation = self._build_expectation(rule.expectation_type, rule.kwargs)
            ge_result = batch.validate(expectation)
            return self._normalize_pass_fail(rule, ge_result)
        except Exception as e:
            return self._normalize_error(rule, e)

    results: list[RunResult] = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_run_one, r): r for r in rules}
        for f in as_completed(futures):
            r = f.result()
            results.append(r)
            if progress_callback:
                progress_callback(r)   # 即時寫 DB (參見 runs_store)
    return results
```

**`app/services/runs_store.py`**（修改）

```python
def create_run(session, table_name: str) -> int:
    """INSERT dq.runs (status='running') RETURNING id"""

def finalize_run(session, run_id: int, status: Literal['success','failed'],
                 error_message: str | None) -> None:
    """UPDATE dq.runs SET status=:s, completed_at=NOW(), error_message=:e
       WHERE id=:id AND status='running'                            -- atomic guard
       並聚合 pass_count / fail_count / error_count"""
```

**Async run task** (`app/api/results.py` 內定義)：

```python
def _execute_run(run_id: int, table_name: str, rule_ids: list[int] | None):
    """BackgroundTask body. 自己取 Session, 跑完 finalize, 異常時 status='failed'"""
    with get_session() as session:
        try:
            rules = rules_store.list_rules(session, table_name, rule_ids=rule_ids)
            engine = GeEngine()
            engine.run_rules(
                table_name, rules,
                progress_callback=lambda r: runs_store.write_result(session, run_id, r),
            )
            runs_store.finalize_run(session, run_id, "success", None)
        except Exception as e:
            runs_store.finalize_run(session, run_id, "failed", str(e)[:200])
```

#### 3.3.3 Backend API 變動

**`POST /runs`**（D#23 改 async）

```
Request:  CreateRunRequest { table_name, rule_ids? }
Response: 202 Accepted
          RunSummary { id, status: 'running', table_name, started_at, ... pass/fail/error_count=0 }
```

前端拿到 `run_id` 後立刻發 `useQuery(['runs', id], { refetchInterval: ... })`。

**`GET /runs/{id}`**（不變，但回傳可能 status='running' 且 results=[]）

**`POST /results/{result_id}/explain`**（D#30 新）

```
Request:  body: {}  (result_id 在 path)
Response: ExplainResponse { explanation, possible_causes, suggested_action }
Errors:   404 RESULT_NOT_FOUND, 400 RESULT_NOT_FAILED (只給 fail row 用)
```

**`POST /rules/from-nl`**（D#25 messages）

```
Request:  { table_name, messages: ChatMessage[] }
Response: NlRuleResponse (同 Day 2)
```

**`PUT /rules/{id}`**（既有，前端 D#26 開始使用）

#### 3.3.4 Frontend — 關鍵元件

**`NlChatThread`**（D#25）

```tsx
<div className="flex flex-col">
  {messages.map((m, i) => (
    <ChatBubble key={i} role={m.role}>
      {m.role === "assistant" && m.toolUse ? <RuleCardPreview rule={m.toolUse}/> : m.content}
    </ChatBubble>
  ))}
  <Input value={draft} onChange={...} onSubmit={() => mutate({ messages: [...messages, {role:'user', content: draft}] })}/>
  {messages.length >= 10 && <Button onClick={reset}>Start over</Button>}
</div>
```

**Run polling 邏輯**（`lib/queries.ts`）

```typescript
export const useRunDetail = (runId: number | null) =>
  useQuery({
    queryKey: ["runs", runId],
    queryFn: () => apiFetch<RunDetail>(`/runs/${runId}`),
    enabled: runId != null,
    refetchInterval: (q) => {
      const status = q.state.data?.status;
      return status === "running" ? 1000 : false;  // 1s 輪詢直到結束
    },
  });
```

**`RuleEditModal`**（D#26）

```tsx
<Modal>
  <div className="grid grid-cols-2 gap-4">
    <pre className="bg-gray-50">{JSON.stringify(original, null, 2)}</pre>
    <div>
      <Select value={edited.expectation_type} onChange={...}/>
      <Textarea value={kwargsJson} onChange={parseAndSetKwargs}/>
      <Textarea value={edited.description} onChange={...}/>
      {jsonError && <p className="text-red-600">{jsonError}</p>}
    </div>
  </div>
  <DiffLines original={original} edited={edited}/>
  <Button onClick={() => mutate(edited)} disabled={!!jsonError}>Save</Button>
</Modal>
```

**`ResultRow` + `ResultExplainPanel`**（D#30）

```tsx
<div>
  ... existing pass/fail/error row UI ...
  {expanded && status === "fail" && (
    <div>
      {sampleValues.map(...)}
      {!explanation && (
        <Button onClick={() => fetchExplanation(result.id)}>
          💡 Why did this fail?
        </Button>
      )}
      {explanation && <ResultExplainPanel data={explanation}/>}
    </div>
  )}
</div>
```

#### 3.3.5 Prompt — 新 / 修改

**`rule_from_nl.md`**（修改）

- 在頂端 prompt body 注入 message history（Anthropic Messages API 原生格式）。
- 加入 "Please keep responses concise; do not repeat earlier explanations" 指示。
- bump `PROMPT_VERSION_NL = "v2"`。

**`explain_failure.md`**（新）

- 變數：`{{table_name}}`、`{{expectation_type}}`、`{{kwargs_json}}`、`{{unexpected_sample_json}}`、`{{observed_value_json}}`。
- 強制透過 Tool Use 回傳 `{explanation, possible_causes: [...], suggested_action}`。
- 對 sample 中可能的 PII 不做特殊處理（在 prompt 結尾加 NOTE：「Demo data is fake; production deployments should mask PII before sending」）。

#### 3.3.6 DB Migration

**`db/003_llm_cache.sql`**（新）

```sql
CREATE TABLE IF NOT EXISTS dq.llm_cache (
  cache_key VARCHAR(64) PRIMARY KEY,
  prompt_name VARCHAR(50) NOT NULL,
  response JSONB NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  expires_at TIMESTAMP NOT NULL,
  hit_count INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS llm_cache_expires_idx ON dq.llm_cache(expires_at);
```

`dq.runs` 不需要新 migration（`status` 欄位已是 VARCHAR(20)，能放 `'running'`）。

**`db/004_run_results_rows.sql`**（新，D#37）

```sql
ALTER TABLE dq.run_results
  ADD COLUMN IF NOT EXISTS unexpected_rows JSONB,
  ADD COLUMN IF NOT EXISTS truncated BOOLEAN NOT NULL DEFAULT FALSE;

-- 不對 unexpected_rows 做 query，只整欄取出，故不加 GIN index
```

#### 3.3.7 違規 Row 整列展示 + CSV 下載（D#33–D#38）

跨層設計，從 PK 偵測 → GE index 取法 → 反查整列 → JSONB 持久化 → CSV 串流 → 表格 UI，端對端流程：

**`app/schemas/runs.py`** 進一步擴張 `RunResult`：

```python
class RunResult(BaseModel):
    id: int
    rule_id: int | None
    expectation_type: str
    status: ResultStatus
    success: bool
    unexpected_count: int | None
    unexpected_sample: list[Any] | None       # 保留（向後相容；新前端不再使用）
    unexpected_rows: list[dict] | None        # D#33: 完整 row dict 陣列, status='fail' 時填入
    truncated: bool = False                   # D#37: 若違規 > 1000 則 True, UI 顯示 "Showing 1000 of N"
    observed_value: Any | None
    error_message: str | None
```

**`app/services/pk_inspector.py`**（新，D#36）：

```python
def get_pk_columns(session, table_name: str, schema: str = "public") -> list[str] | None:
    """Return PK column names for a table. None if no PK exists.
    Supports single-column and composite PKs.
    """
    rows = session.execute(text("""
        SELECT a.attname AS column_name
        FROM pg_index i
        JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
        WHERE i.indrelid = (:schema || '.' || :table)::regclass AND i.indisprimary
        ORDER BY array_position(i.indkey, a.attnum)
    """), {"schema": schema, "table": table_name}).all()
    return [r.column_name for r in rows] or None
```

**`app/services/ge_engine.py`** 變動：

```python
_RESULT_FORMAT = {
    "result_format": "COMPLETE",                  # 升級自 SUMMARY
    "partial_unexpected_count": 1000,             # cap (D#37)
}

def _run_one(rule: RuleRecord) -> RunResult:
    pk_cols = get_pk_columns(session, table_name)
    fmt = {**_RESULT_FORMAT}
    if pk_cols:
        fmt["unexpected_index_column_names"] = pk_cols
    ge_result = batch.validate(expectation, result_format=fmt)
    result = self._normalize_pass_fail(rule, ge_result)
    if result.status == "fail" and pk_cols:
        index_list = ge_result.result.get("partial_unexpected_index_list", [])
        result.unexpected_rows = self._fetch_full_rows(table_name, pk_cols, index_list)
        result.truncated = len(index_list) >= 1000
    return result

def _fetch_full_rows(self, table_name, pk_cols, index_list) -> list[dict]:
    """index_list = [{"id":42}, {"id":107}, ...]; build WHERE pk IN (...) and return list[dict]."""
    if not index_list:
        return []
    # 單欄: WHERE id IN (42, 107, ...)
    # 複合: WHERE (a, b) IN ((1,2), (3,4), ...)
    ...
```

**`app/api/results.py`** CSV endpoint：

```python
@router.get("/results/{result_id}/violations.csv")
def download_violations_csv(result_id: int, session: Session = Depends(get_db)):
    result = get_result(session, result_id)
    if result is None:
        raise_error("RESULT_NOT_FOUND")
    if result.status != "fail":
        raise_error("RESULT_NOT_FAILED")           # 400, D#35

    def generate():
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(result.unexpected_rows[0].keys()))
        writer.writeheader(); yield buf.getvalue(); buf.seek(0); buf.truncate()
        for row in result.unexpected_rows:
            writer.writerow(row); yield buf.getvalue(); buf.seek(0); buf.truncate()

    filename = f"violations_run{result.run_id}_result{result_id}.csv"
    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

**`frontend/components/ViolatingRowsTable.tsx`**（新，D#38）：

```tsx
interface Props {
  rows: Record<string, unknown>[];
  violatingColumns: string[];     // 從 rule.kwargs.column / column_A,B 推導
  truncated: boolean;
  totalCount: number;
  downloadUrl: string;            // /results/{id}/violations.csv
}

export function ViolatingRowsTable({ rows, violatingColumns, truncated, totalCount, downloadUrl }: Props) {
  if (!rows.length) return <p className="text-xs text-gray-600">This table has no primary key — row data unavailable.</p>;
  const columns = Object.keys(rows[0]);
  const preview = rows.slice(0, 10);  // D#34: UI 預設 10 筆
  return (
    <div>
      <div className="flex justify-between items-center">
        <span className="text-xs">
          Showing {preview.length} of {totalCount} violating rows{truncated ? " (capped at 1000)" : ""}.
        </span>
        <a href={downloadUrl} download className="text-xs text-red-700 underline">
          ⬇ Download all violations (CSV)
        </a>
      </div>
      <div className="overflow-x-auto mt-2">
        <table className="text-xs">
          <thead><tr>{columns.map(c => <th key={c}>{c}</th>)}</tr></thead>
          <tbody>{preview.map((row, i) => (
            <tr key={i}>{columns.map(c => (
              <td key={c} className={violatingColumns.includes(c) ? "bg-red-100 font-mono" : "font-mono"}>
                {String(row[c] ?? "")}
              </td>
            ))}</tr>
          ))}</tbody>
        </table>
      </div>
    </div>
  );
}
```

**邊界處理（D#36）**：
- **單欄 PK**：`WHERE id IN (42, 107, ...)`。示範表都走此 path。
- **複合 PK**：`WHERE (col_a, col_b) IN ((1,2), (3,4), ...)`；GE 1.x `unexpected_index_column_names` 支援多欄陣列。
- **無 PK 表**：`pk_inspector` 回 `None`，跳過撈整列；`unexpected_rows = null`；UI 在 `ViolatingRowsTable` 顯示「This table has no primary key — row data unavailable」訊息。列為 D#36 已知限制與 Future Enhancement。

**violatingColumns 推導**：前端從 `rule.kwargs.column`（單欄規則）或 `kwargs.column_A` + `kwargs.column_B`（pair 規則）等慣用 key 取出；找不到對應 key 時退化為「不 highlight」、表格仍可用。

---

### 3.4 風險與可逆性

| 風險 | 嚴重度 | 可逆性 | 緩解 |
|------|--------|--------|------|
| BackgroundTask 在 reload 時被取消 (dev 時 uvicorn `--reload`) | 中 | 容易（重新觸發即可） | README 明寫「dev 時用 `--reload` 可能會中斷 in-flight runs」 |
| `finalize_run` race condition（同 run 被 finalize 兩次） | 中 | 容易 | UPDATE 帶 `WHERE status='running'` guard |
| `ThreadPoolExecutor` worker 共用 Supabase Session Pooler 連線被回收 | 中 | 容易 | `GeEngine` 內偵測 `OperationalError` retry 1 次；pool_pre_ping 已開 |
| Prompt 改了但忘記 bump `PROMPT_VERSION_*` 導致命中過時 cache | 中 | 容易 | `architecture.md` 內 "Prompt change SOP"；以及在 `ai_generator.py` 頂部 comment 提醒 |
| Multi-turn 對話 token 累積爆炸 | 低 | 容易 | 5 輪 hard cap + Start over button |
| `RuleEditModal` 的 JSON parser 對 trailing comma / single quote 不容錯 | 低 | 容易 | inline 紅字 + Save disabled，user 自然修正 |
| LLM Explain 對含 PII sample 的回應在 cache 留存 | 中 | 容易 | 文件明示 demo data 為 fake；production 需先 mask（架構不變） |
| `dq.llm_cache` 無限累積（沒 GC job） | 低 | 容易 | `expires_at` index 已開；Day 3 範圍內手動 `DELETE WHERE expires_at < NOW()`；Future Enhancement 加 cron |
| Async run 改造後前端 polling 不收場（status 卡 'running'） | 高 | 容易 | BackgroundTask exception 一定 fall-through 到 `finalize_run(..., 'failed', ...)`；前端輪詢 60s 後 UI 顯示提示但不停 |
| `dq.run_results.unexpected_rows` JSONB 長期累積無 GC（D#37） | 低 | 容易 | cap 1000 rows / result + 於 `docs/architecture.md` Future Enhancements 明列為已知債務；MVP 範圍可手動 `DELETE FROM dq.run_results WHERE created_at < NOW() - INTERVAL '30 days'` 清理 |
| 含 PII 的違規 row 寫入 JSONB（D#33） | 中 | 容易 | demo data 為 fake；production 需先 mask（與 D#30 共用同一 mitigation） |
| 無 PK 表 fallback（D#36） | 低 | 容易 | UI 顯示「This table has no primary key — row data unavailable」訊息；D#36 列為已知限制；示範表都有 PK 不受影響 |
| 複合 PK 在 GE 1.x SQL backend 的 `unexpected_index_column_names` 支援度未驗證（D#36） | 中 | 容易 | Phase 7 第一個 task 是 spike 驗證（用測試表複合 PK）；不通則該 table 走無 PK fallback |

**最難回滾的決策**：
- **D#23（async run）**：回滾要同時改 API contract、frontend hooks、`runs_store` state machine——估 3–4 小時。
- **D#25（multi-turn NL）**：回滾相對容易（messages 退成單 user message 即 Day 2 行為），但 prompt template 已 bump，需手動 revert `prompt_version`。

---

### 3.5 Rollout Phases（每 Phase 含 Verification 與優先級）

> 每個 Phase 的 Verification 必須通過才能進下一個。**時間不夠就從 Phase 順序末端往前砍**：Phase 7 (違規 Row + CSV) → Phase 6 (Bonus) → Phase 4 (Multi-turn NL) → Phase 5 (PUT UI + Error Polish)。Phase 1 / 2 / 8 是 Must-have。

#### Phase 1 — Backend Foundations 與 Migration（M，估 2–3 小時）

**Outcome**: DB 新增 `dq.llm_cache` 表；error helper / code map 集中；error envelope 升級。

Tasks:
1. `db/003_llm_cache.sql` 在 Supabase SQL Editor 跑過。
2. `app/api/errors.py` 集中 `raise_error()` 與 `code_map`（new codes 見 D#31）。
3. `app/schemas/runs.py` 加 `RunStatus = Literal["running", ...]`；`CreateRunRequest.rule_ids` optional。
4. `app/schemas/explain.py` 新檔（`ChatMessage` + `ExplainResponse`）。
5. `lib/errorMessages.ts` 集中前端 mapping。

**Verification**:
- `psql -c "SELECT column_name FROM information_schema.columns WHERE table_schema='dq' AND table_name='llm_cache';"` 列出全部欄位。
- `curl http://localhost:8000/tables/nonexistent` 回新格式（無變化但 code map 已遷移到 errors.py）。
- `uv run pytest` 全綠（既有測試不應該掛）。

#### Phase 2 — LLM Cache + Parallel Execution（S，估 3 小時）

**Outcome**: `AiGenerator` 三條 prompt path 都過 cache；`GeEngine.run_rules` 平行；可在 SQL 查到 hit_count 累計。

Tasks:
1. `app/services/llm_cache.py` 完整實作。
2. `ai_generator.py` 在 `suggest_rules` / `rule_from_nl` 包 cache（explain_failure 在 Phase 6 加）。
3. `ge_engine.py` 改用 `ThreadPoolExecutor`，加 retry-on-OperationalError。
4. `tests/test_llm_cache.py`：hit / miss / expire 三條 path。

**Verification**:
- 連按兩次 Suggest 同表：第一次 ~3s，第二次 < 200ms。`SELECT cache_key, hit_count FROM dq.llm_cache` 看到 `hit_count=1`。
- `time curl -X POST .../runs ...` 比平行前快約 2-3 倍（demo 規模可能差距小，但 logs 可看到 4 個 worker 同時 active）。
- bump `PROMPT_VERSION_SCHEMA` → 同樣輸入產生新 cache row。

#### Phase 3 — Async Run + Per-rule Run + Polling UI（S，估 4–5 小時）

**Outcome**: D#23 完整生效；前端 `useRunDetail` 輪詢；D#28 per-rule filter。

Tasks:
1. `app/api/results.py`：`POST /runs` 改為立刻回 `202 + RunSummary(status='running')`；BackgroundTask 觸發 `_execute_run`。
2. `runs_store.py`：`create_run` 寫 `status='running'`；`finalize_run` 帶 guard。
3. `rules_store.list_rules` 接 `rule_ids` filter。
4. 前端 `useTriggerRun` 改回 `run_id`；`useRunDetail` 用 `refetchInterval`；`ResultsView` 在 status='running' 顯示「Running... (N rules)」進度條；逐筆累積已完成 results。
5. `RuleFilter` 元件 + ResultsView 折疊整合。
6. `tests/test_runs_async.py`：BackgroundTask + polling 行為（用 TestClient + asyncio）。

**Verification**:
- `curl -X POST .../runs -d '{"table_name":"policyholders"}'` 立刻回 `status:'running'`。
- 2 秒內再 `curl .../runs/{id}` 看到 `status:'success'` + 完整 results。
- Frontend：按 Run 看到 1-2 秒的「Running... 3/8 rules」UI；results 結束後自動切到結果列表。
- 帶 `rule_ids:[1,3]` POST 確認只跑兩條。
- 帶錯誤 rule_id（不屬於該 table）回 `400 INVALID_RULE_IDS`。

#### Phase 4 — Multi-turn NL Chat（N，估 4 小時）

**Outcome**: D#25 完整生效；前端 chat thread 可進行 5 輪對話。

Tasks:
1. `prompts/rule_from_nl.md` 改寫支援 messages history；bump `PROMPT_VERSION_NL='v2'`。
2. `ai_generator.rule_from_nl` 接 `messages: list[ChatMessage]`；組 Anthropic messages 陣列。
3. `app/schemas/rules.py` 與 `app/api/rules.py` 改 request shape。
4. 前端 `NlChatThread` 新元件；`NlRuleInput` 改為其薄包裝。
5. `useNlRule` mutation 改為「append message → 重發整個 thread」模式。
6. 5 輪 cap + Start over button。
7. `tests/test_rules_multi_turn.py`：history serialization + cap 邊界。

**Verification**:
- Type "premium cannot be negative" → 回 rule draft；type "and also no zero" → 看到 refined rule。
- 連續送 5 輪後輸入框被 disable 顯示「Conversation too long」+ Start over 按鈕可用。
- Refresh 頁面後對話清空（feature）。

#### Phase 5 — PUT Edit Modal + Error Polish（N，估 3 小時）

**Outcome**: D#26 / D#31 生效。

Tasks:
1. `RuleEditModal` + `DiffLines` 元件；`RuleCard` 加 Edit 按鈕；`useUpdateRule` mutation。
2. `ErrorState` 改用 `errorMessages.ts` map；新 codes 全部填滿 possible_causes。
3. 既有 endpoint 把 raw HTTPException 改用 `raise_error(...)`。

**Verification**:
- Edit modal 開啟、改 description、Save → 列表更新且 diff view 在 modal 內可見。
- 改 kwargs 內 JSON 寫成 `{a: 1,}` → inline 紅字、Save disabled。
- 停 backend → 前端各頁顯示具體 possible_causes（不再是泛用訊息）。

#### Phase 6 — Bonus: LLM Explain Failure（S+，估 2-3 小時）

**Outcome**: D#30 生效；fail row 展開可看到 💡 Why? + LLM 解釋。

Tasks:
1. `prompts/explain_failure.md` + `PROMPT_VERSION_EXPLAIN`。
2. `ai_generator.explain_failure(...)` + tool schema。
3. `app/api/results.py`：`POST /results/{result_id}/explain`。
4. 前端 `ResultExplainPanel` + `ResultRow` button + `useExplainFailure` mutation。
5. `tests/test_explain.py`：cache hit / explain shape。

**Verification**:
- INSERT dirty row → Run → 展開 fail row → 按 💡 → 1-2 秒後看到 plain English 解釋 + 2-3 possible causes + 1 suggested action。
- 連點兩次 💡 同 row：第二次 < 200ms（cache hit）。

#### Phase 7 — 違規 Row 整列展示 + CSV 下載（S，估 6–8 小時）

**Outcome**: D#33–D#38 完整生效；`status='fail'` 的 row 展開後顯示完整 row 表格（最多 10 筆，違規欄位 highlight），可下載完整違規 row CSV；無 PK 表降級為 fallback 訊息。

Tasks（依序）：
1. **Spike 驗證**（1 小時）：在測試表（含複合 PK）跑 `batch.validate(..., result_format={"result_format":"COMPLETE", "unexpected_index_column_names":["a","b"]})`，確認 GE 1.x SQL backend 回傳 `partial_unexpected_index_list` 形狀（單欄與複合 PK 皆驗）。不通則該規則類型走無 PK fallback。
2. `db/004_run_results_rows.sql`：`ALTER TABLE dq.run_results ADD COLUMN unexpected_rows JSONB, truncated BOOLEAN`，在 Supabase SQL Editor 跑過。
3. `app/services/pk_inspector.py`：`get_pk_columns(session, table_name) -> list[str] | None`。
4. `app/services/ge_engine.py`：`_RESULT_FORMAT` 升 `COMPLETE` + `partial_unexpected_count=1000`；`_run_one` 整合 PK Inspector；新增 `_fetch_full_rows(table, pk_cols, index_list)` 用 IN clause 撈整列；handle 單欄 / 複合 / 無 PK 三條 path。
5. `app/schemas/runs.py`：`RunResult` 加 `unexpected_rows: list[dict] | None` + `truncated: bool`。
6. `app/services/runs_store.py`：`write_result` 寫入 `unexpected_rows` + `truncated` 兩欄。
7. `app/api/results.py`：新 endpoint `GET /results/{result_id}/violations.csv`，用 `StreamingResponse` + `csv.DictWriter` 串流；error 結果回 `400 RESULT_NOT_FAILED`。
8. `frontend/types/api.ts`：擴張 `RunResult` 型別。
9. `frontend/components/ViolatingRowsTable.tsx`：新元件（表格 + 違規欄位 highlight + 橫向 scroll + Download CSV 按鈕 + 無 PK fallback 訊息）。
10. `frontend/components/ResultRow.tsx`：展開區改用 `ViolatingRowsTable`，移除舊的純值列點。
11. `backend/tests/test_violating_rows.py`：PK 偵測（單/複合/無 PK 三 case）+ GE index 取法 + 反查 SQL + CSV 串流 + `RESULT_NOT_FAILED` 邊界。

**Verification**:
- `psql -c "SELECT column_name FROM information_schema.columns WHERE table_schema='dq' AND table_name='run_results' AND column_name IN ('unexpected_rows','truncated');"` 列出兩個欄位。
- INSERT 多筆違規 row 到 `policyholders`（例如 `premium_monthly = -100, -50, 0`）→ Run → `SELECT unexpected_rows FROM dq.run_results WHERE id=<latest_fail>` 看到完整 row JSON 陣列。
- Frontend：展開 fail row 看到表格、最多 10 筆完整 row、`premium_monthly` 欄位紅底 highlight、欄位多時可橫向 scroll。
- 點「Download all violations (CSV)」→ 下載的 CSV 在 Excel 可開、欄位完整、row 數 = `unexpected_count`（cap 1000）。
- 對 `status='error'` 的結果按下載連結（若 UI 漏擋）→ 後端回 `400 RESULT_NOT_FAILED`。
- 在無 PK 測試表跑規則 → UI 顯示「This table has no primary key — row data unavailable」訊息。

#### Phase 8 — Documentation（M，估 4-5 小時）

**Outcome**: 4 份 docs 完成；fresh clone 可在 5 分鐘內跑完 demo。

Tasks (順序):
1. `README.md` 5-minute demo walkthrough（含 INSERT dirty row + 完整 click-through path）。
2. `docs/ai-tools-usage.md` 續寫 Day 2 + Day 3 entries（從 git log + 對話歷史摘要）。
3. `docs/architecture.md` 系統總覽 + Future Enhancements 章節（D#19 / D#22 / Celery / PII / multi-user）。
4. `docs/ai-integration.md` Prompt 設計 + Tool Use schemas + cache key 策略 + multi-turn 處理。
5. 把 `CLAUDE.md` Task Breakdown Day 3 checkbox 全部勾掉。

**Verification**:
- 新環境 git clone → 跟 README walk through → 5 分鐘內完成「Suggest → Save → NL → Run → 看紅黃綠 → 💡 解釋」全流程。
- `docs/ai-tools-usage.md` 含 Day 3 至少 5 條目（含 prompt iteration、debug、架構決策、ultrareview/architect 用法、bonus prompt 設計）。
- 4 份 docs 互不重複；architecture.md 引用 day1/2/3-plan.md 作為決策出處。

---

### 3.6 最終交付清單（Demo Checklist）

Day 3 結束時下列全部為 true：

- [x] `db/003_llm_cache.sql` 已在 Supabase 跑過。
- [x] `POST /runs` 回 202 + `status:'running'`；BackgroundTask 完成後 `dq.runs.status` flip 為 `success`/`failed`。
- [x] 前端輪詢 `GET /runs/{id}` 直到結束；UI 顯示進度。
- [x] `dq.llm_cache` 連續 Suggest 同表後 `hit_count >= 1`。
- [x] `POST /rules/from-nl` 接受 `messages: ChatMessage[]`；前端 chat thread 可 5 輪對話。
- [x] `RuleEditModal` 可改 rule，diff view 顯示變更；JSON 錯誤 inline 顯示。
- [x] `POST /runs` 帶 `rule_ids` 只跑指定 rules；錯誤 ids 回 `INVALID_RULE_IDS`。
- [x] `POST /results/{id}/explain` 對 fail row 回傳 LLM 解釋；前端 💡 按鈕顯示 panel。
- [x] `ErrorState` 對每個 new code 都有 possible_causes 列表。
- [x] `db/004_run_results_rows.sql` 已在 Supabase 跑過；`dq.run_results.unexpected_rows` JSONB 與 `truncated` 兩欄存在。
- [x] Fail row 展開後顯示表格、最多 10 筆完整 row；違規欄位以紅底 highlight；欄位多時可橫向 scroll。
- [x] 「Download all violations (CSV)」按鈕可下載完整違規 row CSV，Excel 可開、row 數 = unexpected_count（cap 1000）。
- [x] 對 status='error' 結果 hit CSV endpoint 回 `400 RESULT_NOT_FAILED`；無 PK 表 UI 顯示 fallback 訊息。
- [x] `docs/architecture.md` Future Enhancements 章節明列「定期清除 stale unexpected_rows / run history 的 cron job 或 SOP」與「無 PK 表的 row data 撈取策略」兩條。
- [x] `README.md` 5-minute demo 可在 fresh clone 重現。
- [x] `docs/architecture.md`、`docs/ai-integration.md`、`docs/ai-tools-usage.md` 三份新文件已寫。
- [x] `CLAUDE.md` Day 3 checklist 全部勾起；Bonus checkbox `LLM auto-explains failures` 勾起。

**「若時間不夠」的可砍順序**（從上往下砍）：

1. Phase 7 整體 (D#33-D#38 違規 Row + CSV) — UI 退回 Day 2 純值 sample 顯示；CSV download 按鈕降為 Future Enhancement。表格展示若已做完可保留，整體可拆 task 分段砍。
2. Phase 6 (D#30 Bonus) — 失去 AI-First bonus 加分但不影響核心 demo。
3. Phase 4 (D#25 Multi-turn NL) — 保留 Day 2 的 one-shot NL；在 `architecture.md` 註明此為 Future Enhancement。
4. Phase 5 子項 (D#26 PUT UI) — Delete + recreate 仍可用。
5. Phase 3 子項 (D#28 Per-rule run) — 保留 run-all，rule_ids 留為 API surface 但 frontend 不暴露。

**絕不砍的（M-must-have）**：Phase 1 (foundations)、Phase 2 (cache + parallel)、Phase 8 (docs)、Phase 3 主路徑 (async run + polling)。

---

### 3.7 Day 3 後狀態（即最終交付）

無 Day 4。Day 3 結束後專案進入「準備提交」階段：

1. `git status` 應為 clean。
2. `git log --oneline` 應能講出「Day 1 foundation → Day 2 core loop → Day 3 polish + scalability + bonus」三幕故事。
3. Final demo 在 fresh clone 上 < 5 分鐘可完整走過。
4. 三大評分項對應的「最強展示點」：
   - **AI-First Development**：Tool Use 結構化輸出（D#7）、multi-turn NL chat（D#25）、LLM 解釋 failure（D#30）、prompt versioning + cache（D#24）。
   - **Product Thinking**：三色 status（D#18）、honest design（D#22）、edit + diff view（D#26）、每 code 都有 possible_causes（D#31）、違規 row 整列展示 + CSV 下載（D#33/D#34/D#38——把 fail 從「看到」升級為「能行動」）。
   - **Technical Implementation**：async run + polling（D#23）、parallel execution（D#29）、DB-backed cache（D#24）、stateless multi-turn（D#25）、clean Decision Log 文件結構、PK Inspector + GE index 取法的層次化抽象（D#36）。

Future Enhancements（皆寫入 `docs/architecture.md`）：D#19 draft 持久化、D#22 UNIQUE 約束、Celery / 多 process、PII masking、multi-user auth、mobile layout、cache GC cron job、cross-rule expectations、**定期清除 stale `dq.run_results.unexpected_rows` 與整理 run history 的 cron job 或手動 SOP（per D#37 Tradeoff）**、**無 PK 表的 row data 撈取策略（per D#36 fallback）**、**違規 row 表格「智能聚焦」（預設只顯示違規欄位 + toggle 展開全部）（per D#38 Option D）**。
