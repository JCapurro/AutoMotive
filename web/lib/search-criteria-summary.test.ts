import { createElement, type ComponentProps } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { SearchCriteriaSummary } from "@/components/app/search-criteria-summary";

const sources = [
  { id: "mercadolibre", name: "MercadoLibre", enabled: true },
  { id: "kavak", name: "Kavak", enabled: true },
  { id: "autocosmos", name: "Autocosmos", enabled: false },
];
function html(props: Partial<ComponentProps<typeof SearchCriteriaSummary>> = {}) {
  return renderToStaticMarkup(createElement(SearchCriteriaSummary, {
    name: "Ford Fiesta Titanium", filters: {}, preferences: {}, radiusKm: 30, hasLocation: true, sources, ...props,
  }));
}

describe("saved search criteria", () => {
  it("shows independent accessible loading, completed, failed and paused platform states", () => {
    const result = html({ sources: [
      { id: "mercadolibre", name: "MercadoLibre", enabled: true, collectionState: "loading" },
      { id: "kavak", name: "Kavak", enabled: true, collectionState: "done" },
      { id: "autocosmos", name: "Autocosmos", enabled: true, collectionState: "failed" },
      { id: "v6", name: "V6", enabled: false, collectionState: "done" },
    ], filters: { sources: ["mercadolibre", "kavak", "autocosmos", "v6"] } });
    expect(result).toContain('aria-label="MercadoLibre: Recolectando datos"');
    expect(result).toContain('aria-label="Kavak: Recolección completada"');
    expect(result).toContain('aria-label="Autocosmos: No se pudo completar la recolección"');
    expect(result).toContain('aria-label="V6: Recolección pausada"');
    expect(result).toContain("motion-reduce:animate-none");
    expect(result.match(/data-collection-state="done"/g)).toHaveLength(1);
    expect(html()).not.toContain('data-collection-state="done"');
  });
  it("shows both bounds, currency and the real location without repeating the title", () => {
    const result = html({ filters: { make: "Ford", model: "Fiesta", year_min: 2016, year_max: 2018,
      price_min: 10_000, price_max: 12_000, currency: "USD", km_min: 50_000, km_max: 150_000,
      transmission: "manual", location_label: "Palermo" } });
    expect(result).toContain("2016–2018");
    expect(result).toContain("USD 10.000–12.000");
    expect(result).toContain("50.000–150.000 km");
    expect(result).toContain("Manual");
    expect(result).toContain("Palermo · 30 km");
    expect(result).not.toContain("Ford Fiesta");
  });
  it("handles open ranges and legacy currency in the same way as matching", () => {
    const result = html({ filters: { year_min: 2016, price_min: 15_000_000, km_max: 100_000 } });
    expect(result).toContain("Desde 2016");
    expect(result).toContain("Desde ARS 15.000.000");
    expect(result).toContain("Hasta 100.000 km");
    expect(html({ filters: { year_min: 2018, year_max: 2018, price_max: 12_000 } })).toContain("Hasta USD 12.000");
  });
  it("uses enabled platforms for an unrestricted profile and only the saved subset otherwise", () => {
    expect(html()).toContain("MercadoLibre");
    expect(html()).toContain("Kavak");
    expect(html()).not.toContain("Autocosmos");
    const result = html({ filters: { sources: ["mercadolibre", "autocosmos", "mercadolibre"] } });
    expect(result).toContain("MercadoLibre");
    expect(result).toContain("Autocosmos");
    expect(result).toContain("pausada");
    expect(result).not.toContain("Kavak");
    expect(result.match(/>MercadoLibre</g)).toHaveLength(1);
    expect(html({ filters: { sources: [] } })).toContain("Kavak");
  });
  it("does not invent platform names or collection status when metadata is unavailable", () => {
    const result = html({ sources: null });
    expect(result).toContain("No se pudieron cargar las plataformas");
    expect(result).not.toContain("MercadoLibre");
    expect(html({ filters: { sources: ["unknown"] } })).toContain("unknown · sin información");
    expect(html({ filters: { sources: ["unknown"] } })).not.toContain("pausada");
  });
  it("keeps secondary criteria in a closed disclosure and labels soft preferences", () => {
    const result = html({ filters: { fuel: "nafta", trims: ["Titanium"] },
      preferences: { preferred_trims: ["Titanium", "SE"], seller_type: "private", colors: ["Blanco"],
        price_target: 10_000, price_target_currency: "USD", km_target: 80_000, max_distance_km: 20 } });
    expect(result).toContain("<details");
    expect(result).not.toMatch(/<details[^>]*\sopen/);
    expect(result).toContain("Ver más criterios");
    expect(result).toContain("Nafta");
    expect(result).toContain("Versión preferida");
    expect(result).toContain("Titanium, SE");
    expect(result).toContain("Vendedor preferido");
    expect(result).toContain("Particular");
    expect(result).toContain("USD 10.000");
    expect(result).toContain("80.000 km");
    expect(result).toContain("20 km");
    expect(html({ filters: { trims: ["Titanium"], trim_strict: true } })).not.toContain("Versión preferida");
  });
  it("omits location filters without a usable origin and preserves the vehicle for custom names", () => {
    const result = html({ name: "Mi próximo auto", hasLocation: false,
      filters: { make: "Ford", model: "Fiesta", location_label: "Palermo" }, preferences: { max_distance_km: 20 } });
    expect(result).toContain("Ford Fiesta");
    expect(result).not.toContain("Palermo");
    expect(result).not.toContain("Distancia preferida");
    expect(html({ filters: { location_label: "Palermo" }, radiusKm: 0 })).not.toContain("Palermo");
    expect(html({ sources: [], hasLocation: false })).toBe("");
  });
});
