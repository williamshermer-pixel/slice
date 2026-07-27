import { NextResponse } from "next/server";
import { LAB_COOKIE, labToken } from "@/lib/lab-auth";

/** Exchanges the passphrase for an httpOnly cookie. Sign out with DELETE. */
export async function POST(request: Request) {
  const secret = process.env.LAB_PASSWORD;
  if (!secret) {
    return NextResponse.json(
      { error: "LAB_PASSWORD is not set on this deployment." },
      { status: 503 },
    );
  }

  let password = "";
  try {
    const body = (await request.json()) as { password?: unknown };
    password = typeof body.password === "string" ? body.password : "";
  } catch {
    return NextResponse.json({ error: "Expected a JSON body." }, { status: 400 });
  }

  if (password !== secret) {
    // Deliberately vague, and deliberately slow enough to be tedious to grind.
    await new Promise((r) => setTimeout(r, 400));
    return NextResponse.json({ error: "That passphrase is not right." }, { status: 401 });
  }

  const response = NextResponse.json({ ok: true });
  response.cookies.set(LAB_COOKIE, await labToken(secret), {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 60 * 60 * 24 * 30,
  });
  return response;
}

export async function DELETE() {
  const response = NextResponse.json({ ok: true });
  response.cookies.set(LAB_COOKIE, "", { path: "/", maxAge: 0 });
  return response;
}
