/**
 * Shared between the middleware (edge) and the sign-in route (node), so both
 * derive the cookie value the same way.
 *
 * The cookie holds a hash of the password, never the password. It is httpOnly,
 * so page scripts cannot read it, and the password itself never reaches the
 * client bundle — the check happens on the server. That is a real gate rather
 * than a hidden div, which is the usual way this gets done and is worth
 * nothing.
 *
 * What it is not: per-user auth. It is one shared passphrase for a private
 * workbench. If this ever needs to distinguish people or survive a determined
 * attacker, it needs real sessions, not this.
 */
export const LAB_COOKIE = "lab";

export async function labToken(secret: string): Promise<string> {
  const data = new TextEncoder().encode(`slice-lab:v1:${secret}`);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/** Length-independent comparison, so timing does not leak the prefix. */
export function safeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}
