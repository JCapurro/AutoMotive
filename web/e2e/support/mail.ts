import { MAILPIT_URL } from "./env";

type Summary = { ID: string; To: { Address: string }[]; Created: string };

/**
 * The confirmation or recovery link sent to `email` (local Supabase delivers to Mailpit).
 * Waits for a message newer than `since`.
 */
export async function magicLink(email: string, since: Date, timeoutMs = 20_000): Promise<string> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const res = await fetch(`${MAILPIT_URL}/api/v1/search?query=${encodeURIComponent(`to:"${email}"`)}`);
    if (res.ok) {
      const { messages } = (await res.json()) as { messages: Summary[] };
      const latest = messages
        .filter((m) => new Date(m.Created).getTime() >= since.getTime() - 1000)
        .sort((a, b) => b.Created.localeCompare(a.Created))[0];
      if (latest) {
        const message = (await (await fetch(`${MAILPIT_URL}/api/v1/message/${latest.ID}`)).json()) as { HTML: string };
        const href = message.HTML.match(/href="([^"]*\/auth\/(?:v1\/verify|confirm|callback)[^"]*)"/)?.[1];
        if (href) return href.replaceAll("&amp;", "&");
      }
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`no auth link for ${email} in ${timeoutMs} ms`);
}
