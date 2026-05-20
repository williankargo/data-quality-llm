# Day 2 架構規劃 — AI-Powered Data Quality Assistant

本文件是 Day 2 的完整架構規劃，涵蓋所有已解決決策（Decision Log）、目前無待解決決策（Decision Points）以及實作規格（Specification）。請將本文件視為 Day 2 唯一的真實來源（single source of truth）。

Day 1 的決策（D#0–D#10）請參考 [day1-plan.md](./day1-plan.md)。

---

## Day 2 範圍

來自 `CLAUDE.md`：

**Backend**
- `schemas/rules.py` — GE 規則的 Pydantic 模型與 API 請求/回應結構
- `services/ai_generator.py` — Anthropic 客戶端封裝、Tool Use 結構化輸出（D#7）、Pydantic 二次驗證
- `services/ge_engine.py` — Great Expectations 對 Postgres 執行
- `services/rules_store.py` — `dq.rules` CRUD
- `services/runs_store.py` — `dq.runs` + `dq.run_results` 寫入/讀取
- `api/rules.py` — `POST /rules/suggest`、`POST /rules/from-nl`、`GET/POST /rules`、`PUT/DELETE /rules/{id}`
- `api/results.py` — `POST /runs`、`GET /runs/{id}`、`GET /runs/`
- 在 `main.py` 註冊 `rules` 與 `results` router
- `db/002_run_results_status.sql` — 新增 `status VARCHAR(10)` 三態欄位

**Frontend**
- Rule Management 視圖（`/tables/[name]?tab=rules`）
- Results Dashboard 視圖（`/tables/[name]?tab=results`）

**不在 Day 2 範圍**（延後到 Day 3）：LLM 回應快取（hash-based）、平行規則執行、行動裝置版面、true chat 對話歷史、規則編輯 PUT 的 UI（Day 2 僅支援 Delete + 重新建立）。

---

## Section 1: Decision Log（已解決決策）

每筆決策皆包含 **問題本質**（為什麼這是一個真實的決策、不是 trivial）與 **Tradeoff**（選擇此選項所放棄的東西）。

---

### D#11: 函式庫版本由 Day 1 `pyproject.toml` 鎖定

- **決定**：使用 `backend/pyproject.toml` 中現有的版本，Day 2 不升級：
  - `anthropic>=0.103.1`（Messages API + Tool Use）
  - `great-expectations>=1.17.2`（**GE 1.x**，與 0.x API 不相容）
  - `sqlalchemy>=2.0.49`、`psycopg[binary]>=3.3.4`
- **為什麼重要**：GE 1.x 用全新的 `gx.Context` + `Validator` + `BatchDefinition` 模型取代 0.x 的 Expectation Suite YAML 流程，2024 年以前的 blog 與 StackOverflow 答案幾乎都不適用。寫 `ge_engine.py` 必須直接讀官方 GE 1.x 文件。
- **考慮過的選項**：降級 GE 到 0.18.x（生態多但官方已標記 deprecated）。否決原因：在 Day 2 反向動 lockfile 等同於放棄 Day 1 的所有驗證。
- **如何選擇**：受 Day 1 既有 lockfile 約束。
- **問題本質**：跨主版本的 GE 不只是 API 換名而已，整個資料表達模型都改了 — 0.x 是「Suite 是檔案、Checkpoint 是 YAML、Datasource 是 config 文字檔」；1.x 是「所有東西都是 Python object、Context 持有所有 metadata、Validator 與 Batch 是兩個獨立概念」。寫 1.x 程式碼時若不小心抄到 0.x 的範例，會看到語法看似對、但 runtime 噴 `AttributeError: 'Context' object has no attribute 'add_expectation_suite'` 這種錯誤訊息。
- **Tradeoff**：放棄了 GE 0.x 的大量 tutorial 與 StackOverflow 內容；只能讀官方文件，初次 debug 時間會比較長。如果未來想接 GE Cloud 也只能用 1.x 路徑。

---

### D#12: API 形狀由 `CLAUDE.md` 鎖定

- **決定**：API 路徑與 HTTP method 完全照 `CLAUDE.md` 的表格，不另設計：
  - `POST /rules/suggest`、`POST /rules/from-nl`
  - `GET /rules`、`POST /rules`、`PUT /rules/{id}`、`DELETE /rules/{id}`
  - `POST /runs`、`GET /runs/{id}`、`GET /runs/`
- **為什麼重要**：前端 Day 2 同步在做，若 API path 變動會逼出第二輪前後端對接。
- **考慮過的選項**：用更 REST-ier 的 nested path（`POST /tables/{name}/rules/suggest`）。否決原因：CLAUDE.md 已敲定。
- **如何選擇**：受既有規格約束。
- **問題本質**：REST 風格在資源層級不明確時容易過度設計。`CLAUDE.md` 把 `/rules` 設計成 top-level 而非 `/tables/{name}/rules` 的 nested，意味著 rule 是 first-class entity（可以跨 table 列出、刪除時不依賴 table context）。這對 Day 2 的「規則管理」UX 來說是好事 — 只是 `GET /rules?table_name=X` 比 `GET /tables/X/rules` 多一個 query param 而已。
- **Tradeoff**：放棄 nested path 自帶的 `table_name` context；`GET /rules` 必須接受 `?table_name=` query param 才能 scope 列表。前端因此要記得帶。

---

### D#13: DB Schema 在 Day 1 已建立

- **決定**：使用 `backend/db/001_dq_schema.sql` 中已建好的 `dq.rules`、`dq.runs`、`dq.run_results`。Day 2 唯一新增的是 `002_run_results_status.sql`（為了 D#18 的三態）。
- **為什麼重要**：可以立即開始寫 store 層程式碼，不需中斷流程做 migration。
- **約束**：`dq.rules` 已存在欄位 `(id, table_name, expectation_type, kwargs JSONB, description, source, created_at, updated_at)`；`schemas/rules.py` 的所有 Pydantic 模型必須能無痛 round-trip 到此結構。
- **問題本質**：先建 schema、後寫 ORM 跟先寫 ORM、後 generate schema，兩種開發順序的 tradeoff 完全不同。MVP 規模小、schema 已經人工設計過，所以「以 SQL 為 source of truth、Pydantic model 對齊 schema」是更短的路徑。等 schema 演化次數變多時可以再轉成 Alembic-driven。
- **Tradeoff**：任何結構性變動（例如 D#18 要加 `status` 欄位）都需要寫一個 `00N_*.sql` 然後手動跑 — 比 Alembic auto-generate migration 多一步，但小規模可接受。

---

### D#14: 前端寫入路徑統一用 TanStack Query mutation

- **決定**：Day 2 所有寫入操作（save rule、delete rule、trigger run）使用 `useMutation`；成功後用 `queryClient.invalidateQueries({ queryKey: [...] })` 觸發相關查詢的 refetch。
- **為什麼重要**：延續 Day 1 用 `useQuery` 的 server-state 管理風格；避免在 component 中混用 `useState + fetch + 手動 refetch`，產生 boilerplate。
- **考慮過的選項**：直接在 `onClick` handler 裡 `apiFetch`。否決原因：失去 cache invalidation；每個 component 都要重寫 loading/error state。
- **問題本質**：React 中「server state」與「local UI state」是兩個獨立問題。`useState` 適合管 local state，但管 server state 會逼開發者自己處理 caching、refetching、stale-while-revalidate、error retry 這四件事。TanStack Query 的 `useMutation` 把這些抽象成「mutation 完成 → invalidate 相關 query key → UI 自動 refetch」的單一 pattern，等於不用想就有正確行為。
- **Tradeoff**：要學 `useMutation` 的 lifecycle（`onMutate` / `onSuccess` / `onError` / `onSettled`），初次用會卡一下。Optimistic update 也要寫 `onMutate` + `onError` rollback，但 Day 2 暫不做 optimistic（除了 Delete 規則卡片）。

---

### D#15: Error envelope 完全沿用 Day 1

- **決定**：Day 2 所有 endpoint 沿用 Day 1 的 `ErrorEnvelope`（`{error: {code, user_message, technical_detail}}`）。新增的 error code（見 3.3.3）只是擴充 `code_map`，不改 envelope 結構。
- **為什麼重要**：前端 `ApiError` class 與 `<ErrorState>` component 已能處理此格式；新 error code 直接 work。
- **問題本質**：API 錯誤 contract 越早穩定越好。改 envelope 結構是 cross-cutting change，要動所有 endpoint + 前端 `apiFetch` 一起改；改 `code_map` 只是字典加 entry。Day 1 的設計通過了 D#10 的驗證，沒有理由動。
- **Tradeoff**：無 — 純粹累加。

---

### D#16: GE 執行模式 = SQL Datasource

- **決定**：`services/ge_engine.py` 使用 Great Expectations 1.x 的 **Postgres SQL Datasource**。流程為 `Context → Datasource → TableAsset → BatchDefinition → Batch → batch.validate(expectation)`。資料完全留在 Postgres，GE 自己生 SQL。
- **為什麼重要**：這是 Day 2 最 load-bearing 的決策 — 決定了 `ge_engine.py` 的整體形狀、執行的記憶體 footprint、以及結果如何映射到 `dq.run_results`。事後改最痛。
- **考慮過的選項**：
  - Pandas DataFrame in-memory（簡單但會把整張表載入 Python 記憶體；若未來指向真實大表會 OOM）。
  - 自己寫 SQL emulator（完全控制結果格式但違反 CLAUDE.md「不要重新發明輪子」原則）。
- **如何選擇**：使用者選定 SQL Datasource，理由是 production fidelity 與「資料不離開 DB」的安全模型。
- **問題本質**：Data quality 工具的核心張力是「驗證邏輯該住在哪？」— Pandas 路徑等同於「把資料 pull 到應用層、用 Python 算」，SQL 路徑等同於「把驗證 push down 到 DB、用 SQL 算」。前者開發體驗好（一切都是 DataFrame，可印、可 debug），但對「真實大表」毫無防衛；後者開發成本高（GE 1.x 的 Datasource/Validator/Batch 層級多），但天生 scalable。我們選後者，是賭「production fidelity 與 demo 時的安全性敘事」值得這個學習曲線。
- **Tradeoff**：放棄了 Pandas 的「印 DataFrame、interactive debug」工作流。GE 1.x SQL Datasource 的錯誤訊息在 schema 不符時較難理解（會看到 SQLAlchemy + GE 雙層 stack trace）。`DATABASE_URL` 格式（`postgresql+psycopg://`）與 GE `add_postgres(connection_string=...)` 期望的格式（純 `postgresql://`）不同，需要在 `ge_engine.py` 做一次字串轉換。

---

### D#17: Run 執行模式 = 同步阻塞

- **決定**：`POST /runs` 同步執行所有規則，寫入 `dq.runs` + `dq.run_results`，回傳完整 `{run_id, status, results: [...]}`。`dq.runs.status` 只會有 `success` / `failed` 兩種值（不會有 `running`）。
- **為什麼重要**：影響 API contract 形狀（同步 = 回應裡帶 `results` 陣列；非同步 = 回應只帶 `run_id`、要靠 polling）與前端 loading UX。
- **考慮過的選項**：FastAPI BackgroundTasks + 前端輪詢 GET（更響應、但 BackgroundTasks 沒有真正的 worker 隔離）、Server-Sent Events（最佳 UX、但 TanStack Query 不擅長 streaming）。
- **如何選擇**：使用者選同步，理由為 MVP 規模下 GE 執行 < 2 秒，非同步的複雜度不值得。
- **問題本質**：HTTP 同步 vs 非同步的選擇不是技術偏好問題，而是「使用者願意盯著畫面等多久」的 UX 問題。經驗值：5 秒以內同步 fine、5–15 秒同步可以但要有 loading state、15 秒以上一定要非同步否則 browser timeout / proxy 502 / 使用者開始按重新整理。MVP seed data 大概 50 列 × 8 條規則，GE SQL 化後每條 < 100ms，總共估 1 秒左右，遠在同步舒適區。Day 3 polish 階段若想 demo 大表場景，再升級成非同步。
- **Tradeoff**：放棄了「執行中也能即時看每條規則進度」的 UX。若未來把同一支 API 指向 100 萬列大表（單條 expectation 可能要 10 秒），HTTP 會 timeout — 需要的時候重構成 background job，估計成本一天。

---

### D#18: 結果狀態模型 = 三態（pass / fail / error）

- **決定**：`dq.run_results` 新增 `status VARCHAR(10) NOT NULL`（值為 `'pass'` / `'fail'` / `'error'`）。透過 `002_run_results_status.sql` migration 加入。前端用紅黃綠對應：綠 = pass、紅 = fail（資料違反規則）、黃 = error（規則本身執行失敗，例如欄位不存在、type mismatch、GE 內部例外）。
- **為什麼重要**：CLAUDE.md 明示要求 red/yellow/green 配色，使用者體驗的 clarity 是 Product Thinking 評分項。
- **考慮過的選項**：兩態（保留現有 `success BOOLEAN`，例外 normalize 成 fail）、DB 兩態 + API 推導三態（避免 migration 但 store/API 隱性耦合）。
- **如何選擇**：使用者選三態，理由為 Product Thinking 加分明確。
- **問題本質**：「規則沒過」這件事，根本原因有兩種：（1）規則正確、資料違反規則（業務洞察 — 資料有問題）；（2）規則本身執行不起來（技術錯誤 — 規則寫錯了）。把這兩種混在同一個紅色狀態下，會讓非技術使用者完全無法分辨「我該叫資料管理員修資料」還是「我該叫工程師修規則」。三態的價值不在資料庫設計、不在 API 設計，而在「使用者看到黃燈時知道要做什麼」這件事 — 這正是 Product Thinking 評分項要看的。
- **Tradeoff**：增加 schema migration（一個 `002_*.sql` 檔案 + ALTER TABLE）、store 層要寫入第三個值、API response model 要露出 `status` enum、前端要做三色 mapping。估 1.5 小時額外工作量。`success BOOLEAN` 欄位保留（為了向下相容與雙重驗證），但讀取時以 `status` 為準。

---

### D#19: 規則建議流程 = 草稿模式（Suggest 不入 DB）

- **決定**：`POST /rules/suggest` **不寫 DB**，只回傳記憶體中的 draft 陣列。前端把 draft 顯示為卡片，每張有 `[Save]` `[Discard]` 按鈕；按 Save 才打 `POST /rules` 入庫，並設 `source='ai_schema'`。
- **為什麼重要**：決定 `POST /rules/suggest` 的 API 形狀（回傳陣列 vs 回傳 id 列表）、`dq.rules.source` 的語意、前端的「review-before-save」UI、以及 undo 的行為模型。
- **考慮過的選項**：自動全存、使用者刪不要的；Hybrid（草稿 + Save all 批次按鈕）。
- **如何選擇**：使用者選草稿模式，理由為 AI 是協作者不是覆蓋者，符合 Product Thinking 訴求。
- **問題本質**：當 AI 替使用者「做出」決定（直接寫 DB）vs「建議」決定（顯示草稿），其實是兩種完全不同的 trust model。前者宣告「AI 永遠對、你只要校稿」，後者宣告「AI 提案、你來決定」。MVP 的目標使用者是非技術領域專家 —「校稿 AI 寫進 DB 的內容」這件事對他們的認知負荷更高（需要先讀懂、再判斷對錯、再決定刪不刪）；而「看 AI 的提案、勾選喜歡的」對非技術使用者更直覺、心理負擔更小。這個選擇定義了整個產品的 AI 關係定位，不只是技術設計。
- **Tradeoff**：每條規則要兩個 click（suggest → save）；前端要管 draft state（不能存 localStorage，因為 LLM 輸出可能含 PII，刷新頁面就消失也算 feature）。

---

### D#20: Run 範圍 = table 內全部規則

- **決定**：`POST /runs` request body 僅接受 `{table_name: string}`。後端 SELECT `dq.rules WHERE table_name=:name` 取出全部規則執行。沒有 `rule_ids` 子集參數。
- **為什麼重要**：決定 request body 形狀、re-run UX（每個 table 一個 Run 按鈕，沒有「只 re-run 失敗的」per-rule 按鈕）、以及 `dq.run_results.rule_id` 在 rule 被刪後的歷史保留語意（`ON DELETE SET NULL` 保留歷史結果）。
- **考慮過的選項**：接受 `rule_ids` 子集、雙模式（`rule_ids` 可選 default 全跑）。
- **如何選擇**：使用者選全跑，理由為 MVP 簡潔；per-rule re-run 留到 Day 3。
- **問題本質**：「執行粒度」是 data quality 工具的長期分歧點。粗粒度（per-table）的好處是 mental model 簡單 — 「我關心這張表的健康度」是一個整體判斷；細粒度（per-rule）的好處是工程效率高 — 「我只改了一條規則、不想再跑整批」。MVP 規模下總執行時間 < 2 秒（D#17），細粒度節省的時間根本感受不到 — 那此時細粒度的成本（前端要追蹤勾選狀態、URL 要編碼勾選集合、結果要 merge 進歷史）就完全是負擔。Day 3 若 demo 場景變成「100 條規則、單條跑 5 秒」，再加 `rule_ids` 也只是把 endpoint 從 required 變 optional，向下相容。
- **Tradeoff**：放棄了 per-rule re-run；想 re-run 單條只能 re-run 整個 table（在 MVP 規模下不痛）。Results Dashboard 不會有 per-rule 的「↻」按鈕。

---

### D#21: NL clarification UX = 一次性溝通

- **決定**：`POST /rules/from-nl` request body 為 `{table_name, description}`，response 為 discriminated union：
  - `{type: "rule", rule: {expectation_type, kwargs, description}}`
  - `{type: "clarification", question: string}`
  - 前端在收到 `clarification` 時，把 question 顯示成輸入框上方的訊息；使用者重新輸入更詳細的描述（不會自動帶入原本的 description）。
- **為什麼重要**：決定 `from-nl` endpoint 是 stateless 還是 stateful；決定前端 NL 輸入元件是 single-shot 還是對話框；決定 prompt 是否需要支援 message history。
- **考慮過的選項**：完整 chat（messages history）、Hybrid（允許一次 follow-up）。
- **如何選擇**：使用者選一次性溝通；conversational chat 留給 Day 3 bonus。
- **問題本質**：CLAUDE.md 把使用介面描述成「chat-style」，但「chat-style 的視覺」與「stateful 對話的後端」是兩回事。要做出 chat 視覺只需要把輸入框與訊息泡泡疊起來；真正 stateful 對話則需要 message history、prompt 要會處理 history、token 成本指數成長、prompt eviction 策略要設計。MVP 訴求只需要前者，後者的工程投資對核心評分項（AI-First、Product Thinking、Technical Implementation）沒有比例性的回報。Day 3 若需要 chat 是 bonus item。
- **Tradeoff**：放棄了「多輪對話」UX；使用者收到 clarification 後需要重新打字。當下 prompt 的 `request_clarification` 已要求 LLM 給「具體的 follow-up question」，使用者通常一次補完就能成功，不會反覆很多輪。

---

### D#22: 規則重複處理 = 後端標記、前端 disable Save

- **決定**：`POST /rules/suggest` 回傳的每張 draft 多帶一個 `already_saved: bool` 旗標 — 後端會比對該 table 的現有 `dq.rules`，若 `(expectation_type, kwargs)` 已存在則 `already_saved=true`。前端顯示時：`already_saved=true` 的卡片上顯示 "Already saved" badge 並 disable Save 按鈕（但卡片本身仍顯示，讓使用者看到 AI 重複提到什麼）。後端 `POST /rules` 寫入時不做 dedupe 也不加 UNIQUE constraint（允許使用者刻意建立看似重複的規則）。
- **為什麼重要**：決定 `dq.rules` schema 是否需要 UNIQUE constraint（不要）、`/rules/suggest` response 是否需要擴充欄位（要 — 加 `already_saved`）、以及前端 draft card 元件的 disabled state UI。
- **考慮過的選項**：後端 filter 掉重複的（前端看不到）、`POST /rules` 抱錯回 409、完全不管。
- **如何選擇**：使用者選「顯示但標記」，理由為透明度高 — 使用者能看見 AI 又提了哪些舊建議，不會誤以為自己漏掉新規則。
- **問題本質**：軟體設計常有一個迷思：「重複是錯的、要消除」。但對使用者來說，「為什麼這個建議沒出現？」比「為什麼這個建議重複出現？」更難 debug — 隱性 filter 會讓使用者誤以為「AI 想不到那條規則」，而事實是「AI 想到了但被我們藏起來」。透明地顯示重複（並標記 already saved）是「不撒謊的設計」 — 使用者能看見 AI 完整的提案，也能看見哪些已存在，做決策時資訊完整。這同時避免了 DB UNIQUE constraint 在 JSONB 上的技術難題（需要 `md5(kwargs::text)` expression index，對 key 順序與空白脆弱）。
- **Tradeoff**：suggest response 多了一個欄位（前端 type 要對齊）；前端卡片元件要多寫 disabled state；DB 允許重複（若使用者透過 PUT 把兩條本來不同的規則改成一樣，也不阻止 — Day 2 暫不支援 PUT UI，所以不會發生）。

---

## Section 2: Decision Points（待解決決策）

**（空 — 所有決策已解決。）**

實作期間若浮現新的架構選擇，停下來、加 Decision Point、等使用者答案、再繼續。

---

## Section 3: Specification

### 3.1 問題重述

Day 2 的目標是把 Day 1 的骨架升級成可用的閉環：使用者選一張 table → 按 Suggest 看到 AI 提案的規則 → 勾選想要的存入 DB → 用自然語言補幾條客製規則 → 按 Run 看到紅黃綠結果與違規樣本 → 重整頁面後結果還在。

**Day 2 結束的最低 demo bar**：使用者能在 `policyholders` 表上完成「Suggest → Save 5 條 → 用 NL 加 1 條 → Run → 看到紅黃綠 + 違規 sample」整個流程，且後端 console 沒有 unhandled exception。

**模糊與假設**：
- 前面提到的「demo 看到紅色失敗結果」需要在 seed data 之外手動 INSERT 一條 dirty row（D#2）— Day 2 的 README 補上這個指令。
- Day 2 不做 PUT `/rules/{id}` 的前端 UI（後端要實作 endpoint，但前端僅支援 Delete + 重新建立）— 避免 edit form 與 GE schema 編輯器的設計負擔。

---

### 3.2 影響範圍（檔案路徑）

#### Backend（`backend/`）

```
backend/
├── pyproject.toml                         # 不動（GE 與 Anthropic 已在 Day 1 鎖好）
├── app/
│   ├── main.py                            # +註冊 rules_router、results_router
│   ├── schemas/
│   │   ├── rules.py                       # 新增：GE rule、suggest/from-nl 請求回應
│   │   └── runs.py                        # 新增：run、run_result 請求回應
│   ├── services/
│   │   ├── ai_generator.py                # 新增：Anthropic client + Tool Use + prompt 注入 + Pydantic 驗證
│   │   ├── ge_engine.py                   # 新增：GE 1.x SQL Datasource 執行
│   │   ├── rules_store.py                 # 新增：dq.rules CRUD（含 already_saved 比對）
│   │   └── runs_store.py                  # 新增：dq.runs + dq.run_results 寫入/讀取
│   └── api/
│       ├── rules.py                       # 新增：5 個 endpoint
│       └── results.py                     # 新增：3 個 endpoint
├── db/
│   └── 002_run_results_status.sql         # 新增：ALTER TABLE 加 status VARCHAR(10)
└── tests/
    ├── test_rules.py                      # 新增：rules endpoint + ai_generator (mocked)
    └── test_runs.py                       # 新增：runs endpoint + ge_engine (in-memory)
```

#### Frontend（`frontend/`）

```
frontend/
├── app/tables/[name]/page.tsx             # 不動（已支援 tab 切換）
├── components/
│   ├── TableTabs.tsx                      # 修改：rules / results tab 改為實際元件
│   ├── RulesView.tsx                      # 新增：Rule Management 主視圖
│   ├── RuleCard.tsx                       # 新增：單一規則卡片（draft / saved 兩態 + already_saved badge）
│   ├── NlRuleInput.tsx                    # 新增：自然語言輸入框 + clarification 訊息
│   ├── ResultsView.tsx                    # 新增：Results Dashboard 主視圖
│   ├── ResultRow.tsx                      # 新增：單一結果列（pass/fail/error 三色 + expand 違規樣本）
│   └── RunButton.tsx                      # 新增：Run + loading state
├── lib/
│   ├── queries.ts                         # +useRules / useRun / useLatestRun
│   └── mutations.ts                       # 新增：useSuggestRules / useSaveRule / useDeleteRule / useNlRule / useTriggerRun
└── types/
    └── api.ts                             # 擴充：Rule, RuleDraft, RunSummary, RunResult, ResultStatus
```

#### Docs（`docs/`）

```
docs/
├── day2-plan.md                           # 本文件
└── ai-tools-usage.md                      # 每日更新 Day 2 entries
```

---

### 3.3 設計細節

#### 3.3.1 Backend — Schemas

**`app/schemas/rules.py`**

```python
class GeRule(BaseModel):
    """單一 GE 規則的標準結構（用於 store、API、ai_generator output）"""
    expectation_type: str           # 例 "expect_column_values_to_not_be_null"
    kwargs: dict[str, Any]          # 例 {"column": "national_id"}
    description: str                # 給非技術使用者看的白話描述

class RuleRecord(GeRule):
    """從 DB 讀出的 rule，含 id / table_name / source / timestamps"""
    id: int
    table_name: str
    source: Literal["ai_schema", "ai_nl", "user"]
    created_at: datetime
    updated_at: datetime

class RuleDraft(GeRule):
    """LLM suggest 回傳的草稿，含 already_saved 比對結果（D#22）"""
    already_saved: bool

class SuggestRequest(BaseModel):
    table_name: str

class SuggestResponse(BaseModel):
    drafts: list[RuleDraft]
    # 不回傳 raw LLM response — 已經透過 Tool Use 結構化

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
    pass  # PUT 只能改 expectation_type / kwargs / description；不能改 table_name / source
```

**`app/schemas/runs.py`**

```python
ResultStatus = Literal["pass", "fail", "error"]

class RunResult(BaseModel):
    id: int
    rule_id: int | None              # rule 被刪後保留歷史；對應為 None
    expectation_type: str
    status: ResultStatus              # D#18 三態
    success: bool                     # 保留欄位；pass=True、fail/error=False
    unexpected_count: int | None
    unexpected_sample: list[Any] | None   # 1–3 筆樣本（CLAUDE.md 約束）
    observed_value: Any | None
    error_message: str | None         # status=error 時填入

class RunSummary(BaseModel):
    id: int
    table_name: str
    status: Literal["success", "failed"]  # 整體 run 是否完成（不是個別規則的 pass/fail）
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

純 SQL helpers（透過 SQLAlchemy `text()`），不引入 ORM declarative model（避免在 MVP 為 4 個欄位寫一個 model class）。

```
list_rules(session, table_name: str | None) -> list[RuleRecord]
get_rule(session, rule_id: int) -> RuleRecord | None
create_rule(session, table_name: str, source: str, rule: GeRule) -> RuleRecord
update_rule(session, rule_id: int, rule: GeRule) -> RuleRecord
delete_rule(session, rule_id: int) -> bool
mark_drafts_already_saved(session, table_name: str, drafts: list[GeRule]) -> list[RuleDraft]
    # D#22：比對 (expectation_type, kwargs) — kwargs 比對採 canonical JSON dump（sort_keys=True）
```

**`app/services/runs_store.py`**

```
create_run(session, table_name: str) -> int  # 回傳 run_id，status='running'（過渡態，內部用）
finalize_run(session, run_id: int, status: 'success'|'failed', error_message: str | None) -> None
write_result(session, run_id: int, rule_id: int, result: RunResult) -> None
get_run(session, run_id: int) -> RunDetail | None
list_runs(session, table_name: str | None, limit: int = 20) -> list[RunSummary]
get_latest_run_for_table(session, table_name: str) -> RunDetail | None  # 前端 Results Dashboard 首次載入
```

**`app/services/ai_generator.py`**

```python
class AiGenerator:
    def __init__(self): self.client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    def suggest_rules(self, table_name: str, columns: list[ColumnInfo], sample_rows: list[dict]) -> list[GeRule]:
        prompt = load_template("rule_from_schema.md", {
            "table_name": table_name,
            "columns_json": json.dumps([c.model_dump() for c in columns], indent=2),
            "sample_rows_json": json.dumps(sample_rows[:20], default=str, indent=2),  # 截前 20 列（prompt 既有約束）
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
            tool_choice={"type": "any"},  # 強制呼叫其中一個 tool
            ...
        )
        return self._dispatch_nl_response(response)
```

Tool schema 定義 inline 在 `ai_generator.py`（不另存檔，方便修改）：

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
# PROPOSE_RULE_TOOL（單條）、REQUEST_CLARIFICATION_TOOL 同上結構
```

**Pydantic 二次驗證**：Tool Use 保證 schema 對，但不保證語意對。`_extract_and_validate_rules` 要：
1. 拿 tool_use block 的 `input.rules`
2. 每條塞進 `GeRule.model_validate(...)`（若失敗則 raise `LlmOutputError`）
3. 回傳 `list[GeRule]`

**`app/services/ge_engine.py`**

```python
class GeEngine:
    def __init__(self):
        # GE 1.x ephemeral context（不寫 GE 內建 store）
        self.context = gx.get_context(mode="ephemeral")
        # DATABASE_URL 轉換：postgresql+psycopg:// → postgresql://（GE 不認 SQLAlchemy dialect 前綴）
        pg_url = settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)
        self.datasource = self.context.data_sources.add_postgres(
            name="dq_pg",
            connection_string=pg_url,
        )

    def run_rules(self, table_name: str, rules: list[RuleRecord]) -> list[RunResult]:
        """對單一 table 跑一組規則，回傳結構化結果（不寫 DB — runs_store 負責）"""
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
        # 用 getattr 從 gx.expectations 取 class（例 ExpectColumnValuesToNotBeNull）
        # GE expectation_type 是 snake_case，class 名是 CamelCase — 用簡單 mapping table 或 inflection 函式轉換
        ...
```

**規則結果 normalize**：
- `_normalize_pass_fail`: 從 `ge_result.success` 推 `status`；`unexpected_count` 從 `result.result.get("unexpected_count")` 取；`unexpected_sample` 取 `result.result.get("partial_unexpected_list", [])[:3]`
- `_normalize_error`: `status="error"`、`error_message=str(e)`、`unexpected_*=None`、`success=False`

**潛在踩坑**：GE 1.x 在 SQL backend 下對某些 expectation 的 `partial_unexpected_list` 行為與 Pandas backend 不同 — 視情況可能要設 `result_format={"result_format": "SUMMARY", "partial_unexpected_count": 3}` 在 `validate()` 呼叫。

#### 3.3.3 Backend — API endpoints

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

**新增的 error codes（擴充 main.py 的 code_map）**：
- `LLM_TIMEOUT` — Anthropic API > 60s 無回應。user_message: "AI 服務暫時沒有回應，請稍後再試。"
- `LLM_OUTPUT_INVALID` — Tool use 結構通過但 Pydantic 驗證失敗。user_message: "AI 回傳的規則格式有誤，請重試。"
- `RULE_NOT_FOUND` — PUT/DELETE 不存在的 rule_id。
- `RUN_NOT_FOUND` — GET 不存在的 run_id。
- `GE_EXECUTION_FAILED` — `run_rules()` 整體失敗（非個別規則 error）。user_message: "規則執行失敗，請檢查表名或欄位設定。"

#### 3.3.4 Frontend — components

**`RulesView`**（rules tab 的 root）

```
─────────────────────────────────────────
│ [✨ Suggest rules]  [✏️ Add rule by description ▼]
─────────────────────────────────────────
│ Suggested (drafts)                    │  ← 只在 suggest 後出現
│ ┌──────────────────────────────────┐  │
│ │ expect_column_values_to_not_be_null │
│ │ Every policyholder must have...    │
│ │ Already saved                      │  ← 若 already_saved=true
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

**`NlRuleInput`** — collapsible，展開後是 textarea + Submit；後端回 `clarification` 時把 `question` 顯示在 textarea 上方紅色提示框，textarea 不會自動填入舊內容（D#21）。

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

色票：綠 = `text-green-600 bg-green-50`、紅 = `text-red-600 bg-red-50`、黃 = `text-amber-600 bg-amber-50`。

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

`apiFetch` 要小幅擴充以支援 `method` 與 `body`（Day 1 只支援 GET）。

---

### 3.4 風險與可逆性

| 風險 | 嚴重度 | 可逆性 | 緩解 |
|------|--------|--------|------|
| GE 1.x SQL Datasource 在某些 expectation 對 SQL backend 行為不同（例如 `partial_unexpected_list` 為空） | 高 | 中 | `_normalize_pass_fail` 處理 `None` 樣本 + 在 `validate()` 設定 `result_format={"result_format": "SUMMARY", "partial_unexpected_count": 3}` |
| Anthropic Tool Use 回傳的 `kwargs` 出現非預期型別（例如把數字字串而非數字） | 中 | 易 | Pydantic 用 `ConfigDict(strict=False)` + GeRule.kwargs 不做 strict typing；GE 執行時若型別錯會落入 `status=error`（D#18），不會 crash |
| DATABASE_URL 轉換為 GE 用格式時遺漏 query string（如 `?sslmode=require`） | 中 | 易 | `replace("postgresql+psycopg://", "postgresql://")` 只動 scheme 不動其他 — 寫測試覆蓋 |
| Suggest 重複呼叫造成 token 浪費 | 低 | 易 | Day 3 加 hash-based cache；Day 2 不防 |
| Optimistic delete 在後端失敗時 race condition（使用者快速連點兩次刪不同 rule） | 低 | 易 | `onError` rollback 用 `ctx.prev`；TanStack Query 自帶序列化保證 |
| GE 例外的 error_message 含敏感資訊（DB 結構、連線字串） | 中 | 易 | `_normalize_error` 截斷 message 到 200 字、移除任何含 `postgresql://` 的子字串 |
| 三態 migration 002 在 Supabase 上手動跑時忘記 NOT NULL default | 中 | 易 | `002_*.sql` 寫 `ALTER TABLE ... ADD COLUMN status VARCHAR(10) NOT NULL DEFAULT 'pass'`，後續寫入會覆蓋 |

**最難 reverse 的決定**：
- **D#16（GE SQL Datasource）**：轉成 Pandas 路徑要重寫 `ge_engine.py` 大部分；估 4–6 小時。
- **D#18（三態）**：往回退成兩態要動 migration + store + API + 前端，估 2 小時。

---

### 3.5 Rollout Phases（每階段附 verification）

> 每階段的 Verification 通過後才能進入下一階段。

#### Phase 1: Schemas + DB migration（est. 1 小時）

**Outcome**：DB 加了 `status` 三態欄位，Pydantic 模型與 `rules_store` CRUD 就位，後端的「資料形狀」從此確定。

任務：
1. 寫 `db/002_run_results_status.sql`，在 Supabase SQL editor 跑。
2. 寫 `app/schemas/rules.py`、`app/schemas/runs.py`。
3. 寫 `app/services/rules_store.py`（純 CRUD，不含 AI）。

**Verification**：
- `psql` 查 `SELECT column_name FROM information_schema.columns WHERE table_schema='dq' AND table_name='run_results';` 含 `status`。
- `uv run pytest tests/test_rules.py::test_rules_store_crud` 通過（手動 fixture 寫一條進 DB、取出來、刪掉）。

#### Phase 2: AI Generator + rules endpoints（est. 3–4 小時）

**Outcome**：六支 `/rules` endpoint 全部上線，Anthropic Tool Use 整合完成，可以用 curl 測試整個「Suggest → 標記重複 → NL 轉規則 → CRUD」流程。

任務：
1. `services/ai_generator.py` 實作 `suggest_rules` 與 `rule_from_nl`，含 Tool Use schemas。
2. `api/rules.py` 5 個 endpoint。
3. 在 `main.py` 註冊 `rules_router`。
4. `tests/test_rules.py` 加 mocked Anthropic client 的 endpoint tests。

**Verification**：
- `curl -X POST http://localhost:8000/rules/suggest -d '{"table_name":"policyholders"}'` 回傳 5–10 條 draft，每條含 `already_saved: false`（DB 還空）。
- 接著 `curl -X POST http://localhost:8000/rules -d '<從上一步挑一條>'` 寫入後，再呼叫一次 suggest 時相同規則 `already_saved: true`。
- `curl -X POST .../rules/from-nl -d '{"table_name":"policies","description":"premium 不能是負的"}'` 回 `{type:"rule",...}`。
- 模糊輸入 `{"description": "資料要好"}` 回 `{type:"clarification", question:"..."}`。
- `uv run pytest tests/test_rules.py` 全綠。

#### Phase 3: GE Engine + runs endpoints（est. 3–4 小時）

**Outcome**：GE 1.x SQL Datasource 跑起來，`POST /runs` 能同步執行一張表的全部規則，結果以三態（pass/fail/error）寫入 DB，`GET /runs` 可讀取歷史。

任務：
1. `services/ge_engine.py` 實作 `GeEngine.run_rules`。
2. `services/runs_store.py` 寫入/讀取邏輯。
3. `api/results.py` 3 個 endpoint。
4. 在 `main.py` 註冊 `results_router`。
5. `tests/test_runs.py` — 用 in-memory SQLite + GE 對 SQLite datasource 驗證流程（不 hit Supabase）。

**Verification**：
- 在 Supabase 手動 `INSERT INTO public.policyholders (national_id, full_name, birth_date, gender) VALUES (NULL, 'dirty', '2020-01-01', 'X');` 製造一筆 dirty row。
- `curl -X POST http://localhost:8000/runs -d '{"table_name":"policyholders"}'` 回 `RunDetail`，至少 1 條 `status="fail"`（gender 不在 set）、1 條 `status="fail"`（national_id 為 null）。
- `curl http://localhost:8000/runs/<id>` 回相同結果。
- 故意 INSERT 一條規則指向不存在的欄位 `nonexistent_col`，run 後該規則 `status="error"` 且 `error_message` 含「does not exist」。

#### Phase 4: 前端 Rule Management（est. 4–5 小時）

**Outcome**：`/tables/[name]?tab=rules` 頁面可用：Suggest 出現草稿卡片、Save/Discard 操作、NL 輸入框、Delete 有 optimistic UI。

任務：
1. `components/RulesView.tsx`、`RuleCard.tsx`、`NlRuleInput.tsx`。
2. `lib/mutations.ts`、擴充 `lib/api.ts` 支援 POST/PUT/DELETE。
3. 在 `TableTabs.tsx` 把 rules tab 從 placeholder 換成 `<RulesView />`。
4. `types/api.ts` 擴充。

**Verification**：
- 開 `/tables/policyholders?tab=rules`，點 Suggest，3 秒內看到 5–10 張 draft 卡片。
- 點其中一張的 Save，卡片消失（或 disable），下方「Saved rules」區出現該規則。
- 再點一次 Suggest，相同規則的卡片顯示「Already saved」badge 且 Save 按鈕 disabled。
- 在 NL 輸入「premium 不能是負的」，看到一張 draft；輸入「資料要好」，看到 clarification 訊息。
- 對任一 saved rule 按 Delete，卡片立即消失（optimistic），後端確認後 invalidate 重新 fetch。

#### Phase 5: 前端 Results Dashboard（est. 3–4 小時）

**Outcome**：`/tables/[name]?tab=results` 頁面可用：Run 按鈕觸發執行、結果以紅黃綠三色呈現、展開可見違規樣本，整個 demo 閉環打通。

任務：
1. `components/ResultsView.tsx`、`ResultRow.tsx`、`RunButton.tsx`。
2. `useTriggerRun` mutation、`useLatestRun` query。
3. 在 `TableTabs.tsx` 把 results tab 換成 `<ResultsView />`。

**Verification**：
- `/tables/policyholders?tab=results` 初次載入：若 `dq.runs` 無歷史，顯示 empty state「按 Run 開始檢查」。
- 點 Run，按鈕進 loading state，2 秒內結果出現：綠/紅/黃三色行可見。
- Expand 任一紅色行，看到 violating sample 與 count。
- 切換到 rules tab 刪一條規則、回到 results tab 重新整理 — 上次 run 結果仍顯示（從 DB 讀），按 Run 後新結果不含已刪規則。
- 把後端關掉，重新整理 — 看到 `<ErrorState>`（沿用 Day 1 D#10）。

#### Phase 6: 文件與 README（est. 1 小時）

**Outcome**：`ai-tools-usage.md` 補齊 Day 2 entries，README 的 5 分鐘 demo 包含 INSERT dirty row 指令，CLAUDE.md 的 checklist 打勾，任何人 clone repo 後能自己走完整個流程。

任務：
1. 更新 `docs/ai-tools-usage.md` 加 Day 2 entries（含 prompt template iteration 過程、Tool Use schema 設計取捨）。
2. 更新 `README.md`「5 分鐘 demo」段落，加入：
   - 手動 INSERT dirty row 的 SQL（用於 demo fail 結果）
   - 「Suggest → Save → NL → Run」整個流程的逐步說明
3. 更新 `CLAUDE.md` 的 Task Breakdown，把 Day 2 項目打勾。

**Verification**：
- 從零 clone 一份 repo，照 README 跑，5 分鐘內能完成 demo。
- `docs/ai-tools-usage.md` 至少有 4 條 Day 2 entry（covering prompt iteration、Tool Use schema 設計、GE 1.x debugging、UI component design）。

---

### 3.6 Day 3 進入條件

以下全部為真才能進入 Day 3：

- [ ] `POST /rules/suggest` 回傳含 `already_saved` 的 draft 陣列。
- [ ] `POST /rules/from-nl` 支援 rule + clarification 兩種回應。
- [ ] `GET/POST/PUT/DELETE /rules` 完整 CRUD 通過 curl 測試。
- [ ] `POST /runs` 同步執行、回傳 `RunDetail`；`dq.run_results.status` 寫入三態值。
- [ ] `GET /runs/{id}` 與 `GET /runs?table_name=X` 工作正常。
- [ ] 前端 Rule Management：Suggest / Save / Discard / NL input / Delete 全部可操作。
- [ ] 前端 Results Dashboard：Run / 紅黃綠三色 / Expand 違規樣本可操作。
- [ ] `db/002_run_results_status.sql` 已在 Supabase 跑過。
- [ ] `docs/ai-tools-usage.md` 含至少 4 條 Day 2 entries。
- [ ] README 5 分鐘 demo 可重現整個流程（含 INSERT dirty row）。
