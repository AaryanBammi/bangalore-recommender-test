# Restaurant Recommender

An AI-powered restaurant recommendation service inspired by Zomato. You enter a location, budget, cuisines, minimum rating, and any other preferences. The backend filters a real dataset of about 12,000 Bangalore restaurants and asks an LLM (served by Groq) to rank the best matches and explain each pick.

```text
Streamlit UI ──HTTP──▶ FastAPI backend: catalogue ─▶ filter (≤ 50 candidates) ─▶ LLM ─▶ top 5 + explanations
```

- **Data:** [ManikaSaini/zomato-restaurant-recommendation](https://huggingface.co/datasets/ManikaSaini/zomato-restaurant-recommendation) on Hugging Face. It covers **Bangalore only** (93 localities).
- **Docs:** see [`docs/`](docs/) for the problem statement, architecture, implementation plan, edge cases, and evaluation gates.

## Requirements

- Python 3.11+ (developed on 3.12)
- Node.js 24 for the web frontend (`web/`)
- A Groq API key, available from [console.groq.com/keys](https://console.groq.com/keys). The free tier works (see [Limits](#limits)).

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# then edit .env and set GROQ_API_KEY=gsk_...
```

### Configuration (`.env`)

| Variable | Default | Purpose |
|---|---|---|
| `GROQ_API_KEY` | (required) | Groq API key. The backend won't start without it. |
| `LLM_MODEL` | `openai/gpt-oss-120b` | Groq model used for ranking (`openai/gpt-oss-20b` is faster) |
| `LLM_TIMEOUT_S` | `25` | Timeout per LLM attempt; one retry is allowed |
| `CANDIDATE_LIMIT` | `50` | Maximum number of filtered restaurants sent to the LLM |
| `TOP_K` | `5` | Number of recommendations returned |
| `API_URL` | `http://localhost:8000` | Where the frontend finds the backend |
| `BACKEND_API_KEY` | (blank) | If set, `/options` and `/recommendations` require it in an `X-API-Key` header, and `/docs` is hidden. Used in deployment ([docs/deployment.md](docs/deployment.md)); leave blank locally |

## Run

Use two terminals, both in the project folder with the virtual environment activated.

**1. Backend**

```bash
uvicorn backend.api:app --port 8000
```

The **first run** downloads the dataset from Hugging Face, cleans it, and caches it to `data/restaurants.parquet`. It reads only the columns it needs, not the full 574 MB, and takes about 1–3 minutes depending on Hugging Face's download speed. Nothing is served until it finishes. Later starts take about a second. Delete `data/restaurants.parquet` to force a fresh download.

Check that it's up at <http://localhost:8000/health>. API docs are at <http://localhost:8000/docs>.

**2. Frontend**

The deployed frontend is the Next.js app in `web/`. Its `/api/*` route handlers forward requests to the backend, so the browser never calls the backend directly:

```bash
cd web
npm install
cp .env.example .env.local   # BACKEND_URL=http://localhost:8000
npm run dev
```

Then open <http://localhost:3000>.

The original Streamlit UI still works (`streamlit run frontend/app.py`, then <http://localhost:8501>). It will be removed once the Vercel deployment is verified ([docs/deployment.md](docs/deployment.md) §5, step 5).

## API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness check and catalogue size |
| `GET` | `/options` | Valid locations and cuisines |
| `POST` | `/recommendations` | Top 5 recommendations with AI explanations |

```bash
curl -X POST localhost:8000/recommendations -H 'content-type: application/json' \
  -d '{"location": "Indiranagar", "budget": "medium", "cuisines": ["north indian"], "min_rating": 4, "preference": "family-friendly"}'
```

- `budget` is `low` (≤ ₹300 for two), `medium` (₹301–700), or `high` (> ₹700).
- If too few restaurants match, the filters are relaxed in order (keyword hints, then budget, then rating down to 3.0), and the response `notes` say what changed.
- If the LLM is unavailable, the response still returns the top-rated matches, with `"degraded": true` and no explanations.

## Tests

```bash
pytest
```

All tests run offline. They use a small fake catalogue and a mocked LLM, so they need no network access and no API key. The suite covers data cleaning, filtering, the API, the LLM integration, and the Streamlit UI (through `streamlit.testing`).

The web frontend has its own offline suite (Vitest and React Testing Library, with `fetch` mocked). It covers the UI states and the proxy route handlers:

```bash
cd web
npm test
npm run typecheck
```

## Limits

- **Groq free tier:** 8,000 tokens per minute. Each request uses about 1–4k tokens, so expect about 2–3 recommendations per minute. Beyond that, responses fall back to `degraded` (top-rated matches without AI explanations). On a paid tier you can raise `CANDIDATE_LIMIT`.
- **Bangalore only:** other cities return `400 Unknown location`.

## Project Layout

```text
backend/    api.py (FastAPI) · catalogue.py (ingestion) · filters.py · llm.py (Groq) · models.py
web/        Next.js frontend deployed to Vercel (app/, components/, lib/, __tests__/)
frontend/   app.py (original Streamlit UI; talks to the backend over HTTP only)
tests/      pytest suite (offline)
scripts/    data_check.py (Phase 0 dataset verification)
docs/       problem statement, context, architecture, plan, edge cases, eval, deployment
```
