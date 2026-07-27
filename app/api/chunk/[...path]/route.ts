import { type NextRequest } from "next/server";

/**
 * Fallback S3 proxy. Nothing calls this.
 *
 * The bucket is anonymous and serves `Access-Control-Allow-Origin: *`, verified
 * against live S3 — so the browser reads chunks directly and this route sits
 * idle. It exists because open CORS is a policy, not a guarantee: if that ever
 * changes, point `openVolume` at `/api/chunk/...` and the app keeps working.
 *
 * Chunks are immutable once published, so responses are cached hard at the
 * edge. Note that chunks are 2 MB uncompressed; this route is a contingency,
 * not a performance path.
 */

const BUCKET = "https://vesuvius-challenge-open-data.s3.us-east-1.amazonaws.com";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { path } = await params;
  const key = path.map(encodeURIComponent).join("/");

  const upstream = await fetch(`${BUCKET}/${key}`, {
    // Chunk keys are content-addressed by position and never rewritten.
    next: { revalidate: 31536000 },
  });

  if (!upstream.ok) {
    return new Response(`Upstream returned ${upstream.status} for ${key}`, {
      status: upstream.status,
    });
  }

  return new Response(upstream.body, {
    status: 200,
    headers: {
      "Content-Type": "application/octet-stream",
      "Cache-Control": "public, max-age=31536000, immutable",
      "Access-Control-Allow-Origin": "*",
    },
  });
}
