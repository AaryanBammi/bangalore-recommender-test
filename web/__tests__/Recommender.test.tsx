// Port of tests/test_frontend.py: the UI with /api/* faked.

import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Recommender } from "@/components/Recommender";
import type { RecommendationItem, RecommendationResponse } from "@/lib/types";

const OPTIONS = { locations: ["BTM", "Indiranagar"], cuisines: ["afghan", "chinese", "north indian"] };

function item(rank: number, overrides: Partial<RecommendationItem> = {}): RecommendationItem {
  return { rank, name: `Place ${rank}`, cuisines: ["north indian"], rating: 4.2, cost_for_two: 500,
    location: "Indiranagar", explanation: "Fits your budget.", ...overrides };
}

function result(overrides: Partial<RecommendationResponse> = {}): RecommendationResponse {
  return { recommendations: [1, 2, 3, 4, 5].map((i) => item(i)), summary: "Great picks.",
    candidates_considered: 8, notes: [], degraded: false, ...overrides };
}

/** Stands in for fetch. `post` is a response body (200), a Response, or an Error to throw. */
function fakeBackend({ options = OPTIONS as unknown, post = result() as unknown } = {}) {
  const posted: unknown[] = [];
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const reply = url === "/api/options" ? options : post;
    if (url === "/api/recommendations") posted.push(JSON.parse(String(init?.body)));
    if (reply instanceof Error) throw reply;
    if (reply instanceof Response) return reply;
    return Response.json(reply);
  });
  vi.stubGlobal("fetch", fetchMock);
  return { fetchMock, posted };
}

async function renderAndSubmit() {
  const user = userEvent.setup();
  render(<Recommender />);
  await user.click(await screen.findByRole("button", { name: /find restaurants/i }));
  return user;
}

beforeEach(() => vi.unstubAllGlobals());
afterEach(() => vi.unstubAllGlobals());

describe("Recommender", () => {
  it("fills the form from /options", async () => {
    fakeBackend();
    render(<Recommender />);
    const location = await screen.findByLabelText("Location");
    expect(within(location).getAllByRole("option").map((o) => o.textContent)).toEqual(["BTM", "Indiranagar"]);
    expect(location).toHaveValue("Indiranagar");
    expect(screen.getByRole("button", { name: "Chinese" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "North Indian" })).toBeInTheDocument();
    expect(screen.getByText("More cuisines")).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "₹300–700" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "3.5+" })).toBeChecked();
  });

  it("shows the welcome state before searching", async () => {
    fakeBackend();
    render(<Recommender />);
    expect(await screen.findByText("Your table is waiting")).toBeInTheDocument();
  });

  it("sends the selected cuisines", async () => {
    const { posted } = fakeBackend();
    const user = userEvent.setup();
    render(<Recommender />);
    await user.click(await screen.findByRole("button", { name: "Chinese" }));
    await user.click(screen.getByText("More cuisines"));
    await user.click(screen.getByRole("button", { name: "Afghan" }));
    await user.click(screen.getByRole("button", { name: /find restaurants/i }));
    await screen.findByText("Place 1");
    expect(posted[0]).toMatchObject({ cuisines: ["chinese", "afghan"] });
  });

  it("submits the default payload and renders cards", async () => {
    const { posted } = fakeBackend();
    await renderAndSubmit();
    expect(await screen.findByText("Your top 5 in Indiranagar")).toBeInTheDocument();
    expect(posted[0]).toEqual({ location: "Indiranagar", budget: "medium", cuisines: [], min_rating: 3.5, preference: "" });
    expect(screen.getAllByRole("article")).toHaveLength(5);
    expect(screen.getByText("Great picks.")).toBeInTheDocument();
    expect(screen.getAllByText("Why we picked this")).toHaveLength(5);
    expect(screen.getAllByText("₹500 for two")).toHaveLength(5);
    expect(screen.getByText("Ranked from 8 matching restaurants")).toBeInTheDocument();
  });

  it("shows a null rating and cost as text", async () => {
    fakeBackend({ post: result({ recommendations: [item(1, { rating: null, cost_for_two: null })] }) });
    await renderAndSubmit();
    expect(await screen.findByText("Unrated")).toBeInTheDocument();
    expect(screen.getByText("Cost N/A")).toBeInTheDocument();
  });

  it("shows a banner and hides explanations when degraded", async () => {
    fakeBackend({ post: result({ degraded: true, summary: null }) });
    await renderAndSubmit();
    expect(await screen.findByText(/AI explanations are unavailable/)).toBeInTheDocument();
    expect(screen.queryByText("Why we picked this")).not.toBeInTheDocument();
  });

  it("shows notes as info banners", async () => {
    fakeBackend({ post: result({ notes: ["Relaxed budget to find more matches."] }) });
    await renderAndSubmit();
    expect(await screen.findByText("Relaxed budget to find more matches.")).toBeInTheDocument();
  });

  it("shows the no-matches state with notes", async () => {
    fakeBackend({ post: result({ recommendations: [], candidates_considered: 0, notes: ["Lowered rating to 3.0."] }) });
    await renderAndSubmit();
    expect(await screen.findByText("No matches this time")).toBeInTheDocument();
    expect(screen.getByText("Lowered rating to 3.0.")).toBeInTheDocument();
  });

  it("explains a slow first load while the backend wakes up", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));
      render(<Recommender />);
      expect(screen.getByRole("status")).toHaveTextContent("Loading neighbourhoods…");
      await act(() => vi.advanceTimersByTimeAsync(5_000));
      expect(screen.getByRole("status")).toHaveTextContent("Waking up the server");
    } finally {
      vi.useRealTimers();
    }
  });

  it("shows the backend-down state on load and retries", async () => {
    const { fetchMock } = fakeBackend({ options: Response.json({ detail: "Backend is unreachable." }, { status: 502 }) });
    const user = userEvent.setup();
    render(<Recommender />);
    expect(await screen.findByText("We can't reach the kitchen right now")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /find restaurants/i })).not.toBeInTheDocument();

    fetchMock.mockImplementation(async () => Response.json(OPTIONS));
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("button", { name: /find restaurants/i })).toBeInTheDocument();
  });

  it("shows an error when the network fails on submit", async () => {
    fakeBackend({ post: new TypeError("Failed to fetch") });
    await renderAndSubmit();
    expect(await screen.findByRole("alert")).toHaveTextContent("We couldn't reach the server");
  });

  it("shows the kitchen message when the backend is down on submit", async () => {
    fakeBackend({ post: Response.json({ detail: "Backend is unreachable." }, { status: 502 }) });
    await renderAndSubmit();
    expect(await screen.findByRole("alert")).toHaveTextContent("may still be starting up");
  });

  it("shows a timeout message", async () => {
    fakeBackend({ post: Response.json({ detail: "The backend timed out." }, { status: 504 }) });
    await renderAndSubmit();
    expect(await screen.findByRole("alert")).toHaveTextContent("The request timed out. Please try again.");
  });

  it("shows the API's 400 detail", async () => {
    fakeBackend({ post: Response.json({ detail: "Unknown location. Data covers Bangalore only." }, { status: 400 }) });
    await renderAndSubmit();
    expect(await screen.findByRole("alert")).toHaveTextContent("Unknown location. Data covers Bangalore only.");
  });

  it("makes a 422 validation detail readable", async () => {
    const detail = [{ loc: ["body", "min_rating"], msg: "Input should be less than or equal to 5", type: "x" }];
    fakeBackend({ post: Response.json({ detail }, { status: 422 }) });
    await renderAndSubmit();
    expect(await screen.findByRole("alert")).toHaveTextContent("min_rating: Input should be less than or equal to 5");
  });

  it("shows a generic message for a 500", async () => {
    fakeBackend({ post: new Response("Internal Server Error", { status: 500 }) });
    await renderAndSubmit();
    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong on the server. Please try again.");
  });
});
