"""Streamlit UI (architecture §4). Talks to the backend only over HTTP.

Run: streamlit run frontend/app.py
Theme (palette, font, light mode) lives in .streamlit/config.toml; layout and card styles are in CSS below.
"""

import html
import os

import httpx
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
API_URL = os.getenv("API_URL", "http://localhost:8000").rstrip("/")
API_HEADERS = {"X-API-Key": key} if (key := os.getenv("BACKEND_API_KEY")) else {}
REQUEST_TIMEOUT_S = 60
DEFAULT_LOCATION = "Indiranagar"
# Shown as chips; every other cuisine sits in the "More cuisines" expander.
POPULAR_CUISINES = ["north indian", "south indian", "chinese", "cafe", "biryani",
                    "fast food", "continental", "italian", "desserts", "street food"]
BUDGETS = {"low": "Under ₹300", "medium": "₹300–700", "high": "₹700+"}
RATINGS = [0.0, 3.5, 4.0, 4.5]
DEFAULT_RATING = 3.5

ICON_LOGO = ('<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2" '
             'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 11h18a9 9 0 0 1-18 0Z"/>'
             '<path d="M8 7c0-1.5 1-2 1-3.5M12 7c0-1.5 1-2 1-3.5M16 7c0-1.5 1-2 1-3.5"/></svg>')
ICON_PIN = ('<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
            'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
            '<path d="M12 21s-7-6.2-7-11.5a7 7 0 0 1 14 0C19 14.8 12 21 12 21Z"/><circle cx="12" cy="9.5" r="2.5"/></svg>')
ICON_STAR = ('<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">'
             '<path d="m12 2.5 2.9 6 6.6.9-4.8 4.6 1.2 6.5L12 17.4l-5.9 3.1 1.2-6.5L2.5 9.4l6.6-.9z"/></svg>')
ICON_PLATE = ('<svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="#557449" stroke-width="1.6" '
              'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="13" r="6.5"/>'
              '<circle cx="12" cy="13" r="3.5"/><path d="M2.5 4v5a1.5 1.5 0 0 0 3 0V4M4 9v11"/>'
              '<path d="M21.5 4c-1.5 0-2.5 2-2.5 5h2.5v11"/></svg>')
ICON_UNPLUGGED = ('<svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="#B5472A" stroke-width="1.6" '
                  'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 12h18a9 9 0 0 1-18 0Z"/>'
                  '<path d="M9 4.5c0 1.5-1 2-1 3.5M13 4.5c0 1.5-1 2-1 3.5"/><path d="m16 3 4 4M20 3l-4 4"/></svg>')

CSS = """
<style>
[data-testid="stHeader"] { background: transparent; }
[data-testid="stDecoration"], [data-testid="stHeaderActionElements"] { display: none; }
[data-testid="stMainBlockContainer"] { max-width: 1120px; padding: 24px 24px 64px; }
[data-testid="stWidgetLabel"] p { font-size: 15px; font-weight: 700; }

/* Search panel card */
.st-key-search { background: #FFFFFF; border: 1px solid #F0E9DD; border-radius: 16px; padding: 32px; gap: 24px;
  box-shadow: 0 1px 2px rgba(70,50,30,0.05), 0 8px 24px rgba(70,50,30,0.06); }
.st-key-search [data-baseweb="select"] > div, .st-key-search [data-baseweb="input"] { min-height: 52px; background: #FFFFFF; }
.st-key-search [data-baseweb="input"] input { background: #FFFFFF; }
.st-key-search [data-testid="stExpander"] details { border-color: #F0E9DD; }

/* Cuisine chips */
.stApp button[data-variant="pills"] {
  min-height: 44px; padding: 0 16px; border-radius: 999px; border-width: 1.5px;
  background: #FFFFFF; border-color: #E4DCCF; color: #2B2A28; font-weight: 600; }
.stApp button[data-variant="pills"]:hover { border-color: #C9BCA8; color: #2B2A28; }
.stApp button[data-variant="pills"][aria-pressed="true"] {
  background: #FBEAE2; border-color: #B5472A; color: #8E3519; font-weight: 700; }

/* Budget / rating segmented controls */
.stApp button[data-variant="segmented_control"] {
  min-height: 44px; background: #F5EFE5; border-color: #F5EFE5; color: #5A554D; font-weight: 600; }
.stApp button[data-variant="segmented_control"]:hover { color: #2B2A28; }
.stApp button[data-variant="segmented_control"][data-selected="true"] {
  background: #FFFFFF; border-color: #E4DCCF; color: #2B2A28; font-weight: 700;
  box-shadow: 0 1px 3px rgba(70,50,30,0.12); z-index: 1; }

.stApp button[data-variant="pills"] p,
.stApp button[data-variant="segmented_control"] p { font-size: 15px; font-weight: inherit; }

/* Primary action */
.stApp button[data-testid="stBaseButton-primary"] { min-height: 56px; border-radius: 14px; }
.stApp button[data-testid="stBaseButton-primary"] p { font-size: 17px; font-weight: 800; }
.stApp button[data-testid="stBaseButton-primary"]:hover { background: #9C3C22; border-color: #9C3C22; }

/* Custom HTML blocks */
.rr-muted { color: #6B655C; }
.rr-header { display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.rr-brand { display: flex; align-items: center; gap: 12px; font-size: 18px; font-weight: 800; }
.rr-logo { width: 40px; height: 40px; border-radius: 12px; background: #B5472A; display: flex; align-items: center; justify-content: center; }
.rr-badge { display: inline-flex; align-items: center; gap: 8px; font-size: 14px; font-weight: 600; color: #46603E;
  background: #EAF0E4; padding: 8px 16px; border-radius: 999px; }
[data-testid="stMarkdownContainer"] .rr-hero h1 { margin: 32px 0 8px; padding: 0; font-size: 44px; line-height: 1.15;
  font-weight: 800; letter-spacing: -0.02em; }
.rr-hero p { margin: 0 0 16px; font-size: 18px; max-width: 560px; }
[data-testid="stMarkdownContainer"] .rr-section-title { margin: 24px 0 8px; padding: 0; font-size: 28px; line-height: 1.25;
  font-weight: 800; letter-spacing: -0.01em; }
.rr-summary { margin: 0 0 16px; font-size: 16px; max-width: 720px; }

.rr-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 24px; margin-bottom: 16px; }
.rr-card { background: #FFFFFF; border: 1px solid #F0E9DD; border-radius: 16px; padding: 24px; display: flex;
  flex-direction: column; gap: 16px; box-shadow: 0 1px 2px rgba(70,50,30,0.05), 0 8px 24px rgba(70,50,30,0.06); }
.rr-card-head { display: flex; gap: 16px; align-items: flex-start; }
.rr-rank { flex: none; width: 36px; height: 36px; border-radius: 999px; background: #FBEAE2; color: #8E3519;
  font-weight: 800; font-size: 16px; display: flex; align-items: center; justify-content: center; }
[data-testid="stMarkdownContainer"] .rr-name { margin: 0; padding: 0; font-size: 20px; line-height: 1.3; font-weight: 800; }
.rr-loc { display: inline-flex; align-items: center; gap: 4px; font-size: 14px; color: #6B655C; }
.rr-tags { display: flex; flex-wrap: wrap; gap: 8px; }
.rr-tag { font-size: 13px; font-weight: 700; color: #46603E; background: #EAF0E4; padding: 4px 12px; border-radius: 999px; }
.rr-meta { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; font-size: 14px; color: #6B655C; }
.rr-rating { display: inline-flex; align-items: center; gap: 4px; background: #557449; color: #FFFFFF; font-weight: 800;
  padding: 4px 12px; border-radius: 8px; }
.rr-rating.rr-unrated { background: #F5EFE5; color: #5A554D; }
.rr-price { font-size: 15px; font-weight: 800; color: #2B2A28; letter-spacing: 0.04em; }
.rr-price span { color: #CFC5B5; }
.rr-why { margin-top: auto; background: #FBF3EA; border-radius: 12px; padding: 16px; }
.rr-why-label { display: block; font-size: 12px; font-weight: 800; letter-spacing: 0.06em; text-transform: uppercase; color: #93431F; }
.rr-why p { margin: 4px 0 0; font-size: 15px; line-height: 1.6; color: #3D3A35; }

.rr-state { border-radius: 16px; padding: 48px 24px; display: flex; flex-direction: column; align-items: center;
  text-align: center; gap: 16px; margin: 24px 0; }
.rr-state-empty { border: 2px dashed #E4DCCF; }
.rr-state-error { background: #FFFFFF; border: 1px solid #F0E9DD; box-shadow: 0 1px 2px rgba(70,50,30,0.05), 0 8px 24px rgba(70,50,30,0.06); }
.rr-state-icon { width: 88px; height: 88px; border-radius: 999px; display: flex; align-items: center; justify-content: center; }
[data-testid="stMarkdownContainer"] .rr-state h2 { margin: 0; padding: 0; font-size: 24px; line-height: 1.3; font-weight: 800; }
.rr-state p { margin: 0; font-size: 16px; color: #6B655C; max-width: 460px; }
.rr-code { background: #F5EFE5; border-radius: 12px; padding: 16px 24px; font-size: 14px; color: #5A554D; }
.rr-code code { display: block; background: none; color: #2B2A28; font-size: 14px; padding: 0; }
.rr-footer { text-align: center; font-size: 14px; color: #6B655C; margin-top: 16px; }

@keyframes rr-pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.55; } }
.rr-sk { animation: rr-pulse 1.4s ease-in-out infinite; }
.rr-sk-bar { display: block; height: 14px; border-radius: 8px; background: #F2EBDF; }
@media (prefers-reduced-motion: reduce) { .rr-sk { animation: none; } }

@media (max-width: 640px) {
  [data-testid="stMainBlockContainer"] { padding: 16px 16px 48px; }
  .st-key-search { padding: 24px 16px; }
  [data-testid="stMarkdownContainer"] .rr-hero h1 { font-size: 32px; }
  .rr-card { padding: 24px 16px; }
}
</style>
"""


class BackendError(Exception):
    """A user-facing error message for anything that went wrong talking to the backend."""


@st.cache_data(ttl=300, show_spinner=False)
def fetch_options() -> dict:
    # Exceptions are not cached, so a down backend is retried on the next rerun.
    resp = httpx.get(f"{API_URL}/options", headers=API_HEADERS, timeout=10)
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
        resp = httpx.post(f"{API_URL}/recommendations", json=payload, headers=API_HEADERS,
                          timeout=REQUEST_TIMEOUT_S)
    except httpx.TimeoutException:
        raise BackendError("The request timed out. Please try again.")
    except httpx.HTTPError:
        raise BackendError(f"Backend not reachable at {API_URL}. Is it still running?")
    if 400 <= resp.status_code < 500:
        raise BackendError(_error_detail(resp))
    if resp.status_code >= 500:
        raise BackendError("Something went wrong on the server. Please try again.")
    return resp.json()


def esc(text) -> str:
    # `$` would otherwise start LaTeX in st.markdown.
    return html.escape(str(text)).replace("$", "&#36;")


def show_html(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


def price_level(cost: int) -> int:
    # Same bands as the backend budget filter: low ≤ 300, medium 301–700, high > 700.
    return 1 if cost <= 300 else 2 if cost <= 700 else 3


def header_html() -> str:
    return (f'<div class="rr-header"><div class="rr-brand"><span class="rr-logo">{ICON_LOGO}</span>'
            f'Restaurant Recommender</div><span class="rr-badge">{ICON_PIN} Bangalore</span></div>'
            '<div class="rr-hero"><h1>Find your next favourite meal</h1>'
            '<p class="rr-muted">Tell us where you are and what you\'re craving. '
            'We\'ll pick five places worth trying, and tell you why.</p></div>')


def card_html(item: dict, show_explanation: bool) -> str:
    tags = "".join(f'<span class="rr-tag">{esc(c.title())}</span>' for c in item["cuisines"])
    if item["rating"] is not None:
        rating = f'<span class="rr-rating">{ICON_STAR} {item["rating"]:.1f}</span>'
    else:
        rating = '<span class="rr-rating rr-unrated">Unrated</span>'
    if item["cost_for_two"] is not None:
        level = price_level(item["cost_for_two"])
        cost = (f'<span class="rr-price" aria-hidden="true">{"₹" * level}<span>{"₹" * (3 - level)}</span></span>'
                f'<span>₹{item["cost_for_two"]:,} for two</span>')
    else:
        cost = "<span>Cost N/A</span>"
    why = ""
    if show_explanation and item.get("explanation"):
        why = (f'<div class="rr-why"><span class="rr-why-label">Why we picked this</span>'
               f'<p>{esc(item["explanation"])}</p></div>')
    return (f'<article class="rr-card"><div class="rr-card-head"><span class="rr-rank">{item["rank"]}</span>'
            f'<div><h3 class="rr-name">{esc(item["name"])}</h3>'
            f'<span class="rr-loc">{ICON_PIN} {esc(item["location"])}</span></div></div>'
            f'<div class="rr-tags">{tags}</div><div class="rr-meta">{rating}{cost}</div>{why}</article>')


def skeleton_html(count: int = 5) -> str:
    bar = '<span class="rr-sk-bar" style="width:{w}%;{extra}"></span>'
    card = ('<div class="rr-card rr-sk" aria-hidden="true">'
            + bar.format(w=70, extra="height:20px") + bar.format(w=40, extra="")
            + bar.format(w=50, extra="height:28px;background:#EEF2E9;border-radius:999px")
            + '<div class="rr-why" style="background:#FBF6F0">' + bar.format(w=100, extra="margin-bottom:8px")
            + bar.format(w=85, extra="") + '</div></div>')
    return ('<h2 class="rr-section-title">Picking your top 5…</h2>'
            '<p class="rr-summary rr-muted" role="status">Checking menus and ratings. '
            'This usually takes a few seconds.</p>'
            f'<div class="rr-grid" aria-busy="true">{card * count}</div>')


def render_empty_state() -> None:
    show_html(f'<div class="rr-state rr-state-empty"><span class="rr-state-icon" style="background:#EAF0E4">'
              f'{ICON_PLATE}</span><h2>Your table is waiting</h2><p>Pick a neighbourhood and a craving above, '
              'then tap <strong style="color:#2B2A28">Find restaurants</strong>. '
              'Your top five picks will appear here.</p></div>')


def render_backend_down() -> None:
    show_html(f'<div class="rr-state rr-state-error" role="alert"><span class="rr-state-icon" '
              f'style="background:#FBEAE2">{ICON_UNPLUGGED}</span><h2>We can\'t reach the kitchen right now</h2>'
              f'<p>Backend not reachable at {esc(API_URL)}. It may still be starting up. '
              'Give it a moment, then try again.</p>'
              '<div class="rr-code">Running it locally? Start the backend with'
              '<code>uvicorn backend.api:app --port 8000</code></div></div>')
    st.button("Try again", type="primary", icon=":material/refresh:", width="stretch")


def render_results(data: dict, location: str) -> None:
    recs = data["recommendations"]
    if not recs:
        for note in data["notes"]:
            st.info(note)
        show_html(f'<div class="rr-state rr-state-empty"><span class="rr-state-icon" style="background:#EAF0E4">'
                  f'{ICON_PLATE}</span><h2>No matches this time</h2><p>Try a different budget or cuisine, '
                  'or a lower minimum rating.</p></div>')
        return
    show_html(f'<h2 class="rr-section-title">Your top {len(recs)} in {esc(location)}</h2>'
              + (f'<p class="rr-summary rr-muted">{esc(data["summary"])}</p>' if data.get("summary") else ""))
    if data["degraded"]:
        st.warning("AI explanations are unavailable right now, so these are the top-rated matches.")
    for note in data["notes"]:
        st.info(note)
    cards = "".join(card_html(item, show_explanation=not data["degraded"]) for item in recs)
    show_html(f'<div class="rr-grid">{cards}</div>'
              f'<p class="rr-footer">Ranked from {data["candidates_considered"]} matching restaurants</p>')


def search_panel(options: dict) -> tuple[dict, bool]:
    locations = options["locations"]
    all_cuisines = options["cuisines"]
    popular = [c for c in POPULAR_CUISINES if c in all_cuisines]
    others = [c for c in all_cuisines if c not in popular]

    with st.container(key="search"):
        left, right = st.columns(2, gap="medium")
        location = left.selectbox(
            "Location", locations,
            index=locations.index(DEFAULT_LOCATION) if DEFAULT_LOCATION in locations else 0,
        )
        budget = right.segmented_control("Budget · cost for two", list(BUDGETS), default="medium", required=True,
                                         format_func=BUDGETS.get, width="stretch")
        picked = st.pills("Cuisines · pick any, or leave blank for all", popular, selection_mode="multi",
                          format_func=str.title)
        more = []
        if others:
            with st.expander("More cuisines"):
                more = st.multiselect("Other cuisines", others, format_func=str.title,
                                      label_visibility="collapsed", placeholder="Search all cuisines")
        left, right = st.columns(2, gap="medium")
        min_rating = left.segmented_control("Minimum rating", RATINGS, default=DEFAULT_RATING, required=True,
                                            format_func=lambda r: "Any" if r == 0 else f"{r:.1f}+",
                                            width="stretch")
        preference = right.text_input("Anything else? · optional", max_chars=300,
                                      placeholder="e.g. family-friendly, quick service, delivery")
        submitted = st.button("Find restaurants", type="primary", icon=":material/search:", width="stretch")

    payload = {"location": location, "budget": budget, "cuisines": list(picked) + list(more),
               "min_rating": min_rating, "preference": preference}
    return payload, submitted


def main() -> None:
    st.set_page_config(page_title="Restaurant Recommender", page_icon="🍽️", layout="centered")
    show_html(CSS)
    show_html(header_html())

    try:
        options = fetch_options()
    except httpx.HTTPError:
        render_backend_down()
        st.stop()

    payload, submitted = search_panel(options)

    if submitted:
        loading = st.empty()
        loading.markdown(skeleton_html(), unsafe_allow_html=True)
        try:
            st.session_state["result"] = get_recommendations(payload)
            st.session_state["searched_location"] = payload["location"]
            st.session_state.pop("error", None)
        except BackendError as exc:
            st.session_state["error"] = str(exc)
            st.session_state.pop("result", None)
        loading.empty()

    if "error" in st.session_state:
        st.error(st.session_state["error"], icon=":material/error:")
    elif "result" in st.session_state:
        render_results(st.session_state["result"], st.session_state["searched_location"])
    else:
        render_empty_state()

    show_html('<p class="rr-footer">Data covers Bangalore only.</p>')


main()
