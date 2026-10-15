"""FastAPI app (architecture §2.4). Run: uvicorn backend.api:app --port 8000"""

import logging
import os
from contextlib import asynccontextmanager
from typing import Callable

import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request

from backend.catalogue import Catalogue, load_catalogue
from backend.filters import filter_restaurants
from backend.models import RecommendationItem, RecommendationRequest, RecommendationResponse

load_dotenv()
logging.basicConfig(level=logging.INFO)
for noisy in ("httpx", "httpx2", "huggingface_hub"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

CANDIDATE_LIMIT = int(os.getenv("CANDIDATE_LIMIT", "300"))
TOP_K = int(os.getenv("TOP_K", "5"))
if CANDIDATE_LIMIT <= 0 or TOP_K <= 0 or TOP_K > CANDIDATE_LIMIT:
    raise RuntimeError("Invalid config: need 0 < TOP_K <= CANDIDATE_LIMIT")


def _to_item(rank: int, row: pd.Series) -> RecommendationItem:
    return RecommendationItem(
        rank=rank,
        name=row["name"],
        cuisines=list(row["cuisines"]),
        rating=None if pd.isna(row["rating"]) else float(row["rating"]),
        cost_for_two=None if pd.isna(row["cost_for_two"]) else int(row["cost_for_two"]),
        location=row["location"],
    )


def create_app(loader: Callable[[], Catalogue] = load_catalogue) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.catalogue = loader()
        logging.info("Catalogue loaded: %d restaurants", len(app.state.catalogue))
        yield

    app = FastAPI(title="Restaurant Recommender", lifespan=lifespan)

    # Endpoints are plain `def` so blocking work runs in the threadpool (edge_case O5).
    @app.get("/health")
    def health(request: Request):
        return {"status": "ok", "rows": len(request.app.state.catalogue)}

    @app.get("/options")
    def options(request: Request):
        catalogue: Catalogue = request.app.state.catalogue
        return {"locations": catalogue.locations(), "cuisines": catalogue.cuisines()}

    @app.post("/recommendations", response_model=RecommendationResponse)
    def recommendations(req: RecommendationRequest, request: Request):
        catalogue: Catalogue = request.app.state.catalogue
        location = catalogue.resolve_location(req.location)
        if location is None:
            raise HTTPException(400, "Unknown location. Data covers Bangalore localities only. See /options.")
        unknown = sorted(set(req.cuisines) - set(catalogue.cuisines()))
        if unknown:
            raise HTTPException(400, f"Unknown cuisines: {', '.join(unknown)}. See /options.")

        candidates, notes = filter_restaurants(catalogue.df, req, location, limit=CANDIDATE_LIMIT)

        # Phase 1 placeholder: top-K pre-sorted candidates, no LLM yet.
        items = [_to_item(i, row) for i, (_, row) in enumerate(candidates.head(TOP_K).iterrows(), 1)]
        return RecommendationResponse(
            recommendations=items,
            candidates_considered=len(candidates),
            notes=notes,
        )

    return app


app = create_app()
