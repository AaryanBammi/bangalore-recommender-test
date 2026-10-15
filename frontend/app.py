"""Streamlit UI (architecture §4). Talks to the backend only over HTTP.

Run: streamlit run frontend/app.py
"""

import os

import httpx
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
API_URL = os.getenv("API_URL", "http://localhost:8000").rstrip("/")
REQUEST_TIMEOUT_S = 60
DEFAULT_LOCATION = "Indiranagar"


class BackendError(Exception):
    """A user-facing error message for anything that went wrong talking to the backend."""


@st.cache_data(ttl=300, show_spinner=False)
def fetch_options() -> dict:
    # Exceptions are not cached, so a down backend is retried on the next rerun.
    resp = httpx.get(f"{API_URL}/options", timeout=10)
    resp.raise_for_status()
    return resp.json()


def _error_detail(resp: httpx.Response) -> str:
    try:
        detail = resp.json().get("detail")
    except ValueError:
        return f"HTTP {resp.status_code}"
    if isinstance(detail, list):  # FastAPI validation errors
        return "; ".join(f"{'.'.join(map(str, e.get('loc', [])[1:]))}: {e.get('msg')}" for e in detail)
    return str(detail)


def get_recommendations(payload: dict) -> dict:
    try:
        resp = httpx.post(f"{API_URL}/recommendations", json=payload, timeout=REQUEST_TIMEOUT_S)
    except httpx.TimeoutException:
        raise BackendError("The request timed out. Please try again.")
    except httpx.HTTPError:
        raise BackendError(f"Backend not reachable at {API_URL}. Is it still running?")
    if 400 <= resp.status_code < 500:
        raise BackendError(_error_detail(resp))
    if resp.status_code >= 500:
        raise BackendError("Something went wrong on the server. Please try again.")
    return resp.json()


def render_card(item: dict, show_explanation: bool) -> None:
    with st.container(border=True):
        st.markdown(f"#### {item['rank']}. {item['name']}")
        st.caption(f"{', '.join(c.title() for c in item['cuisines']) or 'Cuisine N/A'} · {item['location']}")
        rating, cost = st.columns(2)
        rating.markdown(f"⭐ **{item['rating']:.1f}**" if item["rating"] is not None else "⭐ Unrated")
        cost.markdown(
            f"₹ **{item['cost_for_two']:,}** for two" if item["cost_for_two"] is not None else "₹ Cost N/A"
        )
        if show_explanation and item.get("explanation"):
            st.write(item["explanation"])


def render_results(data: dict) -> None:
    if data["degraded"]:
        st.warning("AI explanations are unavailable right now, so these are the top-rated matches.")
    for note in data["notes"]:
        st.info(note)
    if not data["recommendations"]:
        st.info("No matches. Try a different budget or cuisine, or a lower minimum rating.")
        return
    if data.get("summary"):
        st.markdown(f"**Summary:** {data['summary']}")
    for item in data["recommendations"]:
        render_card(item, show_explanation=not data["degraded"])
    st.caption(f"Ranked from {data['candidates_considered']} matching restaurants.")


def main() -> None:
    st.set_page_config(page_title="Restaurant Recommender", page_icon="🍽️")
    st.title("🍽️ Restaurant Recommender")
    st.caption("Data covers Bangalore only.")

    try:
        options = fetch_options()
    except httpx.HTTPError:
        st.error(f"Backend not reachable at {API_URL}. Start it first with: `uvicorn backend.api:app --port 8000`")
        st.stop()

    locations = options["locations"]
    with st.form("preferences"):
        location = st.selectbox(
            "Location", locations,
            index=locations.index(DEFAULT_LOCATION) if DEFAULT_LOCATION in locations else 0,
        )
        budget = st.radio("Budget (cost for two)", ["low", "medium", "high"], index=1, horizontal=True,
                          format_func=lambda b: {"low": "Low (≤ ₹300)", "medium": "Medium (₹301–700)",
                                                 "high": "High (> ₹700)"}[b])
        cuisines = st.multiselect("Cuisines (optional)", options["cuisines"], format_func=str.title)
        min_rating = st.slider("Minimum rating", 0.0, 5.0, 3.5, step=0.5)
        preference = st.text_input("Anything else? (optional)", max_chars=300,
                                   placeholder="e.g. family-friendly, quick service, delivery")
        submitted = st.form_submit_button("Get recommendations", type="primary")

    if submitted:
        payload = {"location": location, "budget": budget, "cuisines": cuisines,
                   "min_rating": min_rating, "preference": preference}
        with st.spinner("Finding the best matches..."):
            try:
                st.session_state["result"] = get_recommendations(payload)
                st.session_state.pop("error", None)
            except BackendError as exc:
                st.session_state["error"] = str(exc)
                st.session_state.pop("result", None)

    if "error" in st.session_state:
        st.error(st.session_state["error"])
    elif "result" in st.session_state:
        render_results(st.session_state["result"])


main()
