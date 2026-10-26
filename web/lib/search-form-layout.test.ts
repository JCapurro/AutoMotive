import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }) }));
vi.mock("@/app/app/searches/actions", () => ({ saveSearch: vi.fn() }));

import { SearchForm } from "@/components/app/search-form";
import { SearchInput } from "@/lib/search-form";

const initial = SearchInput.parse({ make: "Ford", model: "Fiesta", sources: ["mercadolibre"], opportunity_threshold_pct: 12 });

it("doesn't offer the opportunity threshold in the form, even to a search that has one", () => {
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
