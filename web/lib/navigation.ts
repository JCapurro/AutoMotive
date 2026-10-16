const BASE = "https://next.invalid";

/**
 * Only same-site paths: `next` comes from the URL (and from links inside
 * emails) and must not become an open redirect. The URL parser drops tabs and
 * newlines and reads "\" as "/", so "/<TAB>/evil.com" would resolve to another
 * host: anything with a control character or a backslash is rejected, and the
 * parsed result must stay on our origin.
 */
export function safeNext(next: string | null | undefined, fallback = "/app"): string {
  if (!next || !next.startsWith("/") || /[\u0000-\u001f\u007f\\]/.test(next)) return fallback;
  let url: URL;
  try {
    url = new URL(next, BASE);
  } catch {
    return fallback;
  }
  // Dot segments collapse after parsing: "/.//evil.com" comes out as "//evil.com".
  if (url.origin !== BASE || url.pathname.startsWith("//")) return fallback;
  return url.pathname + url.search;
}

/** Recovery links carry `/auth/reset-password?next=<path>`; anything else is not a recovery destination. */
export const RESET_PASSWORD_PATH = "/auth/reset-password";

/** The `next` a recovery link may carry, or the bare reset page. */
export function recoveryNext(next: string | null | undefined): string {
  const safe = safeNext(next, RESET_PASSWORD_PATH);
  const url = new URL(safe, BASE);
  if (url.pathname !== RESET_PASSWORD_PATH) return RESET_PASSWORD_PATH;
  const inner = url.searchParams.get("next");
  return inner ? `${RESET_PASSWORD_PATH}?${new URLSearchParams({ next: safeNext(inner) })}` : RESET_PASSWORD_PATH;
}

/** Where to go once a recovery link is used: the inner `next` of the reset path, or /app. */
export function afterRecovery(next: string | null | undefined): string {
  const url = new URL(recoveryNext(next), BASE);
  return safeNext(url.searchParams.get("next"));
}
