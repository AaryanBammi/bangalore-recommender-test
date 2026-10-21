// @vitest-environment node
// Route handlers: the server-side proxy to the FastAPI backend.

import { afterEach, describe, expect, it, vi } from "vitest";
import { GET as getOptions } from "@/app/api/options/route";
import { POST as postRecommendations } from "@/app/api/recommendations/route";

function stubBackend(reply: Response | Error) {
  const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => {
    if (reply instanceof Error) throw reply;
    return reply;
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function recommend(body: unknown = { location: "Indiranagar" }) {
  return postRecommendations(new Request("http://localhost/api/recommendations", {
    method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body),
  }));
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("route handlers", () => {
  it("forwards to BACKEND_URL with the API key and body", async () => {
    vi.stubEnv("BACKEND_URL", "https://api.example.com/");
    vi.stubEnv("BACKEND_API_KEY", "s3cret");
    const fetchMock = stubBackend(Response.json({ recommendations: [] }));

    const resp = await recommend({ location: "BTM" });

    expect(resp.status).toBe(200);
    expect(await resp.json()).toEqual({ recommendations: [] });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("https://api.example.com/recommendations");
    expect(new Headers(init?.headers).get("X-API-Key")).toBe("s3cret");
    expect(init?.body).toBe(JSON.stringify({ location: "BTM" }));
  });

  it("sends no API key header when none is configured", async () => {
    vi.stubEnv("BACKEND_URL", "http://localhost:8000");
    vi.stubEnv("BACKEND_API_KEY", "");
    const fetchMock = stubBackend(Response.json({ locations: [], cuisines: [] }));

    const resp = await getOptions();

    expect(resp.status).toBe(200);
    expect(resp.headers.get("cache-control")).toContain("s-maxage=300");
    expect(new Headers(fetchMock.mock.calls[0][1]?.headers).has("X-API-Key")).toBe(false);
  });

  it("passes 4xx responses through", async () => {
    vi.stubEnv("BACKEND_URL", "http://localhost:8000");
    stubBackend(Response.json({ detail: "Unknown location." }, { status: 400 }));

    const resp = await recommend();

    expect(resp.status).toBe(400);
    expect(await resp.json()).toEqual({ detail: "Unknown location." });
  });

  it("does not cache failed options", async () => {
    vi.stubEnv("BACKEND_URL", "http://localhost:8000");
    stubBackend(new Response("boom", { status: 500 }));

    const resp = await getOptions();

    expect(resp.status).toBe(500);
    expect(resp.headers.get("cache-control")).toBeNull();
  });

  it("returns 502 when the backend is unreachable", async () => {
    vi.stubEnv("BACKEND_URL", "http://localhost:8000");
    stubBackend(new TypeError("fetch failed"));
    vi.spyOn(console, "error").mockImplementation(() => {});

    expect((await recommend()).status).toBe(502);
  });

  it("returns 502 when BACKEND_URL is missing", async () => {
    vi.stubEnv("BACKEND_URL", "");
    const fetchMock = stubBackend(Response.json({}));
    vi.spyOn(console, "error").mockImplementation(() => {});

    expect((await getOptions()).status).toBe(502);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("hides a backend 401 behind a 502", async () => {
    vi.stubEnv("BACKEND_URL", "http://localhost:8000");
    vi.stubEnv("BACKEND_API_KEY", "wrong");
    stubBackend(Response.json({ detail: "Missing or invalid X-API-Key header." }, { status: 401 }));
    vi.spyOn(console, "error").mockImplementation(() => {});

    const resp = await recommend();

    expect(resp.status).toBe(502);
    expect(JSON.stringify(await resp.json())).not.toContain("X-API-Key");
  });

  it("returns 504 on timeout", async () => {
    vi.stubEnv("BACKEND_URL", "http://localhost:8000");
    stubBackend(new DOMException("The operation timed out.", "TimeoutError"));

    expect((await recommend()).status).toBe(504);
  });
});
