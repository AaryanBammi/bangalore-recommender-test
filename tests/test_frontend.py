"""Frontend tests: run the Streamlit app headless with the HTTP layer faked."""

from pathlib import Path

import httpx
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "frontend" / "app.py")
OPTIONS = {"locations": ["BTM", "Indiranagar"], "cuisines": ["chinese", "north indian"]}


def item(rank, explanation="Fits your budget.", rating=4.2, cost=500):
    return {"rank": rank, "name": f"Place {rank}", "cuisines": ["north indian"], "rating": rating,
            "cost_for_two": cost, "location": "Indiranagar", "explanation": explanation}


def result(**overrides):
    data = {"recommendations": [item(i) for i in range(1, 6)], "summary": "Great picks.",
            "candidates_considered": 8, "notes": [], "degraded": False}
    data.update(overrides)
    return data


class FakeHttp:
    """Stands in for httpx.get/post. `post_result` is a dict (200), an httpx.Response, or an exception."""

    def __init__(self, options=OPTIONS, post_result=None):
        self.options = options
        self.post_result = post_result if post_result is not None else result()
        self.posted = []

    def get(self, url, **kwargs):
        if isinstance(self.options, Exception):
            raise self.options
        return httpx.Response(200, json=self.options, request=httpx.Request("GET", url))

    def post(self, url, json=None, **kwargs):
        self.posted.append(json)
        if isinstance(self.post_result, Exception):
            raise self.post_result
        if isinstance(self.post_result, httpx.Response):
            return self.post_result
        return httpx.Response(200, json=self.post_result, request=httpx.Request("POST", url))


@pytest.fixture
def run(monkeypatch):
    def _run(fake: FakeHttp, submit=True):
        st.cache_data.clear()
        monkeypatch.setattr(httpx, "get", fake.get)
        monkeypatch.setattr(httpx, "post", fake.post)
        at = AppTest.from_file(APP, default_timeout=10).run()
        if submit and not at.exception and at.button:
            at.button[0].click().run()
        return at
    return _run


def texts(at):
    return " ".join(m.value for m in at.markdown) + " ".join(c.value for c in at.caption)


def test_form_populated_from_options(run):
    at = run(FakeHttp(), submit=False)
    assert not at.exception
    assert at.selectbox[0].options == ["BTM", "Indiranagar"] and at.selectbox[0].value == "Indiranagar"
    assert at.radio[0].value == "medium"
    assert at.slider[0].value == 3.5
    assert "Data covers Bangalore only." in texts(at)


def test_submit_sends_payload_and_renders_cards(run):
    fake = FakeHttp()
    at = run(fake)
    assert fake.posted == [{"location": "Indiranagar", "budget": "medium", "cuisines": [],
                            "min_rating": 3.5, "preference": ""}]
    body = texts(at)
    assert "**Summary:** Great picks." in body
    for i in range(1, 6):
        assert f"#### {i}. Place {i}" in body
    assert "⭐ **4.2**" in body and "₹ **500** for two" in body
    assert "Fits your budget." in body
    assert not at.error and not at.warning


def test_null_rating_and_cost_shown_as_text(run):
    at = run(FakeHttp(post_result=result(recommendations=[item(1, rating=None, cost=None)])))
    body = texts(at)
    assert "⭐ Unrated" in body and "₹ Cost N/A" in body
    assert "None" not in body and "nan" not in body


def test_degraded_shows_banner_and_hides_explanations(run):
    data = result(degraded=True, summary=None,
                  recommendations=[item(i, explanation=None) for i in range(1, 6)])
    at = run(FakeHttp(post_result=data))
    assert "AI explanations are unavailable" in at.warning[0].value
    assert "Summary" not in texts(at)


def test_notes_shown_as_info(run):
    at = run(FakeHttp(post_result=result(notes=["Few matches in the high budget; showing other price ranges."])))
    assert any("high budget" in i.value for i in at.info)


def test_empty_state(run):
    at = run(FakeHttp(post_result=result(recommendations=[], summary=None,
                                         notes=["No restaurants match your preferences."])))
    assert any("No matches" in i.value for i in at.info)


def test_backend_down_on_load(run):
    at = run(FakeHttp(options=httpx.ConnectError("refused")), submit=False)
    assert "Backend not reachable" in at.error[0].value
    assert not at.button  # form hidden


def test_backend_down_on_submit(run):
    at = run(FakeHttp(post_result=httpx.ConnectError("refused")))
    assert "Backend not reachable" in at.error[0].value


def test_timeout_on_submit(run):
    at = run(FakeHttp(post_result=httpx.ReadTimeout("slow")))
    assert "timed out" in at.error[0].value


def test_api_400_detail_shown(run):
    resp = httpx.Response(400, json={"detail": "Unknown location. See /options."},
                          request=httpx.Request("POST", "http://x"))
    at = run(FakeHttp(post_result=resp))
    assert at.error[0].value == "Unknown location. See /options."


def test_api_422_detail_readable(run):
    resp = httpx.Response(422, json={"detail": [{"loc": ["body", "min_rating"], "msg": "too big"}]},
                          request=httpx.Request("POST", "http://x"))
    at = run(FakeHttp(post_result=resp))
    assert at.error[0].value == "min_rating: too big"


def test_api_500_generic_message(run):
    resp = httpx.Response(500, text="Internal Server Error", request=httpx.Request("POST", "http://x"))
    at = run(FakeHttp(post_result=resp))
    assert "Something went wrong" in at.error[0].value
