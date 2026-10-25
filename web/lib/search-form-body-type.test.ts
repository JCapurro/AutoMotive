import { createElement, type ComponentProps } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }) }));
vi.mock("@/app/app/searches/actions", () => ({ saveSearch: vi.fn(), previewSearch: vi.fn(), relaxSuggestions: vi.fn() }));

import { SearchForm } from "@/components/app/search-form";
import type { Catalog } from "@/lib/catalog";
import { MODEL_LESS_UNAVAILABLE, MODEL_LESS_UPSELL, SearchInput } from "@/lib/search-form";

const model = (name: string, bodyTypes: string[]) => ({ model: name, trims: [], yearFrom: 1994, yearTo: 2012, transmissions: [], fuels: [], bodyTypes });
const CATALOG: Catalog = [{ make: "Chevrolet", models: [model("Corsa", ["hatchback", "sedan", "pickup", "rural", "utilitario"]), model("S10", ["pickup"])] }];
const sources = [{ id: "mercadolibre", name: "MercadoLibre" }];

function render(props: Partial<ComponentProps<typeof SearchForm>> & { initial: ComponentProps<typeof SearchForm>["initial"] }): string {
  return renderToStaticMarkup(createElement(SearchForm, { catalog: CATALOG, sources, profileId: null, ...props }));
}

/** The checkbox chips' labels, in order. */
function chips(html: string): string[] {
  return [...html.matchAll(/<input type="checkbox" class="sr-only" name="body_types"(?: checked="")? value="([a-z]+)"/g)].map((m) => m[1]);
}

// A new search with the make picked and the model still to choose.
const blank = { ...SearchInput.parse({ make: "Chevrolet", model: "Corsa", sources: ["mercadolibre"] }), model: "" };
const suv = SearchInput.parse({ body_types: ["suv", "pickup"], price_max: 20000, sources: ["mercadolibre"] });

describe("search by body type (docs/CARROCERIA.md)", () => {
  it("offers the mode switch only to a plan with model_less_search, and the upsell otherwise", () => {
    const paid = render({ initial: blank, modelLessSearch: true });
    expect(paid).toContain(">Buscar por</legend>");
    expect(paid).toContain('value="body"');
    expect(paid).not.toContain(MODEL_LESS_UPSELL);
    for (const html of [render({ initial: blank }), render({ initial: blank, modelLessSearch: false })]) {
      expect(html).not.toContain("Buscar por");
      expect(html).toContain(MODEL_LESS_UPSELL);
      expect(html).toContain('href="/app/pro"');
    }
  });

  it("opens a model-less search by body type: the nine chips, no make or model, a required max price", () => {
    const html = render({ initial: suv, modelLessSearch: true, profileId: 3 });
    expect(html).toMatch(/<fieldset[^>]*><legend[^>]*>Carrocería<\/legend>/);
    expect(chips(html)).toEqual(["sedan", "hatchback", "suv", "pickup", "rural", "monovolumen", "coupe", "convertible", "utilitario"]);
    expect(html.match(/name="body_types" checked="" value="(suv|pickup)"/g)).toHaveLength(2);
    expect(html).not.toContain(">Marca<");
    expect(html).toContain("Obligatorio");
    expect(html).toMatch(/id="price_max"[^>]*required=""/);
    expect(html).toContain('value="SUV o Pick-up hasta USD 20.000"');
    expect(html).not.toMatch(/<button[^>]*type="submit"[^>]*disabled/);
  });

  it("locks a saved model-less search when the account lost the feature, with a way back to a model", () => {
    const html = render({ initial: suv, profileId: 3 });
    expect(html).toContain(">Buscar por</legend>");
    expect(html).toMatch(/<fieldset[^>]*disabled=""[^>]*><legend[^>]*>Carrocería/);
    expect(html).toContain(MODEL_LESS_UNAVAILABLE);
    expect(html).toMatch(/<button[^>]*type="submit"[^>]*disabled=""/);
    expect(html).toContain("Para contar las publicaciones, elegí un modelo.");
  });

  it("opens a model-less proposal by model for an account without the feature", () => {
    const html = render({ initial: suv });
    expect(html).not.toContain("Buscar por");
    expect(html).toContain(">Marca<");
    expect(html).toContain(MODEL_LESS_UPSELL);
    expect(chips(html)).toEqual([]);
  });

  it("offers within a model only the body types the catalog lists, when there are several", () => {
    const corsa = render({ initial: SearchInput.parse({ make: "Chevrolet", model: "Corsa", body_types: ["rural"], sources: ["mercadolibre"] }) });
    expect(chips(corsa)).toEqual(["hatchback", "sedan", "pickup", "rural", "utilitario"]);
    expect(corsa).toContain('checked="" value="rural"');
    expect(corsa).toContain("Opcional");
    const s10 = render({ initial: SearchInput.parse({ make: "Chevrolet", model: "S10", sources: ["mercadolibre"] }) });
    expect(chips(s10)).toEqual([]);
  });
});
