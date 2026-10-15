import pytest

from backend.filters import filter_restaurants, keyword_hints
from backend.models import RecommendationRequest
from tests.conftest import make_df, restaurant


def req(**kw):
    base = {"location": "Indiranagar", "budget": "medium", "cuisines": [], "min_rating": 0}
    base.update(kw)
    return RecommendationRequest(**base)


def run(catalogue, location="Indiranagar", **kw):
    return filter_restaurants(catalogue.df, req(location=location, **kw), location)


def test_location_filter(catalogue):
    out, _ = run(catalogue, location="Koramangala", budget="medium")
    assert set(out["location"]) == {"Koramangala"}


def test_cuisine_overlap(catalogue):
    out, _ = run(catalogue, budget="low", cuisines=["thai", "chinese"])
    assert set(out["id"]) == {"r_0000000010", "r_0000000011", "r_0000000012"}


def test_rating_filter_excludes_unrated():
    df = make_df([restaurant(i, rating=4.5) for i in range(5)] + [restaurant(9, rating=None)])
    out, notes = filter_restaurants(df, req(min_rating=4.0), "Indiranagar")
    assert len(out) == 5 and notes == []
    assert "r_0000000009" not in set(out["id"])


def test_min_rating_zero_includes_unrated():
    df = make_df([restaurant(i, rating=None) for i in range(5)])
    out, notes = filter_restaurants(df, req(), "Indiranagar")
    assert len(out) == 5 and notes == []


def test_budget_filter(catalogue):
    out, notes = run(catalogue, budget="medium", cuisines=["north indian"])
    assert notes == []
    assert set(out["budget_tier"]) == {"medium"}
    assert len(out) == 6


def test_sorted_by_rating_then_votes_unrated_last():
    df = make_df([
        restaurant(1, rating=4.0, votes=10),
        restaurant(2, rating=4.5, votes=5),
        restaurant(3, rating=4.0, votes=50),
        restaurant(4, rating=None, votes=999),
        restaurant(5, rating=4.0, votes=50),
    ])
    out, _ = filter_restaurants(df, req(), "Indiranagar")
    assert list(out["id"]) == ["r_0000000002", "r_0000000003", "r_0000000005", "r_0000000001", "r_0000000004"]


def test_candidate_cap():
    df = make_df([restaurant(i) for i in range(50)])
    out, _ = filter_restaurants(df, req(), "Indiranagar", limit=20)
    assert len(out) == 20


def test_relaxes_budget_with_note(catalogue):
    out, notes = run(catalogue, budget="high", cuisines=["italian"])
    assert len(out) == 3
    assert any("budget" in n for n in notes)


def test_relaxes_rating_down_to_floor(catalogue):
    out, notes = run(catalogue, budget="high", cuisines=["italian"], min_rating=4.8)
    # budget dropped first, then rating lowered 4.8 -> 4.3 -> 3.8 -> 3.3 -> 3.0 (floor)
    assert "budget" in notes[0]
    assert "lowered minimum rating to 3" in notes[1]
    assert list(out["rating"]) == [4.5, 3.9, 3.4]


def test_hints_relaxed_before_budget():
    df = make_df([restaurant(i, online_order=(i < 2)) for i in range(6)])
    out, notes = filter_restaurants(df, req(preference="quick delivery"), "Indiranagar")
    assert len(out) == 6
    assert len(notes) == 1 and "delivery" in notes[0]


def test_hint_applied_when_enough_matches():
    df = make_df([restaurant(i, online_order=(i < 5)) for i in range(8)])
    out, notes = filter_restaurants(df, req(preference="delivery please"), "Indiranagar")
    assert len(out) == 5 and out["online_order"].all() and notes == []


def test_no_matches_note(catalogue):
    out, notes = run(catalogue, location="Koramangala", cuisines=["italian"])
    assert out.empty
    assert "No restaurants match" in notes[-1]


@pytest.mark.parametrize("text, expected", [
    ("delivery please", {"online_order"}),
    ("want to book a table", {"book_table"}),
    ("reservation and delivery", {"online_order", "book_table"}),
    ("no delivery needed", set()),
    ("don't need booking", set()),
    ("facebook-famous place", set()),
    ("family-friendly, quick service", set()),
    ("", set()),
])
def test_keyword_hints(text, expected):
    assert set(keyword_hints(text)) == expected
