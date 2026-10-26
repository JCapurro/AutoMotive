import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }) }));
vi.mock("@/app/app/searches/actions", () => ({ saveSearch: vi.fn() }));

import { SearchForm } from "@/components/app/search-form";
import { cityFromText } from "@/lib/argentina-locations";
import { SearchInput } from "@/lib/search-form";

const sources = [{ id: "mercadolibre", name: "MercadoLibre" }];
const place = (text: string, radius_km: number) => {
  const c = cityFromText(text)!;
  return { label: c.label, lat: c.lat, lon: c.lon, radius_km };
};
const RESISTENCIA = place("Resistencia, Chaco", 30);
const CORRIENTES = place("Corrientes, Corrientes", 25);
const base = { make: "Toyota", model: "Corolla", sources: ["mercadolibre"] };

function render(values: Record<string, unknown>, props: Record<string, unknown> = {}): string {
  const initial = SearchInput.parse({ ...base, ...values });
  return renderToStaticMarkup(createElement(SearchForm, { catalog: [], sources, profileId: 7, initial, ...props }));
}

describe("the search form's location", () => {
  it("offers only the current location, a manual one and the whole country", () => {
    const html = render({});
    const labels = [...html.matchAll(/name="place"(?: checked="")? value="[^"]*"\/>([^<]+)</g)].map((m) => m[1]);
    expect(labels).toEqual(["Mi ubicación actual", "Ubicación manual", "Todo el país"]);
    expect(html).not.toContain("AMBA");
    expect(html).not.toContain("Ubicación guardada</label>");
  });

  it("no longer counts listings", () => {
    const html = render({ location: RESISTENCIA });
    expect(html).not.toContain("publicaciones actuales coinciden");
    expect(html).not.toContain("Contando publicaciones");
    expect(html).not.toContain("preview-count");
  });

  it("a manual place lists its cities, each with province, locality and radius", () => {
    const html = render({ location: RESISTENCIA, extra_locations: [CORRIENTES] });
    expect(html).toContain(">Provincia<");
    expect(html).toContain(">Provincia 2<");
    expect(html).toContain(">Localidad 2<");
    expect(html).toMatch(/value="30"/);
    expect(html).toMatch(/value="25"/);
    expect(html).toContain("Agregar otra ciudad");
    expect(html).toContain('aria-label="Quitar la zona 2"');
  });

  it("a saved place that isn't a listed city is kept as it is", () => {
    const html = render({ location: { label: "Zona Norte (GBA)", lat: -34.47, lon: -58.52, radius_km: 25 } });
    expect(html).toContain("Zona Norte (GBA)");
    expect(html).toContain("Ubicación guardada en esta búsqueda.");
  });

  it("the plan's cap disables adding more cities and says so", () => {
    const html = render({ location: RESISTENCIA, extra_locations: [CORRIENTES] }, { maxLocations: 2 });
    expect(html).toMatch(/<button[^>]*disabled=""[^>]*>.*?Agregar otra ciudad/);
    expect(html).toContain("hasta dos zonas");
  });

  it("without a place there are no cities to pick", () => {
    const html = render({});
    expect(html).not.toContain("Agregar otra ciudad");
  });
});
