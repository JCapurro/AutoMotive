import { FUEL, TRANSMISSION } from "@/lib/copy";
import { money, number } from "@/lib/format";
import type { Filters } from "@/lib/types";

/** "2016–2018 · hasta USD 11.500 · hasta 150.000 km · Manual · AMBA (60 km)" */
export function describeFilters(filters: Filters, radiusKm?: number | null): string {
  const parts: string[] = [];
  const { year_min: lo, year_max: hi } = filters;
  if (lo && hi) parts.push(lo === hi ? String(lo) : `${lo}–${hi}`);
  else if (lo) parts.push(`desde ${lo}`);
  else if (hi) parts.push(`hasta ${hi}`);
  if (filters.price_max != null) parts.push(`hasta ${money(filters.price_max, filters.currency ?? "USD")}`);
  if (filters.km_max != null) parts.push(`hasta ${number(filters.km_max)} km`);
  if (filters.transmission) parts.push(TRANSMISSION[filters.transmission]);
  if (filters.fuel) parts.push(FUEL[filters.fuel] ?? filters.fuel);
  if (filters.location_label) {
    parts.push(radiusKm ? `${filters.location_label} (${number(radiusKm)} km)` : filters.location_label);
  } else if (radiusKm) {
    parts.push(`a ${number(radiusKm)} km`);
  }
  return parts.join(" · ") || "Sin filtros adicionales";
}

/** "Ford Fiesta · Titanium" */
export function describeVehicle(filters: Filters): string {
  const name = [filters.make, filters.model].filter(Boolean).join(" ");
  const trims = filters.trims?.filter(Boolean) ?? [];
  return trims.length ? `${name} · ${trims.join(" / ")}${filters.trim_strict ? "" : " (preferida)"}` : name;
}
