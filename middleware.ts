import { NextResponse, type NextRequest } from "next/server";
import { LAB_COOKIE, labToken, safeEqual } from "@/lib/lab-auth";

/**
 * Gates /lab. The public viewer is deliberately not gated — the whole point of
 * shipping it is that people open it.
 *
 * Fails closed: with no LAB_PASSWORD configured the lab is unreachable rather
 * than open. A deploy that forgets the env var should lock, not publish.
 */
export async function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;
  if (pathname === "/lab/enter") return NextResponse.next();

  const secret = process.env.LAB_PASSWORD;
  const url = req.nextUrl.clone();
  url.pathname = "/lab/enter";

  if (!secret) {
    url.searchParams.set("reason", "unset");
    return NextResponse.redirect(url);
  }

  const cookie = req.cookies.get(LAB_COOKIE)?.value ?? "";
  if (safeEqual(cookie, await labToken(secret))) return NextResponse.next();

  url.searchParams.set("next", pathname);
  return NextResponse.redirect(url);
}

export const config = { matcher: "/lab/:path*" };
