"""API request/response models (architecture §3)."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class RecommendationRequest(BaseModel):
    location: str
    budget: Literal["low", "medium", "high"]
    cuisines: list[str] = []
    min_rating: float = Field(0, ge=0, le=5)
    preference: str = Field("", max_length=300)

    @field_validator("budget", mode="before")
    @classmethod
    def _lower_budget(cls, v):
        return v.strip().lower() if isinstance(v, str) else v

    @field_validator("cuisines", mode="before")
    @classmethod
    def _normalize_cuisines(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            v = [v]
        seen = []
        for c in v:
            c = " ".join(str(c).split()).lower()
            if c and c not in seen:
                seen.append(c)
        return seen

    @field_validator("preference", mode="before")
    @classmethod
    def _strip_preference(cls, v):
        return "" if v is None else str(v).strip()


class RecommendationItem(BaseModel):
    rank: int
    name: str
    cuisines: list[str]
    rating: float | None
    cost_for_two: int | None
    location: str
    explanation: str | None = None


class RecommendationResponse(BaseModel):
    recommendations: list[RecommendationItem]
    summary: str | None = None
    candidates_considered: int
    notes: list[str] = []
    degraded: bool = False
