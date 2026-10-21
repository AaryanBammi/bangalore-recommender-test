"use client";

import { useState } from "react";
import type { Budget, Options, RecommendationRequest } from "@/lib/types";
import { SearchIcon } from "./Icons";
import { titleCase } from "./ResultCard";

const DEFAULT_LOCATION = "Indiranagar";
// Shown as chips; every other cuisine sits under "More cuisines".
export const POPULAR_CUISINES = ["north indian", "south indian", "chinese", "cafe", "biryani",
  "fast food", "continental", "italian", "desserts", "street food"];
const BUDGETS: [Budget, string][] = [["low", "Under ₹300"], ["medium", "₹300–700"], ["high", "₹700+"]];
const RATINGS = [0, 3.5, 4, 4.5];
const DEFAULT_RATING = 3.5;

function Segmented<T extends string | number>({ legend, name, options, value, onChange }: {
  legend: string;
  name: string;
  options: [T, string][];
  value: T;
  onChange: (value: T) => void;
}) {
  return (
    <fieldset className="rr-field">
      <legend className="rr-label">{legend}</legend>
      <div className="rr-segmented">
        {options.map(([option, label]) => (
          <label key={String(option)}>
            <input type="radio" name={name} checked={value === option} onChange={() => onChange(option)} />
            <span>{label}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

function Chip({ cuisine, selected, onToggle }: { cuisine: string; selected: boolean; onToggle: () => void }) {
  return (
    <button type="button" className="rr-chip" aria-pressed={selected} onClick={onToggle}>
      {titleCase(cuisine)}
    </button>
  );
}

export function SearchPanel({ options, busy, onSubmit }: {
  options: Options;
  busy: boolean;
  onSubmit: (payload: RecommendationRequest) => void;
}) {
  const { locations, cuisines } = options;
  const popular = POPULAR_CUISINES.filter((c) => cuisines.includes(c));
  const others = cuisines.filter((c) => !popular.includes(c));

  const [location, setLocation] = useState(locations.includes(DEFAULT_LOCATION) ? DEFAULT_LOCATION : locations[0]);
  const [budget, setBudget] = useState<Budget>("medium");
  const [picked, setPicked] = useState<string[]>([]);
  const [minRating, setMinRating] = useState(DEFAULT_RATING);
  const [preference, setPreference] = useState("");
  const [moreQuery, setMoreQuery] = useState("");

  const toggle = (c: string) => setPicked((p) => (p.includes(c) ? p.filter((x) => x !== c) : [...p, c]));
  const pickedOthers = picked.filter((c) => others.includes(c)).length;
  const query = moreQuery.trim().toLowerCase();
  const shownOthers = others.filter((c) => c.includes(query));

  function submit(e: React.FormEvent) {
    e.preventDefault();
    // Popular picks first, in chip order, then the rest in the order chosen.
    const ordered = [...popular.filter((c) => picked.includes(c)), ...picked.filter((c) => !popular.includes(c))];
    onSubmit({ location, budget, cuisines: ordered, min_rating: minRating, preference });
  }

  return (
    <form className="rr-search" onSubmit={submit} aria-label="Search restaurants">
      <div className="rr-row">
        <div className="rr-field">
          <label className="rr-label" htmlFor="rr-location">Location</label>
          <select id="rr-location" className="rr-select" value={location} onChange={(e) => setLocation(e.target.value)}>
            {locations.map((l) => <option key={l} value={l}>{l}</option>)}
          </select>
        </div>
        <Segmented legend="Budget · cost for two" name="budget" options={BUDGETS} value={budget} onChange={setBudget} />
      </div>

      <fieldset className="rr-field">
        <legend className="rr-label">Cuisines · pick any, or leave blank for all</legend>
        <div className="rr-chips">
          {popular.map((c) => <Chip key={c} cuisine={c} selected={picked.includes(c)} onToggle={() => toggle(c)} />)}
        </div>
        {others.length > 0 && (
          <details className="rr-more">
            <summary>More cuisines{pickedOthers > 0 && ` · ${pickedOthers} selected`}</summary>
            <input type="search" className="rr-input" placeholder="Search all cuisines" aria-label="Search all cuisines"
              value={moreQuery} onChange={(e) => setMoreQuery(e.target.value)} />
            <div className="rr-chips rr-chips-scroll">
              {shownOthers.map((c) => <Chip key={c} cuisine={c} selected={picked.includes(c)} onToggle={() => toggle(c)} />)}
              {shownOthers.length === 0 && <span className="rr-muted">No cuisines match “{moreQuery}”.</span>}
            </div>
          </details>
        )}
      </fieldset>

      <div className="rr-row">
        <Segmented legend="Minimum rating" name="min_rating" value={minRating} onChange={setMinRating}
          options={RATINGS.map((r): [number, string] => [r, r === 0 ? "Any" : `${r.toFixed(1)}+`])} />
        <div className="rr-field">
          <label className="rr-label" htmlFor="rr-preference">Anything else? · optional</label>
          <input id="rr-preference" className="rr-input" maxLength={300} value={preference}
            placeholder="e.g. family-friendly, quick service, delivery" onChange={(e) => setPreference(e.target.value)} />
        </div>
      </div>

      <button type="submit" className="rr-primary" disabled={busy}>
        <SearchIcon /> {busy ? "Finding restaurants…" : "Find restaurants"}
      </button>
    </form>
  );
}
