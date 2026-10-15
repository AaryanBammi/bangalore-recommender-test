import pytest
from fastapi.testclient import TestClient

from backend.api import create_app


class FakeRanker:
    """Picks candidates in reverse order with canned explanations; can be told to fail or return junk."""

    def __init__(self, fail=False, picks=None):
        self.fail = fail
        self.picks = picks
        self.calls = 0

    def __call__(self, req, location, candidates):
        self.calls += 1
        if self.fail:
            raise RuntimeError("LLM down")
        if self.picks is not None:
            return self.picks, "Custom summary."
        ids = list(candidates["id"])[::-1][:5]
        return [(cid, f"Why {cid} fits.") for cid in ids], "A short summary."


@pytest.fixture
def ranker():
    return FakeRanker()


@pytest.fixture
def client(catalogue, ranker):
    with TestClient(create_app(loader=lambda: catalogue, ranker=ranker)) as c:
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
    assert len(items) == 5
    assert [i["rank"] for i in items] == list(range(1, 6))
    assert all(i["explanation"].startswith("Why r_") for i in items)
    assert all(i["location"] == "Indiranagar" and i["rating"] >= 4.0 for i in items)
    # LLM order is kept: reverse of pre-sorted (rating desc), so lowest-rated first
    assert [i["rating"] for i in items] == sorted(i["rating"] for i in items)
    assert data["summary"] == "A short summary."
    assert data["candidates_considered"] == 6
    assert data["notes"] == [] and data["degraded"] is False


def test_facts_come_from_catalogue_not_llm(catalogue):
    ranker = FakeRanker(picks=[("r_0000000002", "Rated 5.0 and costs ₹10!")])
    with TestClient(create_app(loader=lambda: catalogue, ranker=ranker)) as c:
        item = c.post("/recommendations", json=body()).json()["recommendations"][0]
    assert item["name"] == "Restaurant 2" and item["rating"] == 4.2 and item["cost_for_two"] == 500


def test_llm_failure_degrades_to_presorted(catalogue):
    with TestClient(create_app(loader=lambda: catalogue, ranker=FakeRanker(fail=True))) as c:
        resp = c.post("/recommendations", json=body())
    data = resp.json()
    assert resp.status_code == 200 and data["degraded"] is True
    assert data["summary"] is None
    assert len(data["recommendations"]) == 5
    assert all(i["explanation"] is None for i in data["recommendations"])
    assert [i["rating"] for i in data["recommendations"]] == [4.5, 4.4, 4.3, 4.2, 4.1]


def test_fewer_picks_topped_up_from_presorted(catalogue):
    ranker = FakeRanker(picks=[("r_0000000001", "Pick."), ("r_unknown", "Ghost.")])
    with TestClient(create_app(loader=lambda: catalogue, ranker=ranker)) as c:
        items = c.post("/recommendations", json=body()).json()["recommendations"]
    assert [i["name"] for i in items] == ["Restaurant 1", "Restaurant 5", "Restaurant 4", "Restaurant 3", "Restaurant 2"]
    assert items[0]["explanation"] == "Pick." and all(i["explanation"] is None for i in items[1:])


def test_no_candidates_skips_llm(client, ranker):
    client.post("/recommendations", json=body(location="Koramangala", cuisines=["italian"]))
    assert ranker.calls == 0


def test_missing_api_key_fails_startup(catalogue, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        with TestClient(create_app(loader=lambda: catalogue)):
            pass


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
