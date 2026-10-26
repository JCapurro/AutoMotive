import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }) }));
vi.mock("@/app/app/searches/actions", () => ({ saveSearch: vi.fn() }));

import { SearchForm } from "@/components/app/search-form";
import { SearchInput } from "@/lib/search-form";

const initial = SearchInput.parse({ make: "Ford", model: "Fiesta", sources: ["mercadolibre"], opportunity_threshold_pct: 12 });

it("a plan without the threshold never sees it, even on a search that has one", () => {
  const html = renderToStaticMarkup(createElement(SearchForm, {
    catalog: [], sources: [{ id: "mercadolibre", name: "MercadoLibre" }], initial, profileId: 7,
  }));
  expect(html).not.toContain("Umbral de oportunidad");
  expect(html).not.toContain("Avisame al instante si está");
});

it("puts the submit button at the end of the form, centered, not in a side column", () => {
  const html = renderToStaticMarkup(createElement(SearchForm, {
    catalog: [], sources: [{ id: "mercadolibre", name: "MercadoLibre" }], initial, profileId: null,
  }));
  expect(html).not.toContain("lg:grid-cols-[1fr_300px]");
  expect(html).toContain("mx-auto w-full max-w-md");
  expect(html.indexOf("Crear búsqueda")).toBeGreaterThan(html.indexOf("Nombre de la búsqueda"));
});

const render = (thresholdAlerts: boolean | undefined, pct: number | null) =>
  renderToStaticMarkup(createElement(SearchForm, {
    catalog: [], sources: [{ id: "mercadolibre", name: "MercadoLibre" }], profileId: 7, thresholdAlerts,
    initial: SearchInput.parse({ make: "Ford", model: "Fiesta", sources: ["mercadolibre"], opportunity_threshold_pct: pct }),
  }));

it("offers the opportunity threshold only to a plan that has it, as a switch and a slider", () => {
  const on = render(true, 15);
  expect(on).toContain("Avisos al instante por buen precio");
  expect(on).toContain('role="switch"');
  expect(on).toContain('aria-checked="true"');
  expect(on).toMatch(/<input[^>]*type="range"[^>]*value="15"/);
  expect(on).toContain("15 % o más por debajo del precio de mercado");
  for (const html of [render(false, 15), render(undefined, null)]) expect(html).not.toContain("Avisos al instante por buen precio");
});

it("a search without a threshold shows the switch off and no slider", () => {
  const off = render(true, null);
  expect(off).toContain('aria-checked="false"');
  expect(off).not.toContain('type="range"');
  expect(off).toContain("Apagado: te avisamos de todo lo que coincide");
});
