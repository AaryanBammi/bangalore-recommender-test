// Browser-side calls to our own /api/* route handlers, with user-facing error messages.

import type { Options, RecommendationRequest, RecommendationResponse } from "./types";

export class BackendError extends Error {}

export async function fetchOptions(): Promise<Options> {
  const resp = await fetch("/api/options");
  if (!resp.ok) throw new BackendError(`HTTP ${resp.status}`);
  return resp.json();
}

async function errorDetail(resp: Response): Promise<string> {
  let detail: unknown;
  try {
    detail = (await resp.json()).detail;
  } catch {
    return `HTTP ${resp.status}`;
  }
  if (Array.isArray(detail)) {
    // FastAPI validation errors: [{loc: ["body", "min_rating"], msg: "..."}]
    return detail.map((e) => `${(e.loc ?? []).slice(1).join(".")}: ${e.msg}`).join("; ");
  }
  return String(detail);
}

export async function getRecommendations(payload: RecommendationRequest): Promise<RecommendationResponse> {
  let resp: Response;
  try {
    resp = await fetch("/api/recommendations", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch {
    throw new BackendError("We couldn't reach the server. Check your connection and try again.");
  }
  if (resp.status === 504) throw new BackendError("The request timed out. Please try again.");
  if (resp.status === 502) {
    throw new BackendError("We can't reach the kitchen right now. It may still be starting up, so try again in a moment.");
  }
  if (resp.status >= 400 && resp.status < 500) throw new BackendError(await errorDetail(resp));
  if (resp.status >= 500) throw new BackendError("Something went wrong on the server. Please try again.");
  return resp.json();
}
