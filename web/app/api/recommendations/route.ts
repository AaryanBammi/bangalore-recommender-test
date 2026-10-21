import { proxyToBackend } from "@/lib/backend";

// An LLM call plus one retry can take ~55 s (deployment.md D5).
export const maxDuration = 60;

export async function POST(request: Request) {
  return proxyToBackend(
    "/recommendations",
    { method: "POST", headers: { "content-type": "application/json" }, body: await request.text() },
    57_000,
  );
}
