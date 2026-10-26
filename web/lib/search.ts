import { FUEL, TRANSMISSION, bodyTypesText } from "@/lib/copy";
import { money, number } from "@/lib/format";
import { isModelLess } from "@/lib/search-form";
import type { Filters } from "@/lib/types";

/** "2016–2018 · hasta USD 11.500 · hasta 150.000 km · Manual · AMBA (60 km)" */
export function describeFilters(filters: Filters, radiusKm?: number | null): string {
  return filterParts(filters, radiusKm).join(" · ") || "Sin filtros adicionales";
}

/** The same, one item per filter (shown as chips). A model-less search's body types are its vehicle. */
export function filterParts(filters: Filters, radiusKm?: number | null): string[] {
  const parts: string[] = [];
  const { year_min: lo, year_max: hi } = filters;
  if (lo && hi) parts.push(lo === hi ? String(lo) : `${lo}–${hi}`);
  else if (lo) parts.push(`desde ${lo}`);
  else if (hi) parts.push(`hasta ${hi}`);
  if (filters.price_max != null) parts.push(`hasta ${money(filters.price_max, filters.currency ?? "USD")}`);
  if (filters.km_max != null) parts.push(`hasta ${number(filters.km_max)} km`);
  if (filters.transmission) parts.push(TRANSMISSION[filters.transmission]);
  if (filters.fuel) parts.push(FUEL[filters.fuel] ?? filters.fuel);
  if (!isModelLess(filters) && bodyTypesText(filters.body_types)) parts.push(bodyTypesText(filters.body_types));
  if (filters.location_label) {
    parts.push(radiusKm ? `${filters.location_label} (${number(radiusKm)} km)` : filters.location_label);
    for (const z of filters.extra_locations ?? []) parts.push(`${z.label} (${number(z.radius_km)} km)`);
  } else if (radiusKm) {
    parts.push(`a ${number(radiusKm)} km`);
  }
  return parts;
}

/** "Ford Fiesta · Titanium"; without a model, its body types: "SUV o Pick-up". */
export function describeVehicle(filters: Filters): string {
  if (isModelLess(filters)) return bodyTypesText(filters.body_types);
  const name = [filters.make, filters.model].filter(Boolean).join(" ");
  const trims = filters.trims?.filter(Boolean) ?? [];
  return trims.length ? `${name} · ${trims.join(" / ")}${filters.trim_strict ? "" : " (preferida)"}` : name;
}
