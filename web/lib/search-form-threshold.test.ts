import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }) }));
vi.mock("@/app/app/searches/actions", () => ({ saveSearch: vi.fn(), previewSearch: vi.fn(), relaxSuggestions: vi.fn() }));

import { SearchForm } from "@/components/app/search-form";
import { SearchInput } from "@/lib/search-form";

const initial = SearchInput.parse({ make: "Ford", model: "Fiesta", sources: ["mercadolibre"], opportunity_threshold_pct: 12 });

function render(thresholdAlerts?: boolean): string {
  return renderToStaticMarkup(createElement(SearchForm, {
    catalog: [], sources: [{ id: "mercadolibre", name: "MercadoLibre" }], initial, profileId: 7, thresholdAlerts,
  }));
}

it("shows the opportunity threshold only to a plan that has it (Pro, 3.2)", () => {
  const pro = render(true);
  expect(pro).toContain("Umbral de oportunidad (opcional)");
  expect(pro).toContain("Avisame al instante si está");
  expect(pro).toContain("% o más por debajo de comparables");
  expect(pro).toContain('value="12"');
  for (const html of [render(false), render()]) expect(html).not.toContain("Umbral de oportunidad");
});
