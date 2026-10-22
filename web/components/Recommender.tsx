"use client";

import { useCallback, useEffect, useState } from "react";
import { BackendError, fetchOptions, getRecommendations } from "@/lib/api";
import type { Options, RecommendationRequest, RecommendationResponse } from "@/lib/types";
import { SearchPanel } from "./SearchPanel";
import { BackendDown, Banner, Header, Results, Skeleton, WelcomeState } from "./States";

// After this long, the backend is probably waking from sleep (deployment.md D2).
const SLOW_LOAD_MS = 5_000;

type View =
  | { kind: "welcome" }
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "results"; data: RecommendationResponse; location: string };

export function Recommender() {
  const [options, setOptions] = useState<Options | null>(null);
  const [optionsFailed, setOptionsFailed] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [view, setView] = useState<View>({ kind: "welcome" });
  const [slowLoad, setSlowLoad] = useState(false);

  const loadOptions = useCallback(async () => {
    setRetrying(true);
    try {
      setOptions(await fetchOptions());
      setOptionsFailed(false);
    } catch {
      setOptionsFailed(true);
    } finally {
      setRetrying(false);
    }
  }, []);

  useEffect(() => {
    loadOptions();
  }, [loadOptions]);

  const waiting = !options && !optionsFailed;
  useEffect(() => {
    if (!waiting) return;
    const timer = setTimeout(() => setSlowLoad(true), SLOW_LOAD_MS);
    return () => clearTimeout(timer);
  }, [waiting]);

  async function search(payload: RecommendationRequest) {
    setView({ kind: "loading" });
    try {
      setView({ kind: "results", data: await getRecommendations(payload), location: payload.location });
    } catch (err) {
      setView({ kind: "error", message: err instanceof BackendError ? err.message : "Something went wrong. Please try again." });
    }
  }

  return (
    <main className="rr-main">
      <Header />
      {optionsFailed ? (
        <BackendDown onRetry={loadOptions} retrying={retrying} />
      ) : !options ? (
        <p className="rr-muted" role="status">
          {slowLoad ? "Waking up the server. This can take up to a minute after a quiet spell…" : "Loading neighbourhoods…"}
        </p>
      ) : (
        <>
          <SearchPanel options={options} busy={view.kind === "loading"} onSubmit={search} />
          {view.kind === "welcome" && <WelcomeState />}
          {view.kind === "loading" && <Skeleton />}
          {view.kind === "error" && <Banner kind="error">{view.message}</Banner>}
          {view.kind === "results" && <Results data={view.data} location={view.location} />}
        </>
      )}
      <p className="rr-footer">Data covers Bangalore only.</p>
    </main>
  );
}
