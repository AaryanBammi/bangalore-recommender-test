"""Ingestion and in-memory catalogue (architecture §2.1, context §3–§4)."""

import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import ftfy
import pandas as pd

log = logging.getLogger(__name__)

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "restaurants.parquet"
HF_PARQUET_DIR = "hf://datasets/ManikaSaini/zomato-restaurant-recommendation@~parquet/default/train"
HF_SOURCES = [f"{HF_PARQUET_DIR}/0000.parquet", f"{HF_PARQUET_DIR}/0001.parquet"]

# Budget tiers on cost for two (INR), revised in Phase 0 (context §5).
BUDGET_LOW_MAX = 300
BUDGET_MEDIUM_MAX = 700

RAW_COLUMNS = {
    "name": "name",
    "address": "address",
    "location": "location",
    "listed_in(city)": "zone",
    "cuisines": "cuisines",
    "rate": "rate",
    "votes": "votes",
    "approx_cost(for two people)": "cost_for_two",
    "rest_type": "rest_type",
    "listed_in(type)": "listing_type",
    "online_order": "online_order",
    "book_table": "book_table",
    "dish_liked": "dish_liked",
}
LIST_COLUMNS = ["cuisines", "rest_type", "listing_types", "dish_liked"]

_RATE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*/\s*5\s*$")


def parse_rate(value) -> float | None:
    """'4.1/5' or '4.1 /5' -> 4.1. 'NEW', '-', nulls and out-of-range values -> None."""
    if not isinstance(value, str):
        return None
    match = _RATE_RE.match(value)
    if not match:
        return None
    rating = float(match.group(1))
    return rating if 0 <= rating <= 5 else None


def parse_cost(value) -> int | None:
    """'800' -> 800, '1,200' -> 1200. Nulls, junk and 0 -> None."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        cost = int(float(str(value).replace(",", "").strip()))
    except ValueError:
        return None
    return cost if cost > 0 else None


def budget_tier(cost: int | None) -> str | None:
    if cost is None:
        return None
    if cost <= BUDGET_LOW_MAX:
        return "low"
    if cost <= BUDGET_MEDIUM_MAX:
        return "medium"
    return "high"


def split_list(value, lower: bool = True) -> list[str]:
    """'North Indian, Chinese,' -> ['north indian', 'chinese'] (trimmed, deduped, order kept)."""
    if not isinstance(value, str) or value.strip().lower() == "null":
        return []
    items = []
    for part in value.split(","):
        part = ftfy.fix_text(part).strip()
        if lower:
            part = part.lower()
        if part and part not in items:
            items.append(part)
    return items


def _text(value) -> str:
    if not isinstance(value, str) or value.strip().lower() == "null":
        return ""
    return " ".join(ftfy.fix_text(value).split())


def _make_id(name: str, address_key: str) -> str:
    digest = hashlib.sha1(f"{name.lower()}|{address_key}".encode()).hexdigest()
    return f"r_{digest[:10]}"


def clean(raw: pd.DataFrame) -> pd.DataFrame:
    """Turn raw dataset rows into one clean row per restaurant."""
    missing = set(RAW_COLUMNS) - set(raw.columns)
    if missing:
        raise ValueError(f"Dataset is missing expected columns: {sorted(missing)}")

    df = raw[list(RAW_COLUMNS)].rename(columns=RAW_COLUMNS).copy()
    for col in ["name", "address", "location", "zone", "listing_type"]:
        df[col] = df[col].map(_text)
    df = df[(df["name"] != "") & (df["location"] != "")].copy()

    df["rating"] = df["rate"].map(parse_rate)
    df["cost_for_two"] = df["cost_for_two"].map(parse_cost)
    df["votes"] = pd.to_numeric(df["votes"], errors="coerce").fillna(0).astype(int)
    df["cuisines"] = df["cuisines"].map(split_list)
    df["rest_type"] = df["rest_type"].map(split_list)
    df["dish_liked"] = df["dish_liked"].map(lambda v: split_list(v, lower=False))
    for col in ["online_order", "book_table"]:
        df[col] = df[col].map(lambda v: isinstance(v, str) and v.strip().lower() == "yes")

    # Dedupe on (name, normalized address); keep the most-voted snapshot, merge listing types.
    df["_key"] = df["name"].str.lower() + "|" + df["address"].str.lower()
    listing_types = df.groupby("_key")["listing_type"].agg(lambda s: sorted({t for t in s if t}))
    df = df.sort_values("votes", ascending=False, kind="stable").drop_duplicates("_key")
    df["listing_types"] = df["_key"].map(listing_types)

    df["id"] = [_make_id(n, a.lower()) for n, a in zip(df["name"], df["address"])]
    if df["id"].duplicated().any():
        raise ValueError("Restaurant id collision after dedupe")
    df["budget_tier"] = df["cost_for_two"].map(budget_tier)
    df["cost_for_two"] = df["cost_for_two"].astype("Int64")

    columns = [
        "id", "name", "address", "location", "zone", "cuisines", "rating", "votes",
        "cost_for_two", "budget_tier", "rest_type", "listing_types", "online_order",
        "book_table", "dish_liked",
    ]
    return df[columns].reset_index(drop=True)


@dataclass
class Catalogue:
    df: pd.DataFrame

    def __post_init__(self):
        self._locations = {loc.lower(): loc for loc in self.df["location"].unique()}
        self._cuisines = sorted({c for cs in self.df["cuisines"] for c in cs})

    def __len__(self) -> int:
        return len(self.df)

    def locations(self) -> list[str]:
        return sorted(self._locations.values())

    def cuisines(self) -> list[str]:
        return self._cuisines

    def resolve_location(self, value: str) -> str | None:
        """Case/whitespace-insensitive match to the canonical locality name."""
        return self._locations.get(" ".join(value.split()).lower())


def _download_raw() -> pd.DataFrame:
    log.info("Downloading dataset from Hugging Face (first run only)...")
    return pd.concat(
        [pd.read_parquet(src, columns=list(RAW_COLUMNS)) for src in HF_SOURCES],
        ignore_index=True,
    )


def load_catalogue(path: Path = DATA_PATH) -> Catalogue:
    """Load the cleaned catalogue, building and caching it on first run."""
    if path.exists():
        try:
            df = pd.read_parquet(path)
        except Exception as exc:
            raise RuntimeError(f"Could not read {path}; delete it to re-ingest.") from exc
        for col in LIST_COLUMNS:  # Parquet returns arrays; restore plain lists.
            df[col] = df[col].map(list)
        return Catalogue(df)

    try:
        raw = _download_raw()
    except Exception as exc:
        raise RuntimeError(
            "Could not download the dataset; check your network or place "
            f"{path.name} in {path.parent} manually."
        ) from exc
    df = clean(raw)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".parquet.tmp")
    df.to_parquet(tmp, index=False)
    tmp.replace(path)
    log.info("Saved %d restaurants to %s", len(df), path)
    return Catalogue(df)
