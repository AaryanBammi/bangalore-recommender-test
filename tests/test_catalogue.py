import pandas as pd
import pytest

from backend.catalogue import Catalogue, budget_tier, clean, parse_cost, parse_rate, split_list


@pytest.mark.parametrize("raw, expected", [
    ("4.1/5", 4.1),
    ("4.1 /5", 4.1),
    (" 3.8 / 5 ", 3.8),
    ("NEW", None),
    ("-", None),
    ("", None),
    (None, None),
    (float("nan"), None),
    ("6.2/5", None),
])
def test_parse_rate(raw, expected):
    assert parse_rate(raw) == expected


@pytest.mark.parametrize("raw, expected", [
    ("800", 800),
    ("1,200", 1200),
    (" 1,200 ", 1200),
    (None, None),
    (float("nan"), None),
    ("", None),
    ("abc", None),
    ("0", None),
])
def test_parse_cost(raw, expected):
    assert parse_cost(raw) == expected


@pytest.mark.parametrize("cost, tier", [
    (300, "low"), (301, "medium"), (700, "medium"), (701, "high"), (None, None),
])
def test_budget_tier_boundaries(cost, tier):
    assert budget_tier(cost) == tier


def test_split_list_trims_lowercases_and_dedupes():
    assert split_list("North Indian, Chinese, chinese,") == ["north indian", "chinese"]
    assert split_list(None) == []
    assert split_list("null") == []


def raw_row(**overrides):
    row = {
        "name": "Jalsa", "address": "942, 21st Main Road", "location": "Banashankari",
        "listed_in(city)": "Banashankari", "cuisines": "North Indian, Mughlai",
        "rate": "4.1/5", "votes": 775, "approx_cost(for two people)": "800",
        "rest_type": "Casual Dining", "listed_in(type)": "Buffet", "online_order": "Yes",
        "book_table": "No", "dish_liked": "Pasta, Lunch Buffet",
    }
    row.update(overrides)
    return row


def test_clean_parses_and_shapes_row():
    df = clean(pd.DataFrame([raw_row()]))
    row = df.iloc[0]
    assert row["rating"] == 4.1
    assert row["cost_for_two"] == 800
    assert row["budget_tier"] == "high"
    assert row["cuisines"] == ["north indian", "mughlai"]
    assert row["online_order"]
    assert not row["book_table"]
    assert row["dish_liked"] == ["Pasta", "Lunch Buffet"]
    assert row["id"].startswith("r_") and len(row["id"]) == 12


def test_clean_dedupes_keeping_most_voted_and_merges_listing_types():
    df = clean(pd.DataFrame([
        raw_row(votes=100, rate="3.9/5", **{"listed_in(type)": "Buffet"}),
        raw_row(votes=775, rate="4.1/5", **{"listed_in(type)": "Dine-out"}),
        raw_row(address="942,  21st MAIN Road", votes=5, **{"listed_in(type)": "Cafes"}),
    ]))
    assert len(df) == 1
    assert df.iloc[0]["rating"] == 4.1
    assert df.iloc[0]["listing_types"] == ["Buffet", "Cafes", "Dine-out"]


def test_clean_keeps_chain_branches_separate():
    df = clean(pd.DataFrame([raw_row(), raw_row(address="12 MG Road")]))
    assert len(df) == 2
    assert df["id"].is_unique


def test_clean_drops_rows_without_name_or_location():
    df = clean(pd.DataFrame([raw_row(), raw_row(name="", address="x"), raw_row(location=None, address="y")]))
    assert len(df) == 1


def test_clean_fixes_mojibake():
    df = clean(pd.DataFrame([raw_row(name="CafÃ© Down The Alley")]))
    assert df.iloc[0]["name"] == "Café Down The Alley"


def test_clean_rejects_missing_columns():
    with pytest.raises(ValueError, match="missing expected columns"):
        clean(pd.DataFrame([{"name": "x"}]))


def test_catalogue_lookups(catalogue: Catalogue):
    assert catalogue.locations() == ["Indiranagar", "Koramangala"]
    assert "chinese" in catalogue.cuisines()
    assert catalogue.resolve_location("  indiranagar ") == "Indiranagar"
    assert catalogue.resolve_location("Delhi") is None
