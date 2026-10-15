# Project Context: AI-Powered Restaurant Recommendation System

> Source of truth for requirements: [problem_statement.txt](problem_statement.txt).
> This document adds the facts, constraints, and decisions needed to build the project. Items marked **Decision** are proposed defaults that can be changed. Items marked **Verify** still need confirming against the actual data.

---

## 1. Goal in One Paragraph

Build a Zomato-inspired service. A user enters preferences (location, budget, cuisine, minimum rating, and free-text extras). The system filters a real restaurant dataset down to a small candidate set and passes those candidates to an LLM. The LLM ranks them, explains why each one fits, and optionally summarizes the choices. The UI shows the top results with name, cuisine, rating, estimated cost, and the AI explanation.

---

## 2. Requirements Checklist (from the problem statement)

| # | Area | Requirement |
|---|------|-------------|
| R1 | Data ingestion | Load and preprocess the Hugging Face Zomato dataset |
| R2 | Data ingestion | Extract name, location, cuisine, cost, rating, etc. |
| R3 | User input | Collect location, budget (low/medium/high), cuisine, minimum rating, and additional preferences |
| R4 | Integration | Filter data based on user input |
| R5 | Integration | Pass structured results into an LLM prompt |
| R6 | Integration | Design a prompt that helps the LLM reason and rank |
| R7 | Recommendation | The LLM ranks restaurants |
| R8 | Recommendation | The LLM explains why each recommendation fits |
| R9 | Recommendation | (Optional) The LLM summarizes the choices |
| R10 | Output | Show the top recommendations with name, cuisine, rating, estimated cost, and AI explanation |

---

## 3. Dataset

**Source:** [`ManikaSaini/zomato-restaurant-recommendation`](https://huggingface.co/datasets/ManikaSaini/zomato-restaurant-recommendation) on Hugging Face

| Property | Value |
|---|---|
| Rows | ~51,717 |
| Format | CSV (an auto-converted Parquet version is also available) |
| Size | ~574 MB, mostly from the `reviews_list` and `menu_item` columns |
| Splits | One: `train` |
| Geography | **Bangalore only.** It has 93 `location` localities and 30 `listed_in(city)` zones |

### 3.1 Columns

| Column | Type | Example | Use in this project |
|---|---|---|---|
| `name` | str | `Jalsa` | **Output.** Restaurant name |
| `location` | str | `Banashankari` | **Filter.** User's location |
| `listed_in(city)` | str | `Banashankari` | Alternative or broader location zone |
| `cuisines` | str, comma-separated | `North Indian, Mughlai, Chinese` | **Filter and output** |
| `rate` | str | `4.1/5` | **Filter and output.** Needs parsing |
| `votes` | int | `775` | Ranking signal and tie-breaker |
| `approx_cost(for two people)` | str | `800` | **Filter and output.** Needs parsing |
| `rest_type` | str | `Casual Dining` | Context for extra preferences |
| `listed_in(type)` | str | `Buffet`, `Cafes`, `Delivery` | Context for extra preferences |
| `online_order` | Yes/No | `Yes` | Context (e.g., "delivery") |
| `book_table` | Yes/No | `Yes` | Context (e.g., "reservations") |
| `dish_liked` | str, nullable | `Pasta, Lunch Buffet` | LLM context for explanations |
| `reviews_list` | str (stringified list of tuples) | `[('Rated 4.0', 'RATED\n ...')]` | Optional: a short review snippet for the LLM |
| `address` | str | `942, 21st Main Road, ...` | Optional output |
| `url`, `phone`, `menu_item` | str | | Not needed. Drop them |

### 3.2 Known Data Quality Issues

- **Bangalore only.** The problem statement uses "Delhi" as an example, but the dataset has no Delhi data. "Location" therefore means a **Bangalore locality**. The UI should offer only the localities that exist in the data. An unknown city should get a clear "no data for this city" message.
> **Verified in Phase 0** with `scripts/data_check.py` on 2026-10-15. The figures below are measured.

- **`rate`** is a string like `"4.1/5"`. ✅ **Verified:** 7,775 nulls, 2,208 `"NEW"`, 69 `"-"`, and 20,377 values with a space (`"3.8 /5"`). Parsed ratings range from **1.8 to 4.9** (no 5.0 exists). Treat anything that isn't numeric as unrated (None).
- **`approx_cost`** is a string. ✅ **Verified:** 6,917 values have commas (`"1,200"`), and there are 346 nulls and no zeros. Strip the commas and cast to int.
- **Duplicates.** ✅ **Verified:** deduplicating on `(name, address)` takes **51,717 rows down to 12,499** (12,495 with a normalized address). In **5,257** duplicate groups the rows have differing `rate` values, so keep the row with the highest `votes`.
- **Nulls.** ✅ **Verified:** there are **no** literal `"null"` strings; the dataset viewer was showing real nulls. Null counts: `dish_liked` 28,078 (54%), `rest_type` 227, `cuisines` 45, `location` 21. Drop rows with no location.
- **Mojibake.** ✅ **Verified:** 269 names have multi-layer mojibake. `ftfy.fix_text` repairs all of them (e.g., `Café Down The Alley`).
- **Locations.** ✅ **Verified:** 93 `location` values and 30 `listed_in(city)` values. 22 localities have fewer than 20 restaurants, so relaxation matters for them. There are 107 distinct cuisines.
- **`listed_in(city)` ≠ physical location.** It is the zone the listing appeared under. Prefer `location` for filtering.
- **Size.** Drop `reviews_list` and `menu_item` early (or never load them) so memory use stays low.

---

## 4. Preprocessing Pipeline (R1, R2)

This runs in the backend at API startup. The first run saves a clean, compact artifact (`data/restaurants.parquet`), and later runs just load it.

1. Load the dataset with `datasets.load_dataset(...)` or download the Parquet file. Select only the needed columns.
2. Rename the columns to snake_case: `approx_cost(for two people)` → `cost_for_two`, `listed_in(type)` → `listing_type`, `listed_in(city)` → `zone`.
3. Parse `rate` → `rating: float | None` and `cost_for_two` → `int | None`.
4. Split `cuisines` into a lowercased, trimmed `list[str]`.
5. Normalize the `"null"` strings, fix the encoding, and trim whitespace.
6. Deduplicate restaurants and aggregate `listing_type` into a list.
7. Derive `budget_tier` from `cost_for_two` (see §5).
8. (Optional) Extract 1–2 short review snippets per restaurant for LLM context, capped at about 200 characters each.
9. Save the artifact. Also save lookup lists (distinct locations and cuisines) to populate UI dropdowns.

---

## 5. User Input Model (R3)

```text
location:          str          # Bangalore locality, chosen from known values
budget:            "low" | "medium" | "high"
cuisine:           str | list[str]   # chosen from known cuisines
min_rating:        float        # 0.0–5.0, e.g. 3.5
extra_preferences: str          # free text: "family-friendly, quick service"
```

**Decision: budget tiers** (cost for two, INR). These were revised in Phase 0 from the measured distribution. With the original 500 / 1,200 thresholds, the split was 72% / 23% / **4.6%**, which leaves the "high" tier nearly empty. The median cost is ₹400, and the 90th percentile is ₹850.

| Tier | Range | Share of restaurants |
|---|---|---|
| low | ≤ ₹300 | ~41% |
| medium | ₹301 – ₹700 | ~44% |
| high | > ₹700 | ~15% |

**Extra preferences** are free text, and the dataset has no "family-friendly" column. They are handled in two ways:
- Cheap keyword hints map to structured fields where possible (e.g., "delivery" → `online_order == Yes`, "reservation" → `book_table == Yes`, "cafe" or "buffet" → `rest_type`/`listing_type`).
- Everything else goes to the LLM, which reasons over `rest_type`, `dish_liked`, and the review snippets.

---

## 6. Architecture

The full design is in [architecture.md](architecture.md). The flow is **UI → API → Filter → Catalogue → LLM → UI**:

```text
Frontend (Streamlit) ──POST /recommendations──▶ Backend (FastAPI)
                                                  Ingestion/Catalogue (~52k) ─▶ Filter (300–400) ─▶ LLM (top 5)
Frontend ◀──────────── top 5 + explanations ──────────────────────────────────────────────────────┘
```

### 6.1 Filter Layer (R4)
- Hard filters: `location`, `cuisine` (any overlap), `rating >= min_rating`, `budget_tier`.
- Pre-rank by `rating` and then `votes`. Keep the **top 50 candidates** (set by `CANDIDATE_LIMIT`; lowered from the diagram's 300–400 to fit Groq's free-tier limit of 8k tokens per minute), and send them to the LLM in a compact one-line-per-row format.
- **Fallbacks when there are zero or very few results:** relax the constraints in a fixed order (budget, then rating, then cuisine, then a nearby zone). Tell the user what was relaxed.

### 6.2 Prompt Design (R5, R6)
- **System prompt:** the role (local food expert), the rules (recommend **only** from the provided candidates, never invent restaurants or facts, cite concrete fields in explanations), and the output schema.
- **User message:** the user's preferences plus the candidates as compact JSON (id, name, cuisines, rating, votes, cost_for_two, rest_type, dish_liked, online_order, book_table, and an optional review snippet).
- **Output:** strict JSON. Validate it with Pydantic, and retry once if parsing fails.

```json
{
  "recommendations": [
    { "id": "r_123", "rank": 1, "explanation": "Why this fits the user's preferences..." }
  ],
  "summary": "Optional 2–3 sentence overview of the choices."
}
```

- Join the LLM output back to the dataset **by `id`**, so displayed facts (rating, cost, cuisine) always come from the data, not from the LLM. This prevents hallucinated numbers.
- Return the **top 5** by default.

### 6.3 Output Display (R10)
For each recommendation, show the **name, cuisine(s), rating, estimated cost for two (₹), and the AI explanation**. Optionally add the locality, restaurant type, and online order / table booking badges. Show the summary above the list, plus any relaxed-filter notice.

---

## 7. Tech Stack

**Decision.** These are proposed defaults. The problem statement doesn't mandate a stack.

| Layer | Choice | Notes |
|---|---|---|
| Language | Python 3.11+ | Best fit for the HF `datasets` library and pandas |
| Data | `datasets`, `pandas`, `pyarrow`, `ftfy` | |
| LLM | Groq via the `groq` SDK (default `openai/gpt-oss-120b`; `openai/gpt-oss-20b` for lower latency) | Strict JSON-schema structured output |
| Validation | `pydantic` | API request/response and LLM output schema |
| API | FastAPI + uvicorn | All frontend ↔ backend traffic goes through the API |
| UI | Streamlit | API client only (`httpx`) |
| Config | `.env` with `GROQ_API_KEY` (never committed) | `python-dotenv` |
| Tests | `pytest` | Parsing, filtering, prompt building, and output validation with a mocked LLM |

### 7.1 Layout

See [architecture.md §7](architecture.md#7-project-layout). The backend lives in `backend/` (api, catalogue, filters, llm, models) and the frontend in `frontend/app.py`. Ingestion runs at API startup and caches its output to `data/restaurants.parquet`, so the separate preprocessing script is no longer needed.

---

## 8. Non-Functional Considerations

- **Grounding:** the LLM may only rank or explain the given candidates. Drop any `id` that isn't in the candidate set.
- **Latency and cost:** limit the candidate count and fields, use a short review snippet, and cache responses keyed on normalized preferences.
- **Robustness:** handle empty results, LLM timeouts, and malformed JSON. If the LLM fails, show the pre-ranked list without explanations.
- **Secrets:** keep the API key in the environment only, and add `.env` and `data/` to `.gitignore`.

---

## 9. Open Questions

1. Should the UI explicitly say the data covers Bangalore only, or should "city" be dropped in favor of "locality"?
2. ~~Are the budget thresholds acceptable?~~ **Resolved in Phase 0:** they were revised to 300 / 700 (§5).
3. ~~Is a separate API needed?~~ **Resolved:** yes. FastAPI backend, with Streamlit as the API client.
4. Is the Groq free tier enough? It allows 8k tokens per minute, so about 2–3 requests per minute at 50 candidates. A paid tier would allow the full 300–400 candidates.
5. Should review snippets be included? They improve the explanations but add tokens and preprocessing work.

---

## 10. Definition of Done

- [x] Backend ingestion builds a clean catalogue from the HF dataset
- [x] The FastAPI backend exposes `/options` and `/recommendations`
- [x] The UI collects all five preference inputs and talks to the backend only through the API
- [x] Filtering, with fallbacks, produces a bounded candidate set
- [x] The LLM returns a ranked, explained, schema-valid JSON list (plus an optional summary)
- [x] The UI shows the top recommendations with name, cuisine, rating, cost, and explanation
- [x] Tests cover parsing, filtering, prompt building, and LLM output handling (mocked)
- [x] The README has setup and run instructions
