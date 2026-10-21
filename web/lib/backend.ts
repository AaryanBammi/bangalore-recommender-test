// Server-only: forwards requests to the FastAPI backend (deployment.md §1).
// BACKEND_URL and BACKEND_API_KEY never reach the browser.

export async function proxyToBackend(path: string, init: RequestInit, timeoutMs: number): Promise<Response> {
  const base = process.env.BACKEND_URL?.replace(/\/+$/, "");
  if (!base) {
    console.error("BACKEND_URL is not set");
    return Response.json({ detail: "Backend is not configured." }, { status: 502 });
  }
  const headers = new Headers(init.headers);
  const key = process.env.BACKEND_API_KEY;
  if (key) headers.set("X-API-Key", key);

  let upstream: Response;
  try {
    upstream = await fetch(`${base}${path}`, { ...init, headers, cache: "no-store", signal: AbortSignal.timeout(timeoutMs) });
  } catch (err) {
    if (err instanceof Error && err.name === "TimeoutError") {
      return Response.json({ detail: "The backend timed out." }, { status: 504 });
    }
    console.error(`Backend unreachable at ${base}${path}`, err);
    return Response.json({ detail: "Backend is unreachable." }, { status: 502 });
  }
  if (upstream.status === 401) {
    // A key mismatch is a deployment problem; the user can't fix it.
    console.error("Backend rejected BACKEND_API_KEY; check it matches on both hosts");
    return Response.json({ detail: "Backend rejected the request." }, { status: 502 });
  }
  return new Response(upstream.body, {
    status: upstream.status,
    headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" },
  });
}
