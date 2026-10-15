# Implementation Plan: AI-Powered Restaurant Recommendation System

> **Based on:** [architecture.md](architecture.md) (structure) and [context.md](context.md) (data facts and decisions).
> When the two differ, architecture.md wins: for example, relaxation is budget, then rating, and candidates use the one-line format.
> **Scope:** a lean test project with 4 phases. Each phase ends in something that can be run and checked.

---

## Phase Overview

| Phase | Goal | Flow step(s) | Output you can run | Reqs |
|---|---|---|---|---|
| **0** | Setup and data check | — | `pytest` runs, and the dataset facts are verified | — |
| **1** | Catalogue, filter, and API skeleton | Catalogue, Filter, API | `GET /health`, `GET /options`, and filter-only `POST /recommendations` | R1–R4 |
| **2** | LLM ranking | LLM | `POST /recommendations` returns the top 5 with AI explanations | R5–R9 |
| **3** | Frontend and wrap-up | UI | End to end: the Streamlit form calls the API and shows result cards | R3, R10 |

```text
Phase 0 ──▶ Phase 1 ──▶ Phase 2 ──▶ Phase 3
 setup      backend      backend     frontend
            (no LLM)     (+ LLM)     + README
```

---

## Phase 0: Setup and Data Check

**Goal:** set up the project skeleton and confirm the dataset assumptions marked **Verify** in context §3.2 before writing any logic.

### Tasks
1. Create the folder layout from architecture §7: `backend/`, `frontend/`, `tests/`, and `data/`, each with an empty `__init__.py` where needed.
2. Add `requirements.txt`, listing fastapi, uvicorn, pandas, pyarrow, datasets, ftfy, groq, pydantic, python-dotenv, streamlit, httpx, and pytest.
3. Add the support files:
   - `.gitignore`, covering `.env`, `data/`, `__pycache__/`, and `.venv/`
   - `.env.example`, covering `GROQ_API_KEY`, `LLM_MODEL`, `CANDIDATE_LIMIT`, `TOP_K`, and `API_URL`
4. Create a virtual environment and install the dependencies.
5. **Data check:** load the HF dataset in a scratch notebook or script, and confirm:
   - the distinct non-numeric `rate` values (`NEW`, `-`, nulls?)
   - whether `approx_cost` contains commas
   - the row count before and after deduplicating on `(name, address)`
   - the distribution of `cost_for_two`, to sanity-check the 500 / 1200 budget thresholds
   - the list of `location` values (expected: 93)
6. Record the findings by updating the **Verify** items in context §3.2 and the thresholds in context §5 if needed.

### Exit Criteria
- [x] `pip install -r requirements.txt` succeeds
- [x] `pytest` runs, with 0 tests and no errors
- [x] The **Verify** items in context.md are confirmed or corrected
- [x] The budget thresholds are confirmed (revised to 300 / 700)

---

## Phase 1: Catalogue, Filter, and API Skeleton

**Goal:** build the backend through the filter step: **API → Filter → Catalogue**, with no LLM yet.

### 1.1 Models (`backend/models.py`)
- `RecommendationRequest`, as in architecture §3.
- `RecommendationItem`, with rank, name, cuisines, rating, cost_for_two, location, and explanation (`str | None`).
- `RecommendationResponse`, with recommendations, summary, candidates_considered, notes, and degraded.

### 1.2 Catalogue (`backend/catalogue.py`), architecture §2.1
1. Write the `parse_rate(str) -> float | None` and `parse_cost(str) -> int | None` helpers.
2. Write the `clean(raw_df) -> DataFrame` steps:
   - select the needed columns and rename them to snake_case
   - parse the rating and cost
   - split `cuisines` and `rest_type` into lowercase lists
   - convert `"null"` strings to real nulls and run `ftfy`
   - deduplicate on `(name, address)`
   - add `id` and `budget_tier`
3. Write `load_catalogue()`. It loads `data/restaurants.parquet` if it exists. Otherwise it downloads the HF dataset, cleans it, and saves the Parquet file.
4. Write the `locations()` and `cuisines()` helpers, which return sorted distinct values.

### 1.3 Filter (`backend/filters.py`), architecture §2.2
1. Write `filter_restaurants(df, req) -> (DataFrame, notes)`, applying the location, cuisine overlap, rating, budget, and keyword-hint filters (delivery and booking).
2. Sort by rating, then votes, and cap at `CANDIDATE_LIMIT` (50 by default; see architecture §2.2).
3. Add relaxation for when fewer than 5 rows match: drop the budget filter, then lower the rating by 0.5. Append a human-readable note for each relaxation.

### 1.4 API (`backend/api.py`), architecture §2.4
1. Create a FastAPI app whose **lifespan** loads the catalogue and fails fast on load errors.
2. Add `GET /health`, which returns `{status, rows}`.
3. Add `GET /options`, which returns `{locations, cuisines}`.
4. Add `POST /recommendations`. It validates the request and returns `400` for an unknown location. It then runs the filter and **temporarily** returns the top 5 filtered rows with `explanation: null`. This placeholder is replaced in Phase 2.

### 1.5 Tests
- **`test_catalogue.py`:** `parse_rate` (`"4.1/5"`, `"4.1 /5"`, `"NEW"`, `"-"`, None), `parse_cost` (`"800"`, `"1,200"`, None), deduplication, and budget tier boundaries (300, 301, 700, 701), all on a small in-memory DataFrame fixture.
- **`test_filters.py`:** each filter on its own, cuisine overlap, the candidate cap, and relaxation order and notes.
- **`test_api.py`:** `/health`, `/options`, an unknown location → 400, an invalid budget → 422, and the happy path returning ≤ 5 items. The catalogue fixture is injected, so there's no HF download.

### Exit Criteria
- [x] `uvicorn backend.api:app` starts. The first run creates `data/restaurants.parquet` (~40 s, 12,450 restaurants), and later starts take 1.1 s.
- [x] `/docs` shows all 3 endpoints
- [x] `curl -X POST /recommendations` with a valid body returns 5 real restaurants (no explanations yet)
- [x] All Phase 1 tests pass (64)

---

## Phase 2: LLM Ranking

**Goal:** add the **LLM** step. The LLM ranks up to `CANDIDATE_LIMIT` candidates, explains its picks, and returns the top 5.

### 2.1 Prompt (`backend/llm.py`), architecture §2.3
1. Write `format_candidates(df) -> str`, which produces one line per row: `id | name | cuisines | rating | votes | cost_for_two | rest_type | online_order | book_table | dish_liked(≤5)`.
2. Write the system prompt. It sets the role, says to choose only from the IDs, return exactly `TOP_K`, ground each explanation, flag preferences that can't be verified, and reply with JSON only. It includes the output schema.
3. Write the user message, which contains the user's preferences, including the free-text `preference`, and then the candidate block.

### 2.2 LLM Call
1. Write `rank_with_llm(req, candidates) -> (picks, summary)`, using the `groq` SDK with `LLM_MODEL`, strict JSON-schema output, a token cap, and a timeout. (Implemented as `GroqRanker`.)
2. Parse the response into a Pydantic `LLMResult`. On a parse or validation failure, retry **once**.
3. **Grounding:** drop IDs that aren't in the candidates, deduplicate, keep the order, and cap at `TOP_K`.

### 2.3 Wire into the API
1. In `POST /recommendations`, replace the Phase 1 placeholder with this sequence: filter, then `rank_with_llm`, then join each pick's facts from the catalogue by `id`, then build the response.
2. If the LLM returns fewer valid picks than `TOP_K`, top up from the pre-sorted candidates with `explanation: null`.
3. **Fallback:** on a timeout, API error, or second parse failure, return the top 5 pre-sorted candidates with `degraded: true` and no explanations.
4. Check at startup: a missing `GROQ_API_KEY` stops startup with a clear message.

### 2.4 Tests (LLM mocked)
- **`test_llm.py`:**
  - `format_candidates` output shape
  - parsing valid JSON
  - an unknown ID dropped
  - a duplicate ID removed
  - invalid JSON triggering a retry
- **`test_api.py`** additions:
  - happy path with a mocked LLM, where facts come from the catalogue, not the LLM
  - LLM exception → `degraded: true`
  - fewer picks than `TOP_K` → topped up

### 2.5 Manual Check (real LLM)
Run 3–5 real requests (different localities, budgets, and cuisines) and check that:
- the picks match the preferences
- the explanations mention real fields
- there are no invented restaurants
- latency and token use are acceptable (measured: 1.7–3.2 s, under 4k tokens per request at 50 candidates). If not, lower `CANDIDATE_LIMIT` or try another model.

### Exit Criteria
- [x] `POST /recommendations` returns 5 ranked items with explanations and a summary (Groq `openai/gpt-oss-120b`, 1.7–3.2 s)
- [x] Forcing an LLM error gives a `degraded: true` response, not a 500 (mocked, plus live with an invalid `LLM_MODEL`). A missing API key stops startup with a clear message (edge_case G1, verified live).
- [x] All tests pass without network access (90)
- [x] The manual check looks sensible (eval.md G1–G5: 100% grounded, injection ignored, unverifiable preferences flagged)

---

## Phase 3: Frontend and Wrap-Up

**Goal:** build the **UI**, which collects input, calls the API, and shows the results, closing the flow.

### 3.1 Streamlit App (`frontend/app.py`), architecture §4
1. Read `API_URL` from the environment, with `http://localhost:8000` as the default.
2. On load, call `GET /options`, cached with `st.cache_data`. If the API is unreachable, show a clear error ("Start the backend first").
3. Build the form:
   - a location selectbox
   - a budget radio (low/medium/high)
   - a cuisine multiselect
   - a min-rating slider (0–5, step 0.5)
   - a preference text input
4. On submit, `POST /recommendations` with a 60 s timeout, showing a spinner while waiting.
5. Render the results:
   - the summary
   - notes, shown as info boxes
   - a degraded warning banner, when relevant
   - 5 cards, each showing the **name, cuisines, ⭐ rating, ₹ cost for two, and AI explanation**
   - an empty-state message when there are no results
6. Add a small note: "Data covers Bangalore only" (context open question 1).

### 3.2 Wrap-Up
1. Write a `README.md` covering:
   - the project summary
   - setup (venv, `pip install`, `.env`)
   - how to run the backend and the frontend (two terminals)
   - how to run the tests
   - the first-run ingestion note (it downloads about 574 MB once)
2. Tick off the definition of done in context §10.
3. Review the docs and update anything that changed during the build (thresholds, limits, model).

### Exit Criteria
- [ ] With the backend and frontend running, the full flow **UI → API → Filter → Catalogue → LLM → UI** works from the browser
- [ ] Error states display cleanly: API down, no results, degraded
- [ ] Following the README from a fresh clone gets the app running
- [ ] Every item in the context §10 definition of done is checked

---

## Requirement Coverage

| Req | Phase |
|---|---|
| R1, R2 Ingestion and fields | 1 (verified in 0) |
| R3 User input | 1 (API model), 3 (form) |
| R4 Filter | 1 |
| R5, R6 Prompt | 2 |
| R7, R8, R9 Rank, explain, summarize | 2 |
| R10 Display | 3 |

## Risks

| Risk | Mitigation | Phase |
|---|---|---|
| Data quality differs from what we assumed | Phase 0 data check before writing any logic | 0 |
| The first HF download is slow or large | Cache to Parquet; tests use fixtures, never the download | 1 |
| Groq free tier: 8k tokens per minute | `CANDIDATE_LIMIT` lowered to 50 (about 3k tokens per request); a 429 waits for `retry-after` (≤ 5 s) and retries once; otherwise degraded | 2 |
| The LLM returns bad JSON or invented IDs | Pydantic validation, one retry, ID allow-list, degraded fallback | 2 |
