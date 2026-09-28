/**
 * /r/<notification_id> (sección 7.3): every link of an alert goes through it.
 *
 *   /r/<id>?to=listing         → the listing at its source
 *   /r/<id>?to=detail          → the listing's page in Automotive
 *   /r/<id>?to=…&l=<listing>   → one item of a digest
 *
 * A click is recorded with public.track_notification_click (clicked_at, and
 * opened_at the first time, plus an alert_clicked event). Link-preview
 * crawlers (Telegram fetches the first link of a message) and HEAD requests
 * are redirected without counting.
 */

const PREVIEW_BOTS =
  /telegrambot|twitterbot|facebookexternalhit|slackbot|whatsapp|discordbot|googlebot|bingbot|linkedinbot|preview/i;

export function isPreview(userAgent: string | null | undefined): boolean {
  return Boolean(userAgent && PREVIEW_BOTS.test(userAgent));
}

export type ClickTarget = "listing" | "detail";

export function parseClick(notificationId: string, search: URLSearchParams) {
  if (!/^\d+$/.test(notificationId)) return null;
  const to: ClickTarget = search.get("to") === "detail" ? "detail" : "listing";
  const l = search.get("l");
  return { notificationId: Number(notificationId), to, listingId: l && /^\d+$/.test(l) ? Number(l) : null };
}

/** Where a click lands: the source's URL, or the detail page (which knows the alert it came from). */
export function destination(
  to: ClickTarget,
  row: { listing_id: number; url: string },
  notificationId: number,
): string {
  return to === "detail" ? `/app/listings/${row.listing_id}?n=${notificationId}` : row.url;
}
