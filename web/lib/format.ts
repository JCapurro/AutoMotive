/**
 * Formatting shared by every screen. Mirrors the worker's copy
 * (worker/intelligence/copy.py, worker/notifications/templates.py): Argentine
 * thousands separators, "Publicado hace X" only when the source says when,
 * first detection as fallback, labeled "Detectado hace X".
 */

export const TIME_ZONE = "America/Argentina/Buenos_Aires";

const integer = new Intl.NumberFormat("es-AR", { maximumFractionDigits: 0 });

export function number(value: number | null | undefined): string {
  return value == null ? "—" : integer.format(Math.round(value));
}

/** USD 10.300 · ARS 12.500.000 */
export function money(amount: number | null | undefined, currency?: string | null): string {
  if (amount == null) return "sin precio";
  return `${currency ?? ""} ${integer.format(Math.round(amount))}`.trim();
}

export function km(value: number | null | undefined): string | null {
  return value == null ? null : `${number(value)} km`;
}

/** 8 → "8%", 6.09 → "6,1%" */
export function pct(value: number, decimals = 0): string {
  return `${value.toFixed(decimals).replace(".", ",")}%`;
}

export function ago(since: string | Date, now: Date = new Date()): string {
  const minutes = Math.max(Math.floor((now.getTime() - new Date(since).getTime()) / 60_000), 1);
  if (minutes < 60) return `${minutes} minuto${minutes === 1 ? "" : "s"}`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours} hora${hours === 1 ? "" : "s"}`;
  return `${Math.floor(hours / 24)} días`;
}

/** Publication age, falling back to the first detection without losing its origin. */
export function ageLine(
  listing: { published_at?: string | null; first_seen_at?: string | null },
  now: Date = new Date(),
): string | null {
  if (listing.published_at) return `Publicado hace ${ago(listing.published_at, now)}`;
  if (listing.first_seen_at) return `Detectado hace ${ago(listing.first_seen_at, now)}`;
  return "Fecha de publicación no informada";
}

export function daysSince(since: string | Date, now: Date = new Date()): number {
  return Math.max(Math.floor((now.getTime() - new Date(since).getTime()) / 86_400_000), 0);
}

const shortDate = new Intl.DateTimeFormat("es-AR", { day: "2-digit", month: "2-digit", timeZone: TIME_ZONE });
const longDate = new Intl.DateTimeFormat("es-AR", {
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: TIME_ZONE,
});

/** 01/09, as in the §31 price history. */
export function dayMonth(value: string | Date): string {
  return shortDate.format(new Date(value));
}

export function dateTime(value: string | Date): string {
  return longDate.format(new Date(value));
}

/** "Ford Fiesta Titanium 2017"; the title when make/model aren't known. */
export function vehicle(listing: {
  make?: string | null;
  model?: string | null;
  trim?: string | null;
  year?: number | null;
  title?: string | null;
}): string {
  if (listing.make && listing.model) {
    return [listing.make, listing.model, listing.trim, listing.year].filter(Boolean).join(" ");
  }
  return listing.title || "Vehículo";
}

/** First image URL of listings.images (a JSON array of URLs or {url} objects). */
export function firstImage(images: unknown): string | null {
  return imageUrls(images)[0] ?? null;
}

export function imageUrls(images: unknown): string[] {
  if (!Array.isArray(images)) return [];
  return images
    .map((img) => (typeof img === "string" ? img : img && typeof img === "object" && "url" in img ? String(img.url) : null))
    .filter((url): url is string => Boolean(url) && /^https?:\/\//.test(url as string));
}
