# Architecture: AI-Powered Restaurant Recommendation System

> **Inputs:** [problem_statement.txt](problem_statement.txt) (requirements) and [context.md](context.md) (dataset facts and decisions).
> **Scope:** a lean test project. There is no database, cache, queue, or scaling work. The frontend talks to the backend **only through the API**.

---

## 1. Overview

```text
┌──────────────────┐        HTTP (JSON)        ┌───────────────────────────────────────────────────────┐
│  FRONTEND        │  POST /recommendations    │  BACKEND (FastAPI)                                    │
│  (Streamlit)     │ ────────────────────────▶ │                                                       │
│                  │                           │  ┌────────────┐   ┌────────────┐   ┌───────────────┐  │
│  Input           │                           │  │ Ingestion  │──▶│  Filter    │──▶│     LLM       │  │
│  - Location      │                           │  │ (~52k rows)│   │ (300–400   │   │  (rank +      │  │
│  - Budget        │                           │  │ at startup │   │ candidates)│   │   explain →   │  │
│  - Cuisine       │                           │  └────────────┘   └────────────┘   │   top 5)      │  │
│  - Rating        │   top 5 + explanations    │                                    └───────┬───────┘  │
│  - Preference    │ ◀──────────────────────────────────────────────────────────────────────┘          │
└──────────────────┘                           └───────────────────────────────────────────────────────┘
```

This follows the reference flow **UI → API → Filter → Catalogue → LLM → UI**:

| Flow step | Component |
|---|---|
| UI (input) | `frontend/app.py`, the Streamlit form |
| API | `backend/api.py`, FastAPI |
| Catalogue | `backend/catalogue.py`, the cleaned dataset held in memory (built by ingestion) |
| Filter | `backend/filters.py`, which narrows the catalogue from about 52k raw rows to 300–400 candidates |
| LLM | `backend/llm.py`, which ranks and explains the candidates and returns the top 5 |
| UI (output) | `frontend/app.py`, the result cards |

**Two processes, run separately:**

```bash
uvicorn backend.api:app --port 8000      # backend
streamlit run frontend/app.py            # frontend (calls http://localhost:8000)
```

---

## 2. Backend Components

### 2.1 Ingestion → Catalogue (`backend/catalogue.py`)

This implements context §4. It runs **once at API startup** (FastAPI lifespan), and the cleaned result stays in memory.

```text
first run:  HF dataset (~52k rows) ─▶ clean ─▶ save data/restaurants.parquet ─▶ load into memory
next runs:  data/restaurants.parquet exists ─▶ load into memory (fast)
```

The cleaning steps are:
- Keep only the needed columns and drop `reviews_list`, `menu_item`, `url`, and `phone`.
- Parse `rate` (`"4.1/5"` → `4.1`; `NEW` or `-` → None) and the cost (`"1,200"` → `1200`).
- Split `cuisines` and `rest_type` into lowercase lists, convert the `"null"` strings to real nulls, and fix encoding with `ftfy`.
- Deduplicate on `(name, address)`.
- Add `id` (a short hash of name and address) and `budget_tier` (≤ 300 / ≤ 700 / above, per context §5).

The module exposes:
- `catalogue.df`, a pandas DataFrame
- `catalogue.locations()` and `catalogue.cuisines()`, which feed the UI dropdowns

Delete `data/restaurants.parquet` to force a re-ingest.

### 2.2 Filter (`backend/filters.py`)

A pure function, `filter_restaurants(df, prefs) -> DataFrame`, applies these filters with pandas boolean masks:

| Filter | Rule |
|---|---|
| Location | `location == prefs.location` |
| Cuisine | Any overlap with `prefs.cuisines` (skipped if empty) |
| Rating | `rating >= prefs.min_rating` |
| Budget | `budget_tier == prefs.budget` |
| Keyword hints from `preference` | `"delivery"` → `online_order`, `"book"`/`"reservation"` → `book_table` |

- **Sort:** `rating` descending, then `votes` descending.
- **Cap:** keep at most `CANDIDATE_LIMIT`, which defaults to **50**. The diagram asked for 300–400, but Groq's free tier allows 8,000 tokens per minute, and each candidate costs about 47 tokens (202 candidates came to 10.5k tokens and were rejected with HTTP 413). Raise the cap on a paid Groq tier.
- **Relaxation:** if fewer than 5 rows match, drop the budget filter, then lower the rating by 0.5. Each relaxation is reported in the response's `notes`.

### 2.3 LLM (`backend/llm.py`)

The LLM picks the top 5 from the candidates and explains each pick.

- **Model:** an LLM served by **Groq** through the `groq` SDK (`client.chat.completions.create`), with the model set by `LLM_MODEL`. The default is `openai/gpt-oss-120b`, a Groq production model with a 131k-token context and support for strict structured output; `openai/gpt-oss-20b` is faster. The call uses `reasoning_effort="low"` and `include_reasoning=False` to keep latency down.
- **Structured output:** `response_format` is a strict `json_schema` (every field required, no extra keys; `summary` is `string | null`), and the response is still validated with Pydantic (`LLMResult`). Groq returns a 400 when output fails schema validation, so a 400 is retried once like a timeout. 401 and 404 (bad key, unknown model) are not retried.
- **Compact candidate format:** one line per restaurant keeps the prompt small (about 47 tokens per row, so 50 rows ≈ 3k tokens):

  ```text
  id | name | cuisines | rating | votes | cost_for_two | rest_type | online_order | book_table | dish_liked(≤5)
  ```

- **System prompt:**
  - Act as a local food expert.
  - Choose **only** from the given IDs.
  - Return exactly 5 picks, or fewer if there are fewer candidates.
  - Ground each explanation in the data and the user's preferences.
  - When a preference can't be verified from the data, say so honestly.
  - Reply with JSON only.
- **Expected output:**

  ```json
  {
    "recommendations": [
      { "id": "r_ab12cd34ef", "explanation": "Why this fits the user..." }
    ],
    "summary": "2–3 sentence overview."
  }
  ```

- **Post-processing:**
  1. Validate the output with Pydantic.
  2. **Drop unknown IDs.**
  3. Join each ID back to the catalogue, so the rating, cost, and cuisine always come from the data and never from the LLM.
- **Failure:** on a timeout, an API error, or bad JSON after one retry, return the top 5 pre-sorted candidates with `explanation: null` and `degraded: true`.

### 2.4 API (`backend/api.py`)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness, plus catalogue row count |
| `GET` | `/options` | `{locations: [...], cuisines: [...]}` for the UI dropdowns |
| `POST` | `/recommendations` | Main flow: filter, then LLM, then top 5 |

Each endpoint is a thin wrapper that calls `filters` and `llm`. FastAPI generates OpenAPI docs at `/docs` automatically.

---

## 3. API Contract (`backend/models.py`)

### Request: `POST /recommendations`

```json
{
  "location": "Indiranagar",
  "budget": "medium",
  "cuisines": ["italian", "chinese"],
  "min_rating": 4.0,
  "preference": "family-friendly, quick service"
}
```

```python
class RecommendationRequest(BaseModel):
    location: str
    budget: Literal["low", "medium", "high"]
    cuisines: list[str] = []
    min_rating: float = Field(0, ge=0, le=5)
    preference: str = Field("", max_length=300)
```

### Response: `200 OK`

```json
{
  "recommendations": [
    {
      "rank": 1,
      "name": "Toscano",
      "cuisines": ["italian", "salad"],
      "rating": 4.4,
      "cost_for_two": 1000,
      "location": "Indiranagar",
      "explanation": "Highly rated Italian spot within your medium budget..."
    }
  ],
  "summary": "Mostly Italian picks in Indiranagar under ₹1,200...",
  "candidates_considered": 312,
  "notes": [],
  "degraded": false
}
```

### Errors

| Case | Response |
|---|---|
| Invalid body (e.g., bad budget) | `422`, with FastAPI's validation detail |
| Unknown location | `400` `{"detail": "Unknown location. See /options."}` |
| No matches, even after relaxation | `200` with `recommendations: []` and a note |
| LLM failure | `200` with `degraded: true` and null explanations |
| Missing `GROQ_API_KEY` | API fails at startup with a clear message |

---

## 4. Frontend (`frontend/app.py`)

1. On load, call `GET /options` to populate the location and cuisine dropdowns.
2. The form has:
   - a location select
   - a budget radio
   - a cuisine multiselect
   - a min-rating slider (0–5, step 0.5)
   - a preference text box
3. On submit, call `POST /recommendations` with `httpx`/`requests` and a timeout of about 60 s, showing a spinner while waiting.
4. Render the result:
   - the summary
   - any notes or degraded banner
   - 5 cards, each showing the **name, cuisines, ⭐ rating, ₹ cost for two, and AI explanation**

The frontend has **no data or LLM logic**. It only knows the API URL (`API_URL` env var, default `http://localhost:8000`).

---

## 5. Request Sequence

```text
Frontend            API                 Filter              Catalogue            LLM
   │ POST /recs      │                     │                    │                   │
   │────────────────▶│ validate (Pydantic) │                    │                   │
   │                 │────────────────────▶│ query df           │                   │
   │                 │                     │───────────────────▶│                   │
   │                 │                     │◀── 300–400 rows ───│                   │
   │                 │◀── candidates ──────│                    │                   │
   │                 │ build prompt ───────────────────────────────────────────────▶│
   │                 │◀───────────────────────────────── top 5 ids + explanations ──│
   │                 │ validate ids, join facts from catalogue                      │
   │◀── top 5 JSON ──│                                                              │
   │ render cards    │                                                              │
```

---

## 6. Configuration

Settings come from `.env`, loaded with `python-dotenv`:

| Variable | Default | Used by |
|---|---|---|
| `GROQ_API_KEY` | (required) | backend |
| `LLM_MODEL` | `openai/gpt-oss-120b` | backend |
| `LLM_TIMEOUT_S` | `25` | backend |
| `CANDIDATE_LIMIT` | `50` | backend |
| `TOP_K` | `5` | backend |
| `API_URL` | `http://localhost:8000` | frontend |

`.env` and `data/` are git-ignored, and `.env.example` is committed.

---

## 7. Project Layout

```text
nextleap1/
├── docs/
│   ├── problem_statement.txt
│   ├── context.md
│   └── architecture.md
├── backend/
│   ├── api.py            # FastAPI app + endpoints
│   ├── catalogue.py      # ingestion + in-memory catalogue
│   ├── filters.py        # filter + relaxation
│   ├── llm.py            # prompt, Groq call, validate + join
│   └── models.py         # request/response Pydantic models
├── frontend/
│   └── app.py            # Streamlit UI (API client only)
├── data/                 # git-ignored; restaurants.parquet
├── tests/
│   ├── test_catalogue.py # rate/cost parsing, dedupe
│   ├── test_filters.py   # filters + relaxation
│   └── test_api.py       # endpoints with LLM mocked
├── requirements.txt      # fastapi, uvicorn, pandas, pyarrow, datasets, ftfy,
│                         # groq, pydantic, python-dotenv, streamlit, httpx, pytest
├── .env.example
└── README.md
```

---

## 8. Testing

These tests are the minimum:
- **`test_catalogue`:** rate and cost parsing edge cases (`NEW`, `-`, `"1,200"`) and deduplication.
- **`test_filters`:** each filter, the candidate cap, and the relaxation notes.
- **`test_api`:** `/options`, plus `/recommendations` with `llm` monkeypatched. Covers the happy path, an unknown ID dropped, and an LLM failure → `degraded: true`.

No test calls the real LLM.

---

## 9. Requirement Traceability

| Req (context §2) | Where |
|---|---|
| R1, R2 Ingestion and fields | `backend/catalogue.py` |
| R3 User input | `frontend/app.py`, `RecommendationRequest` |
| R4 Filter | `backend/filters.py` |
| R5, R6 Prompt | `backend/llm.py` |
| R7, R8, R9 Rank, explain, summarize | `backend/llm.py` |
| R10 Display | `frontend/app.py` |
