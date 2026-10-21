import { proxyToBackend } from "@/lib/backend";

export async function GET() {
  const resp = await proxyToBackend("/options", { method: "GET" }, 10_000);
  // Locations and cuisines only change on redeploy; let the CDN hold them briefly.
  if (resp.ok) resp.headers.set("cache-control", "public, s-maxage=300, stale-while-revalidate=600");
  return resp;
}
