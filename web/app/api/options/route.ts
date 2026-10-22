import { proxyToBackend } from "@/lib/backend";

// Render's free tier sleeps when idle; the first request waits ~30–60 s for it to wake (deployment.md D2).
export const maxDuration = 60;

export async function GET() {
  const resp = await proxyToBackend("/options", { method: "GET" }, 57_000);
  // Locations and cuisines only change on redeploy; let the CDN hold them briefly.
  if (resp.ok) resp.headers.set("cache-control", "public, s-maxage=300, stale-while-revalidate=600");
  return resp;
}
