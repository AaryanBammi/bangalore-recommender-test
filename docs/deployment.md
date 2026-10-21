# Deployment Plan

> **Based on:** [architecture.md](architecture.md) and the [README](../README.md). Edge case IDs refer to [edge_case.md](edge_case.md).
> **Scope:** a public demo deployment. There is no custom domain, autoscaling, or monitoring stack. The frontend still talks to the backend **only through the API**.

---

## 1. Target Setup

```text
Browser ──▶ Vercel (Next.js, web/) ──HTTPS + X-API-Key──▶ Railway (FastAPI, backend.api:app) ──▶ Groq API
            pages + /api/* route handlers                 secrets: GROQ_API_KEY, BACKEND_API_KEY
            secrets: BACKEND_URL, BACKEND_API_KEY         data/restaurants.parquet (committed)
```

| Part | Host | Notes |
|---|---|---|
| Frontend | **Vercel** | A new Next.js app in `web/` replaces the Streamlit UI (§3). Vercel runs only static files and short serverless functions, so it can't host Streamlit, which needs a long-running server with a WebSocket per browser |
| Backend | **Railway** | Runs the existing FastAPI app unchanged apart from an API-key check (§4). Always on by default; no sleep |
| LLM | Groq (existing key) | No change |

**Why the frontend proxies through Vercel route handlers:** the browser calls `/api/options` and `/api/recommendations` on the Vercel domain, and those handlers call Railway on the server side. This means:
- The backend URL and its API key never reach the browser.
- No CORS setup is needed on the backend.
- The backend can reject anyone who isn't the frontend, which protects the Groq quota (D3).

---

## 2. Known Constraints

| # | Constraint | Impact | Handling |
|---|---|---|---|
| D1 | Railway's container disk is **ephemeral** (no volume attached) | Without the parquet in the repo, every deploy rebuilds the catalogue from Hugging Face. The first-run download took **193 s** in Gate 3 | **Commit the parquet** (845 KB), so startup is ~1 s. Done on the `deploy-prep` branch |
| D2 | Railway isn't free past the trial | The trial gives a one-time credit, then the Hobby plan is a monthly fee that includes some usage. One small always-on service should fit within it. Check current pricing at railway.com/pricing | Leave Railway's optional "serverless" sleep setting **off**, so there are no cold starts |
| D3 | A public backend with no auth | Anyone with the URL could spend the Groq quota | `BACKEND_API_KEY` shared secret, sent only by the Vercel route handlers (§4) |
| D4 | Groq free tier: 8k tokens/min | ~2–3 recommendations per minute across **all** users; beyond that, responses are `degraded` | Acceptable for a demo. The UI already explains degraded results |
| D5 | Vercel function duration limit | A slow Groq call plus one retry can take up to ~55 s | Set `maxDuration = 60` on the recommendations route handler (within the Hobby limit) |
| D6 | The Streamlit UI and its 13 UI tests go away | Look, behaviour, and test coverage must be rebuilt, not just redeployed | Feature list and test list in §3. Keep `frontend/` until the new UI passes them |

---

## 3. Frontend Rebuild (`web/`)

**Status: built.** `npm test` passes 23 tests (15 UI, 8 route handler), and `npm run typecheck` and `next build` are clean. A local run against the real backend, with `BACKEND_API_KEY` set on both sides, checked the following:
- The proxy returns real results with explanations.
- A 400 from the backend passes through to the UI with its message.
- A key mismatch reaches the browser as a 502, so the API key is never mentioned.
- Neither the key nor the backend URL appears in `.next/static`.
- There's no horizontal scroll at 390 px or 1280 px.

**Stack:** Next.js 16 (App Router, TypeScript), plain CSS, Nunito through `next/font/google`. Tests: Vitest + React Testing Library. No UI kit is used; the CSS from `frontend/app.py` was ported almost directly.

**Proxy behaviour** (`web/lib/backend.ts`):
- Adds `X-API-Key` to each forwarded request.
- Passes 2xx and 4xx responses through unchanged.
- Turns an unreachable backend, a missing `BACKEND_URL`, or a backend 401 into 502, and a timeout into 504.
- Options get a 10 s timeout and a 300 s CDN cache on success. Recommendations get a 57 s timeout, which is under `maxDuration = 60`.

```text
web/
  app/
    layout.tsx                    # fonts, theme tokens, page metadata ("Restaurant Recommender", 🍽️)
    page.tsx                      # header, search panel, results / states
    globals.css                   # tokens from .streamlit/config.toml + rr-* styles from app.py
    api/options/route.ts          # GET  → BACKEND_URL/options        (cache 300 s)
    api/recommendations/route.ts  # POST → BACKEND_URL/recommendations (maxDuration 60)
  components/                     # SearchPanel, ResultCard, Skeleton, EmptyState, BackendDown
  lib/api.ts                      # client fetch helpers + error-message mapping
  __tests__/
```

### 3.1 Features to carry over

Every item here exists in `frontend/app.py` today.

| Area | Behaviour |
|---|---|
| Header | Logo, "Restaurant Recommender", "Bangalore" badge, hero heading and subtext |
| Location | Dropdown filled from `/options`, defaulting to Indiranagar |
| Budget | Segmented control: Under ₹300 / ₹300–700 / ₹700+, default medium |
| Cuisines | 10 popular cuisines as toggle chips, plus a searchable "More cuisines" list for the rest. All shown title-cased; sent lowercase |
| Rating | Segmented control: Any / 3.5+ / 4.0+ / 4.5+, default 3.5 |
| Preference | Optional text box, max 300 characters |
| Loading | Five pulsing skeleton cards and "Picking your top 5…". The pulse is disabled under `prefers-reduced-motion` |
| Results | "Your top N in {location}", the LLM summary, then cards showing rank, name, location, cuisine tags, rating (or "Unrated"), ₹ level and cost (or "Cost N/A"), and "Why we picked this" |
| Degraded | A warning banner, with explanations hidden |
| Notes | Each relaxation note shown as an info banner |
| No matches | The "No matches this time" state, with the notes |
| First visit | The "Your table is waiting" empty state |
| Backend down | "We can't reach the kitchen right now" with a Try again button. Don't show the backend URL any more, since it's now a server secret |
| Errors | 4xx → the backend's `detail`, with 422 validation lists made readable. 5xx → a generic message. Timeout → "The request timed out" |
| Footer | "Ranked from N matching restaurants" and "Data covers Bangalore only." |
| Layout | Max width 1120 px, card grid `minmax(300px, 1fr)`, 16 px gutters under 640 px |

### 3.2 Tests to port

Recreate the 13 cases in `tests/test_frontend.py` as Vitest tests:
- Form filled from options
- Selected cuisines sent
- Payload sent and cards rendered
- Null rating and cost shown as text
- Degraded banner shown and explanations hidden
- Notes shown
- Empty state
- Backend down on load
- Backend down on submit
- Timeout
- 400 detail shown
- 422 detail made readable
- 500 generic message

Add route handler tests:
- Forwards `X-API-Key`
- Passes 4xx bodies through
- Returns 502 when the backend is unreachable
- Returns 504 on timeout

### 3.3 Vercel project settings

- **Root directory:** `web` · **Framework preset:** Next.js (auto-detected) · **Node:** 24.x (from `engines` in `web/package.json`)
- **Environment variables** (Production and Preview), **server-only**, so **no `NEXT_PUBLIC_` prefix:**
  - `BACKEND_URL`: the Railway URL
  - `BACKEND_API_KEY`: the same value as on Railway
- **Local dev:** put the same variables in `web/.env.local`, with `BACKEND_URL=http://localhost:8000`. Add `.env.local` to `.gitignore`.

---

## 4. Backend Changes (for Railway)

Already done on the `deploy-prep` branch:
1. `data/restaurants.parquet` is committed (`.gitignore` now ignores `data/*` except that file).
2. `requirements.txt` is pinned to the versions that passed Gates 0–3.
3. `.python-version` is set to `3.12`, which Railway's builder reads.
4. `railway.json` sets the start command and health check:
   ```json
   {
     "$schema": "https://railway.com/railway.schema.json",
     "deploy": {
       "startCommand": "uvicorn backend.api:app --host 0.0.0.0 --port $PORT",
       "healthcheckPath": "/health",
       "restartPolicyType": "ON_FAILURE"
     }
   }
   ```

Also done:

5. **API-key check (D3).** If the `BACKEND_API_KEY` env var is set, `/options` and `/recommendations` reject requests without a matching `X-API-Key` header (401). `/health` stays open for Railway's health check. If the variable is unset (local dev and tests), nothing changes. Use `secrets.compare_digest` for the comparison. Tests cover a missing key, a wrong key, a non-ASCII key, the right key, and the key being unset. The Streamlit UI also sends the key when it's set, so local dev keeps working.
6. **Hide the API docs in production:** `/docs`, `/redoc`, and `/openapi.json` return 404 when `BACKEND_API_KEY` is set.
7. `BACKEND_API_KEY` is in `.env.example` (blank) and the README config table.

No CORS change is needed, because the browser never calls Railway directly.

---

## 5. Rollout Steps

### Step 0: Push to GitHub

The repo has no remote yet. Create a GitHub repository (public or private), then:

```bash
git remote add origin git@github.com:<user>/<repo>.git
git push -u origin main
```

### Step 1: Deploy the backend (Railway)

1. Railway → **New Project → Deploy from GitHub repo** → pick the repo, branch `main`. Railway picks up `railway.json` and builds from `requirements.txt`.
2. **Variables:**
   - `GROQ_API_KEY`
   - `BACKEND_API_KEY`: generate one with `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`
   - Optionally `LLM_MODEL`, `LLM_TIMEOUT_S`, `CANDIDATE_LIMIT`, `TOP_K`
3. **Settings → Networking → Generate Domain** to get a public URL, e.g. `https://restaurant-recommender-production.up.railway.app`.
4. In the deploy logs, expect `Catalogue loaded: 12450 restaurants` within seconds. A Hugging Face download in the logs means the parquet isn't committed (D1).

### Step 2: Verify the backend

```bash
BASE=https://<your-service>.up.railway.app
KEY=<BACKEND_API_KEY>
curl -s $BASE/health                                         # {"status":"ok","rows":12450}
curl -s -o /dev/null -w '%{http_code}\n' $BASE/options       # 401 (no key)
curl -s -H "X-API-Key: $KEY" $BASE/options | head -c 300     # locations + cuisines
curl -s -X POST $BASE/recommendations -H "X-API-Key: $KEY" -H 'content-type: application/json' \
  -d '{"location": "Indiranagar", "budget": "medium", "cuisines": ["north indian"], "min_rating": 4, "preference": "family-friendly"}'
```

Pass if the last call returns 5 recommendations with explanations and `"degraded": false`.

### Step 3: Deploy the frontend (Vercel)

1. Vercel → **Add New → Project** → import the repo. Set **Root Directory** to `web`.
2. Add `BACKEND_URL` and `BACKEND_API_KEY` (§3.3).
3. Deploy. Every push to `main` deploys to production, and every other branch or PR gets a preview URL. Previews call the same Railway backend, so they share its Groq quota.

### Step 4: Verify end to end

Run these against the Vercel URL, in a private browser window:

| # | Check | Pass if |
|---|---|---|
| V1 | Page loads | Warm theme and Nunito font appear; location and cuisine lists are filled |
| V2 | Happy path | Indiranagar · medium · north indian · 4.0 returns 5 cards with explanations |
| V3 | Relaxed filters | A narrow query (e.g. low budget + 4.5 rating) shows notes about what was relaxed |
| V4 | No matches | Shows the "No matches this time" state, not an error |
| V5 | Backend down | Temporarily remove `BACKEND_URL` or stop the Railway service: the page shows the "can't reach the kitchen" state |
| V6 | Degraded mode | Fire 5+ requests within a minute; later ones show results without explanations rather than failing |
| V7 | Secrets | Neither the Railway URL nor any key appears in the page source, JS bundles, or browser network tab (only `/api/*` calls to the Vercel domain) |
| V8 | Locked backend | Calling the Railway `/recommendations` without the key returns 401 |
| V9 | Mobile | Works at phone width with no horizontal scroll |

Record the outcome as a new row (Phase 4: Deployment) in the [eval.md](eval.md) progress tracker.

### Step 5: Clean up (after V1–V9 pass)

- Delete `frontend/`, `.streamlit/`, and `tests/test_frontend.py`. Remove `streamlit` from `requirements.txt`, which also makes Railway builds smaller.
- Update the README (run instructions, layout, `API_URL` → `BACKEND_URL`) and the frontend section of [architecture.md](architecture.md).

---

## 6. Configuration Reference

| Variable | Where | Value |
|---|---|---|
| `GROQ_API_KEY` | Railway | Your `gsk_…` key |
| `BACKEND_API_KEY` | Railway **and** Vercel | The same random string in both |
| `LLM_MODEL` | Railway | `openai/gpt-oss-120b` (or `openai/gpt-oss-20b` for speed) |
| `LLM_TIMEOUT_S` | Railway | `25` |
| `CANDIDATE_LIMIT` | Railway | `50` (keep low on Groq's free tier) |
| `TOP_K` | Railway | `5` |
| `BACKEND_URL` | Vercel | The Railway public URL, without a trailing slash |

To rotate the API key, set the new value in Railway and Vercel, then redeploy both. Requests fail with 401 in the minute or so between the two.

---

## 7. Rollback and Troubleshooting

**Rollback:**
- **Railway:** service → **Deployments** → open the last good deploy → **Redeploy**.
- **Vercel:** **Deployments** → last good one → **Promote to Production** (instant).
- **Both:** `git revert` on `main` also works.

| Symptom | Likely cause | Fix |
|---|---|---|
| Railway health check fails | Parquet missing (Hugging Face download running), or the app crashed at startup | Check deploy logs. Commit the parquet; check `GROQ_API_KEY` is set |
| Railway logs `GROQ_API_KEY is not set` | Variable missing | Add it under Variables; Railway redeploys |
| UI shows "can't reach the kitchen" | `BACKEND_URL` wrong or missing, or Railway is down | Check the variable has `https://` and no trailing slash; hit `/health` directly |
| Every request fails with an auth error | `BACKEND_API_KEY` differs between Vercel and Railway | Set the same value in both; redeploy Vercel (env changes need a redeploy) |
| Recommendations time out on Vercel | Function limit hit | Check `maxDuration = 60` is exported from the route; lower `LLM_TIMEOUT_S` |
| Every result is `degraded` | Groq rate limit, bad key, or model renamed | Check the Groq error in Railway logs; try `openai/gpt-oss-20b` |

---

## 8. Optional Hardening (after the first deploy)

1. **Per-IP rate limit** in the Vercel route handler (e.g. Upstash or Vercel KV), so one visitor can't use up the shared Groq quota.
2. **CI:** a GitHub Action that runs `pytest` and `web` tests (`vitest`) on each push, so a red build never reaches `main` (both hosts deploy from it).
3. **Railway usage alert** in billing settings, so a spike can't run past the plan.
