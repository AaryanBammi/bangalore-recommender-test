"""Phase 0 data check: verify dataset assumptions in docs/context.md §3.2.

Run: .venv/bin/python scripts/data_check.py
"""

import re

import pandas as pd

PARQUET_DIR = "hf://datasets/ManikaSaini/zomato-restaurant-recommendation@~parquet/default/train"
SOURCES = [f"{PARQUET_DIR}/0000.parquet", f"{PARQUET_DIR}/0001.parquet"]
COLUMNS = [
    "name", "address", "location", "listed_in(city)", "cuisines", "rate", "votes",
    "approx_cost(for two people)", "rest_type", "dish_liked", "online_order", "book_table",
]
RATE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*/\s*5\s*$")


def section(title):
    print(f"\n=== {title} ===")


def main():
    df = pd.concat([pd.read_parquet(src, columns=COLUMNS) for src in SOURCES], ignore_index=True)

    section("Shape and nulls")
    print(f"raw rows: {len(df):,}")
    print(df.isna().sum().to_string())

    section("rate: values that don't match 'X.X/5'")
    rate = df["rate"].astype("string")
    numeric = rate.str.match(RATE_RE, na=False)
    print(rate[~numeric].value_counts(dropna=False).to_string())
    spaced = rate[numeric & rate.str.contains(r"\s", na=False)]
    print(f"numeric rates containing whitespace: {len(spaced):,} (e.g. {spaced.head(3).tolist()})")
    parsed = rate.str.extract(RATE_RE)[0].astype(float)
    print(f"parsed rating range: {parsed.min()} – {parsed.max()}")

    section("approx_cost(for two people)")
    cost = df["approx_cost(for two people)"].astype("string")
    print(f"values with commas: {cost.str.contains(',', na=False).sum():,} (e.g. {cost[cost.str.contains(',', na=False)].head(3).tolist()})")
    cost_num = pd.to_numeric(cost.str.replace(",", "", regex=False), errors="coerce")
    print(f"unparseable/null: {cost_num.isna().sum():,} | zero: {(cost_num == 0).sum():,}")
    print("quantiles:")
    print(cost_num.quantile([0.1, 0.25, 0.5, 0.75, 0.9, 0.99]).to_string())

    section("Dedup on (name, address)")
    norm_addr = df["address"].astype("string").str.lower().str.split().str.join(" ")
    dedup = df.assign(_addr=norm_addr).drop_duplicates(subset=["name", "_addr"])
    print(f"raw: {len(df):,} -> dedup on (name, address): {len(df.drop_duplicates(subset=['name', 'address'])):,}")
    print(f"dedup on (name, normalized address): {len(dedup):,}")
    dups = df.groupby(["name", "address"]).agg(rate_n=("rate", "nunique"), votes_n=("votes", "nunique"))
    print(f"duplicate groups with differing rate: {(dups.rate_n > 1).sum():,}, differing votes: {(dups.votes_n > 1).sum():,}")

    section("Budget tiers on dedup rows (<=300 low, <=700 medium, >700 high)")
    dcost = pd.to_numeric(dedup["approx_cost(for two people)"].astype("string").str.replace(",", "", regex=False), errors="coerce")
    tiers = pd.cut(dcost, bins=[0, 300, 700, float("inf")], labels=["low", "medium", "high"])
    print(tiers.value_counts(normalize=True, dropna=False).round(3).to_string())

    section("Locations")
    print(f"distinct location: {df['location'].nunique()} | distinct listed_in(city): {df['listed_in(city)'].nunique()}")
    print(f"locations with < 20 dedup restaurants: {(dedup['location'].value_counts() < 20).sum()}")

    section("Other fields")
    for col in ["online_order", "book_table"]:
        print(f"{col}: {df[col].value_counts(dropna=False).to_dict()}")
    for col in ["dish_liked", "rest_type", "cuisines"]:
        print(f"literal 'null' strings in {col}: {(df[col].astype('string').str.strip().str.lower() == 'null').sum():,}")
    mojibake = df["name"].astype("string").str.contains("Ã|Â", na=False)
    print(f"names with mojibake markers: {mojibake.sum():,} (e.g. {df['name'][mojibake].drop_duplicates().head(3).tolist()})")
    cuisines = df["cuisines"].dropna().str.split(",").explode().str.strip().str.lower()
    print(f"distinct cuisines: {cuisines.nunique()}")


if __name__ == "__main__":
    main()
