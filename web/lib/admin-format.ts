import { dateTime, number, pct } from "@/lib/format";

/** Formatting for the admin tables. */

export function when(value: string | null | undefined): string {
  return value ? dateTime(value) : "—";
}

export function percent(value: number | null | undefined): string {
  return value == null ? "—" : pct(Number(value), 1);
}

export function count(value: number | null | undefined): string {
  return number(value == null ? null : Number(value));
}

/** "Ford Fiesta 2016–2018 · ≤ USD 11.500" from search_profiles.filters. */
export function filterSummary(filters: unknown): string {
  const f = (filters ?? {}) as Record<string, unknown>;
  const parts = [[f.make, f.model].filter(Boolean).join(" ") || "Sin vehículo"];
  if (f.year_min || f.year_max) parts.push(`${f.year_min ?? "…"}–${f.year_max ?? "…"}`);
  if (f.price_max) parts.push(`≤ ${f.currency ?? "USD"} ${number(Number(f.price_max))}`);
  if (f.km_max) parts.push(`≤ ${number(Number(f.km_max))} km`);
  if (f.transmission) parts.push(String(f.transmission));
  return parts.join(" · ");
}

/** A match_reasons result as §45 writes it: true / false / unknown. */
export function reasonValue(result: string): "true" | "false" | "unknown" {
  return result === "ok" ? "true" : result === "fail" ? "false" : "unknown";
}

/** The instant `days` ago, as an ISO timestamp (or a YYYY-MM-DD date for date columns). */
export function daysAgo(days: number, dateOnly = false): string {
  const iso = new Date(Date.now() - days * 86_400_000).toISOString();
  return dateOnly ? iso.slice(0, 10) : iso;
}

export function isPast(value: string | null | undefined): boolean {
  return Boolean(value) && Date.parse(value!) < Date.now();
}
