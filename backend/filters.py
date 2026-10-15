"""Filter and relaxation (architecture §2.2)."""

import re

import pandas as pd

from backend.models import RecommendationRequest

MIN_RESULTS = 5
RATING_FLOOR = 3.0
RATING_STEP = 0.5

# Keyword hints from free-text preference -> boolean catalogue column (whole words only).
HINTS = {
    "online_order": (re.compile(r"\bdeliver(?:y|ies)?\b"), "delivery"),
    "book_table": (re.compile(r"\b(?:book(?:ing)?|reserv(?:e|ation|ations))\b"), "table booking"),
}
NEGATIONS = {"no", "not", "don't", "dont", "without", "never", "skip"}


def keyword_hints(preference: str) -> dict[str, str]:
    """Map preference text to {column: label}, ignoring negated mentions like 'no delivery'."""
    text = preference.lower()
    hints = {}
    for column, (pattern, label) in HINTS.items():
        for match in pattern.finditer(text):
            before = re.findall(r"[\w']+", text[: match.start()])[-3:]
            if not NEGATIONS.intersection(before):
                hints[column] = label
                break
    return hints


def _match(df: pd.DataFrame, req: RecommendationRequest, location: str, *,
           hints: dict[str, str], use_budget: bool, min_rating: float) -> pd.DataFrame:
    mask = df["location"] == location
    if req.cuisines:
        wanted = set(req.cuisines)
        mask &= df["cuisines"].map(lambda cs: not wanted.isdisjoint(cs))
    if min_rating > 0:
        mask &= df["rating"] >= min_rating  # NaN (unrated) compares False
    if use_budget:
        mask &= df["budget_tier"] == req.budget
    for column in hints:
        mask &= df[column]
    return df[mask]


def filter_restaurants(df: pd.DataFrame, req: RecommendationRequest, location: str,
                       limit: int = 300) -> tuple[pd.DataFrame, list[str]]:
    """Apply hard filters, relaxing (hints -> budget -> rating) until MIN_RESULTS match.

    `location` must already be resolved to the catalogue's canonical name.
    Returns candidates sorted by rating then votes (capped at `limit`) and relaxation notes.
    """
    hints = keyword_hints(req.preference)
    use_budget = True
    min_rating = req.min_rating
    notes: list[str] = []

    result = _match(df, req, location, hints=hints, use_budget=use_budget, min_rating=min_rating)

    if len(result) < MIN_RESULTS and hints:
        notes.append(f"Few matches with {' and '.join(hints.values())}; showing places without it too.")
        hints = {}
        result = _match(df, req, location, hints=hints, use_budget=use_budget, min_rating=min_rating)

    if len(result) < MIN_RESULTS:
        notes.append(f"Few matches in the {req.budget} budget; showing other price ranges.")
        use_budget = False
        result = _match(df, req, location, hints=hints, use_budget=use_budget, min_rating=min_rating)

    floor = min(RATING_FLOOR, req.min_rating)
    while len(result) < MIN_RESULTS and min_rating > floor:
        min_rating = max(floor, min_rating - RATING_STEP)
        result = _match(df, req, location, hints=hints, use_budget=use_budget, min_rating=min_rating)
    if min_rating < req.min_rating:
        notes.append(f"Few matches rated {req.min_rating:g}+; lowered minimum rating to {min_rating:g}.")

    if result.empty:
        notes.append("No restaurants match your preferences, even after relaxing filters.")

    result = result.sort_values(
        ["rating", "votes", "id"], ascending=[False, False, True], na_position="last"
    )
    return result.head(limit), notes
