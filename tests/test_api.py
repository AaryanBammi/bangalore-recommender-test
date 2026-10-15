import pytest
from fastapi.testclient import TestClient

from backend.api import create_app


@pytest.fixture
def client(catalogue):
    with TestClient(create_app(loader=lambda: catalogue)) as c:
        yield c


def body(**kw):
    base = {"location": "Indiranagar", "budget": "medium", "cuisines": ["north indian"], "min_rating": 4.0}
    base.update(kw)
    return base


def test_health(client, catalogue):
    assert client.get("/health").json() == {"status": "ok", "rows": len(catalogue)}


def test_options(client):
    data = client.get("/options").json()
    assert data["locations"] == ["Indiranagar", "Koramangala"]
    assert data["cuisines"] == sorted(data["cuisines"]) and "italian" in data["cuisines"]


def test_recommendations_happy_path(client):
    resp = client.post("/recommendations", json=body())
    assert resp.status_code == 200
    data = resp.json()
    items = data["recommendations"]
    assert 0 < len(items) <= 5
    assert [i["rank"] for i in items] == list(range(1, len(items) + 1))
    assert all(i["explanation"] is None for i in items)
    assert all(i["location"] == "Indiranagar" and i["rating"] >= 4.0 for i in items)
    assert data["candidates_considered"] == 6
    assert data["notes"] == [] and data["degraded"] is False


def test_location_and_cuisine_case_insensitive(client):
    resp = client.post("/recommendations", json=body(location=" indiranagar ", cuisines=["North Indian"], budget="MEDIUM"))
    assert resp.status_code == 200 and resp.json()["recommendations"]


def test_null_rating_and_cost_serialize_as_null(client):
    resp = client.post("/recommendations", json=body(cuisines=["italian"], budget="high", min_rating=0))
    items = {i["name"]: i for i in resp.json()["recommendations"]}
    assert items["Restaurant 22"]["cost_for_two"] is None


def test_unknown_location_400(client):
    resp = client.post("/recommendations", json=body(location="Delhi"))
    assert resp.status_code == 400 and "See /options" in resp.json()["detail"]


def test_unknown_cuisine_400(client):
    resp = client.post("/recommendations", json=body(cuisines=["martian"]))
    assert resp.status_code == 400 and "martian" in resp.json()["detail"]


@pytest.mark.parametrize("bad", [
    {"budget": "cheap"},
    {"min_rating": 6},
    {"min_rating": -1},
    {"preference": "x" * 301},
    {"location": None},
])
def test_validation_422(client, bad):
    assert client.post("/recommendations", json=body(**bad)).status_code == 422


def test_empty_body_422(client):
    assert client.post("/recommendations", content="not json").status_code == 422


def test_no_matches_returns_empty_with_note(client):
    resp = client.post("/recommendations", json=body(location="Koramangala", cuisines=["italian"]))
    data = resp.json()
    assert resp.status_code == 200 and data["recommendations"] == []
    assert "No restaurants match" in data["notes"][-1]
