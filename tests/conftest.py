import pandas as pd
import pytest

from backend.catalogue import Catalogue, budget_tier


def restaurant(i, *, location="Indiranagar", cuisines=("north indian",), rating=4.0,
               votes=100, cost=500, online_order=False, book_table=False, name=None):
    return {
        "id": f"r_{i:010d}",
        "name": name or f"Restaurant {i}",
        "address": f"{i} Main Road",
        "location": location,
        "zone": location,
        "cuisines": list(cuisines),
        "rating": rating,
        "votes": votes,
        "cost_for_two": cost,
        "budget_tier": budget_tier(cost),
        "rest_type": ["casual dining"],
        "listing_types": ["Dine-out"],
        "online_order": online_order,
        "book_table": book_table,
        "dish_liked": [],
    }


def make_df(rows):
    df = pd.DataFrame(rows)
    df["rating"] = df["rating"].astype(float)
    df["cost_for_two"] = df["cost_for_two"].astype("Int64")
    return df


@pytest.fixture
def catalogue():
    """~20 clean restaurants across two localities."""
    rows = [
        # Indiranagar, medium budget, north indian — 6 matches for a typical query
        *(restaurant(i, rating=4.0 + i / 10, votes=100 + i, cost=500) for i in range(6)),
        # Indiranagar, low budget, chinese, mixed ratings
        restaurant(10, cuisines=("chinese",), rating=3.6, cost=250, online_order=True),
        restaurant(11, cuisines=("chinese", "thai"), rating=4.2, cost=300, online_order=True),
        restaurant(12, cuisines=("chinese",), rating=None, cost=200),
        # Indiranagar, high budget, italian
        restaurant(20, cuisines=("italian",), rating=4.5, cost=1500, book_table=True),
        restaurant(21, cuisines=("italian", "pizza"), rating=3.4, cost=900),
        restaurant(22, cuisines=("italian",), rating=3.9, cost=None),
        # Koramangala
        *(restaurant(30 + i, location="Koramangala", cuisines=("cafe",), rating=4.1, cost=400)
          for i in range(5)),
    ]
    return Catalogue(make_df(rows))
