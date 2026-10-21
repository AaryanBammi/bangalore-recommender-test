"""FastAPI app (architecture §2.4). Run: uvicorn backend.api:app --port 8000"""

import logging
import os
import secrets
from contextlib import asynccontextmanager
from typing import Callable

import pandas as pd
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Request

from backend.catalogue import Catalogue, load_catalogue
from backend.filters import filter_restaurants
from backend.llm import GroqRanker
from backend.models import RecommendationItem, RecommendationRequest, RecommendationResponse

load_dotenv()
logging.basicConfig(level=logging.INFO)
for noisy in ("httpx", "httpx2", "huggingface_hub"):
    logging.getLogger(noisy).setLevel(logging.WARNING)
log = logging.getLogger(__name__)

CANDIDATE_LIMIT = int(os.getenv("CANDIDATE_LIMIT", "50"))
TOP_K = int(os.getenv("TOP_K", "5"))
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")
LLM_TIMEOUT_S = float(os.getenv("LLM_TIMEOUT_S", "25"))
# When set (deployment), /options and /recommendations require a matching X-API-Key header.
BACKEND_API_KEY = os.getenv("BACKEND_API_KEY") or None
if CANDIDATE_LIMIT <= 0 or TOP_K <= 0 or TOP_K > CANDIDATE_LIMIT:
    raise RuntimeError("Invalid config: need 0 < TOP_K <= CANDIDATE_LIMIT")

# (request, canonical location, candidates) -> ([(id, explanation | None)], summary | None)
Ranker = Callable[[RecommendationRequest, str, pd.DataFrame], tuple[list[tuple[str, str | None]], str | None]]


def _default_ranker() -> Ranker:
    if not os.getenv("GROQ_API_KEY"):
        raise RuntimeError("GROQ_API_KEY is not set. Copy .env.example to .env and add your key.")
    return GroqRanker(model=LLM_MODEL, top_k=TOP_K, timeout_s=LLM_TIMEOUT_S)


def _to_item(rank: int, row: pd.Series, explanation: str | None = None) -> RecommendationItem:
    return RecommendationItem(
        rank=rank,
        name=row["name"],
        cuisines=list(row["cuisines"]),
        rating=None if pd.isna(row["rating"]) else float(row["rating"]),
        cost_for_two=None if pd.isna(row["cost_for_two"]) else int(row["cost_for_two"]),
        location=row["location"],
        explanation=explanation,
    )


def create_app(loader: Callable[[], Catalogue] = load_catalogue,
               ranker: Ranker | None = None,
               api_key: str | None = BACKEND_API_KEY) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.ranker = ranker or _default_ranker()
        app.state.catalogue = loader()
        logging.info("Catalogue loaded: %d restaurants", len(app.state.catalogue))
        yield

    def require_api_key(x_api_key: str | None = Header(default=None)):
        if api_key and not (x_api_key and secrets.compare_digest(x_api_key.encode(), api_key.encode())):
            raise HTTPException(401, "Missing or invalid X-API-Key header.")

    # A keyed (deployed) backend also hides its API docs.
    docs = {"docs_url": None, "redoc_url": None, "openapi_url": None} if api_key else {}
    app = FastAPI(title="Restaurant Recommender", lifespan=lifespan, **docs)
    keyed = [Depends(require_api_key)]

    # Endpoints are plain `def` so blocking work runs in the threadpool (edge_case O5).
    @app.get("/health")
    def health(request: Request):
        return {"status": "ok", "rows": len(request.app.state.catalogue)}

    @app.get("/options", dependencies=keyed)
    def options(request: Request):
        catalogue: Catalogue = request.app.state.catalogue
        return {"locations": catalogue.locations(), "cuisines": catalogue.cuisines()}

    @app.post("/recommendations", response_model=RecommendationResponse, dependencies=keyed)
    def recommendations(req: RecommendationRequest, request: Request):
        catalogue: Catalogue = request.app.state.catalogue
        location = catalogue.resolve_location(req.location)
        if location is None:
            raise HTTPException(400, "Unknown location. Data covers Bangalore localities only. See /options.")
        unknown = sorted(set(req.cuisines) - set(catalogue.cuisines()))
        if unknown:
            raise HTTPException(400, f"Unknown cuisines: {', '.join(unknown)}. See /options.")

        candidates, notes = filter_restaurants(catalogue.df, req, location, limit=CANDIDATE_LIMIT)
        if candidates.empty:  # nothing to rank; skip the LLM (edge_case F14)
            return RecommendationResponse(recommendations=[], candidates_considered=0, notes=notes)

        picks: list[tuple[str, str | None]] = []
        summary, degraded = None, False
        try:
            picks, summary = request.app.state.ranker(req, location, candidates)
        except Exception:
            log.exception("LLM ranking failed; returning pre-sorted candidates")
            degraded = True

        # Facts always come from the catalogue rows, never from the LLM.
        by_id = candidates.set_index("id", drop=False)
        chosen = [(cid, expl) for cid, expl in picks if cid in by_id.index][:TOP_K]
        picked = {cid for cid, _ in chosen}
        for cid in candidates["id"]:  # top up from pre-sorted order (edge_case L16)
            if len(chosen) >= TOP_K:
                break
            if cid not in picked:
                chosen.append((cid, None))

        items = [_to_item(i, by_id.loc[cid], expl) for i, (cid, expl) in enumerate(chosen, 1)]
        return RecommendationResponse(
            recommendations=items,
            summary=summary,
            candidates_considered=len(candidates),
            notes=notes,
            degraded=degraded,
        )

    return app


app = create_app()
