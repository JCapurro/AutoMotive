/** profiles.email_unsubscribe_token, as it arrives in /baja?t=… (F7, punto 7). */
export function unsubscribeToken(value: unknown): string | null {
  return typeof value === "string" && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value)
    ? value.toLowerCase()
    : null;
}
