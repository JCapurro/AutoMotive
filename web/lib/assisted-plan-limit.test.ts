import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), replace: vi.fn() }) }));
vi.mock("@/app/app/searches/actions", () => ({ startAssisted: vi.fn(), finishAssisted: vi.fn() }));
vi.mock("@/components/app/search-form", () => ({ SearchForm: () => null }));
vi.mock("@/lib/supabase/client", () => ({ createClient: () => ({}) }));

import { ModelChoice, PlanFull } from "@/components/app/assisted-search";
import { afterParse, roomText, type SearchLimit, toggleChoice } from "@/lib/assisted";

/** «Busco Focus, Cruze o Corolla 2015 a 2018 en AMBA»: three models, one search each. */
const MODELS = ["Ford Focus", "Chevrolet Cruze", "Toyota Corolla"];
const UPSELL = "Con Particular seguís hasta 3 modelos a la vez por $ 15.000.";
const trial: SearchLimit = { capacity: 1, maxProfiles: 1, activeSearches: 0, upsell: UPSELL };
const particular: SearchLimit = { capacity: 3, maxProfiles: 3, activeSearches: 0, upsell: null };

describe("after the parse", () => {
  it("reviews the three models in Particular and asks to choose in the trial", () => {
    expect(afterParse(MODELS.length, particular)).toBe("review");
    expect(afterParse(MODELS.length, trial)).toBe("choose");
  });
  it("asks to choose when the plan only has room for some, and stops when it has none", () => {
    expect(afterParse(3, { ...particular, capacity: 2, activeSearches: 1 })).toBe("choose");
    expect(afterParse(1, { ...trial, capacity: 0, activeSearches: 1 })).toBe("full");
  });
  it("doesn't limit without enforced plan limits", () => {
    expect(afterParse(5, null)).toBe("review");
  });
});

describe("choosing models", () => {
  it("works like a radio with room for one", () => {
    expect(toggleChoice([], 2, 1)).toEqual([2]);
    expect(toggleChoice([2], 0, 1)).toEqual([0]);
    expect(toggleChoice([0], 0, 1)).toEqual([]);
  });
  it("never selects more than the plan's room", () => {
    expect(toggleChoice([0, 1], 2, 2)).toEqual([0, 1]);
    expect(toggleChoice([0, 1], 1, 2)).toEqual([0]);
  });
  it("words the room the plan has", () => {
    expect(roomText(trial)).toBe("tu plan permite una búsqueda activa.");
    expect(roomText({ ...particular, capacity: 2, activeSearches: 1 })).toBe("te queda lugar para 2 búsquedas más en tu plan.");
  });
});

describe("the choice screen", () => {
  const render = (limit: SearchLimit, selected: number[] = []) => renderToStaticMarkup(createElement(ModelChoice, {
    text: "Busco Focus, Cruze o Corolla 2015 a 2018 en AMBA", onEdit: vi.fn(), limit, titles: MODELS, selected,
    onToggle: vi.fn(), onContinue: vi.fn(),
  }));

  it("shows the detected models and the Particular offer in the trial", () => {
    const html = render(trial);
    for (const model of MODELS) expect(html).toContain(model);
    expect(html).toContain("Encontramos 3 modelos en tu pedido. Cada modelo es una búsqueda y tu plan permite una búsqueda activa.");
    expect(html).toContain("Elegí cuál querés activar");
    expect(html.match(/type="radio"/g)).toHaveLength(3);
    expect(html).toContain(UPSELL);
    expect(html).toMatch(/<button[^>]*disabled=""[^>]*>Continuar/);
  });

  it("uses checkboxes up to the room, without the trial offer", () => {
    const html = render({ ...particular, capacity: 2, activeSearches: 1 }, [0, 1]);
    expect(html).toContain("Elegí cuáles querés activar (hasta 2)");
    expect(html.match(/type="checkbox"/g)).toHaveLength(3);
    expect(html.match(/disabled=""/g)).toHaveLength(1);
    expect(html).not.toContain("Con Particular");
  });

  it("explains a plan with every search in use", () => {
    const html = renderToStaticMarkup(createElement(PlanFull, {
      text: "Corolla", onEdit: vi.fn(), limit: { ...trial, capacity: 0, activeSearches: 1 }, found: 1,
    }));
    expect(html).toContain("Encontramos un modelo en tu pedido, pero ya tenés una búsqueda activa: el máximo de tu plan.");
    expect(html).toContain("Para activar otra búsqueda, pausá una de las que tenés.");
    expect(html).toContain(UPSELL);
    expect(html).toContain('href="/app/pro"');
  });
});
