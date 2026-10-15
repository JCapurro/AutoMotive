import { headers } from "next/headers";

/** The Auth callback that carries `next` through confirmation, recovery and OAuth links. */
export async function callbackUrl(next: string): Promise<string> {
  const h = await headers();
  const origin = process.env.SITE_URL?.replace(/\/$/, "") ?? h.get("origin") ?? `http://${h.get("host")}`;
  return `${origin}/auth/callback?next=${encodeURIComponent(next)}`;
}
