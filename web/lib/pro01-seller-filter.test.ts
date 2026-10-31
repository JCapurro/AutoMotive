import { createElement, type ComponentProps } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }) }));
vi.mock("@/app/app/searches/actions", () => ({ saveSearch: vi.fn() }));

import { SearchCriteriaSummary } from "@/components/app/search-criteria-summary";
import { SearchForm } from "@/components/app/search-form";
import { type AssistedDraft, draftToValues } from "@/lib/assisted";
import { SELLER_STRICT } from "@/lib/copy";
import { SearchInput, fromProfile, sellerForPlan, storedSellerTypes, toColumns, toFilters, toPreferences } from "@/lib/search-form";
import type { SearchProfile } from "@/lib/types";

/**
 * PRO-01 paso 1 (docs/superpowers/specs/2026-10-31-pro01-contacto-design.md,
 * decisiones 1, 6–9): filters.seller_types from the form, a downgraded search
 * back into it, the plan rule of the server action, the form and the summary.
 */
const v = (raw: SearchInput) => SearchInput.parse({ make: "Ford", model: "Fiesta", sources: ["mercadolibre"], ...raw });

const profile = (filters: Record<string, unknown>, preferences: Record<string, unknown> = {}) => ({
  id: 7, name: "Ford Fiesta", filters: { make: "Ford", model: "Fiesta", ...filters }, preferences,
  origin_lat: null, origin_lon: null, radius_km: null, notification_frequency: "immediate", notify_min_level: "good",
  opportunity_threshold_pct: null,
}) as unknown as SearchProfile;

describe("filters.seller_types", () => {
  it("the check stores the type as a hard filter and not as the preference", () => {
    const strict = v({ seller_type: "private", seller_strict: true });
    expect(toFilters(strict).seller_types).toEqual(["private"]);
    expect(toPreferences(strict)).not.toHaveProperty("seller_type");
    const soft = v({ seller_type: "dealer" });
    expect(toFilters(soft)).not.toHaveProperty("seller_types");
    expect(toPreferences(soft).seller_type).toBe("dealer");
  });

  it("asks for a type when the check is on", () => {
    const r = SearchInput.safeParse({ make: "Ford", model: "Fiesta", seller_strict: true });
    expect(r.success).toBe(false);
    expect(r.error?.issues[0]).toMatchObject({ path: ["seller_type"], message: "Elegí el tipo de vendedor." });
    expect(SearchInput.safeParse({ make: "Ford", model: "Fiesta", seller_type: "dealer_inferred", seller_strict: true }).success).toBe(false);
    expect(SearchInput.safeParse({ make: "Ford", model: "Fiesta", seller_type: "private", seller_strict: "yes" }).success).toBe(false);
  });

  it("a stored filter comes back as the select's value with the check (a downgrade too)", () => {
    const back = fromProfile(profile({ seller_types: ["dealer"] }), ["mercadolibre"]);
    expect([back.seller_type, back.seller_strict]).toEqual(["dealer", true]);
    const plain = fromProfile(profile({}, { seller_type: "private" }), ["mercadolibre"]);
    expect([plain.seller_type, plain.seller_strict]).toEqual(["private", false]);
    // Round trip: the same columns, so an edit that doesn't touch it asks no rematch.
    expect(toColumns(back, ["mercadolibre"]).filters.seller_types).toEqual(["dealer"]);
  });

  it("reads only the known types, as the worker does", () => {
    expect(storedSellerTypes({ seller_types: ["private"] })).toEqual(["private"]);
    expect(storedSellerTypes({ seller_types: ["dealer_inferred"] } as never)).toEqual([]);
    expect(storedSellerTypes({ seller_types: "private" } as never)).toEqual([]);
    expect(storedSellerTypes(null)).toEqual([]);
  });
});

describe("sellerForPlan (decisión 8: setting it is Pro's, clearing it is anyone's)", () => {
  const strict = v({ seller_type: "private", seller_strict: true });
  it("Pro keeps what it sends", () => {
    expect(sellerForPlan(strict, true)).toBe(strict);
    expect(sellerForPlan(v({ seller_type: "private" }), true, ["private"]).seller_strict).toBe(false);
  });
  it("without the feature a new strict value is the preference", () => {
    const out = sellerForPlan(strict, false);
    expect([out.seller_type, out.seller_strict]).toEqual(["private", false]);
    expect(toPreferences(out).seller_type).toBe("private");
    expect(toFilters(out)).not.toHaveProperty("seller_types");
  });
  it("without the feature the stored value is kept, never replaced", () => {
    expect(sellerForPlan(strict, false, ["private"])).toMatchObject({ seller_type: "private", seller_strict: true });
    expect(sellerForPlan(v({ seller_type: "dealer", seller_strict: true }), false, ["private"]))
      .toMatchObject({ seller_type: "private", seller_strict: true });
  });
  it("any plan clears it", () => {
    const cleared = sellerForPlan(v({ seller_type: "private" }), false, ["private"]);
    expect(toFilters(cleared)).not.toHaveProperty("seller_types");
    expect(toPreferences(cleared).seller_type).toBe("private");
  });
});

describe("the form", () => {
  const render = (sellerFilter: boolean | undefined, raw: SearchInput = {}) => renderToStaticMarkup(createElement(SearchForm, {
    catalog: [], sources: [{ id: "mercadolibre", name: "MercadoLibre" }], profileId: 7, sellerFilter, initial: v(raw),
  }));

  it("a plan without the filter never sees the check, nor the new options", () => {
    for (const html of [render(false, { seller_type: "private" }), render(undefined, { seller_type: "dealer" })]) {
      expect(html).not.toContain(SELLER_STRICT.check);
      expect(html).not.toContain(SELLER_STRICT.option.dealer);
      expect(html).toContain(">Particular<");
      expect(html).toContain(">Concesionaria<");
    }
    expect(render(false, { seller_type: "dealer" })).toContain("Incluye posibles agencias.");
  });

  it("Pro sees the options with «posibles agencias», the check and its explanation", () => {
    const html = render(true, { seller_type: "dealer", seller_strict: true });
    expect(html).toContain(">Particulares<");
    expect(html).toContain(">Agencias (incluye posibles agencias)<");
    expect(html).toContain(SELLER_STRICT.check);
    expect(html).toContain(SELLER_STRICT.hint);
    expect(html).not.toContain('data-testid="seller-type-hint"');        // not said twice
    expect(render(true, {})).not.toContain(SELLER_STRICT.check);           // nothing to make strict
  });

  it("a downgraded search says it's Pro's and offers to clear it", () => {
    const html = render(false, { seller_type: "private", seller_strict: true });
    expect(html).toContain(SELLER_STRICT.proOnly);
    expect(html).toContain(SELLER_STRICT.remove);
    expect(html).not.toContain(SELLER_STRICT.check);
    expect(render(true, { seller_type: "private", seller_strict: true })).not.toContain(SELLER_STRICT.proOnly);
  });
});

describe("the summary", () => {
  const html = (props: Partial<ComponentProps<typeof SearchCriteriaSummary>>) => renderToStaticMarkup(createElement(SearchCriteriaSummary, {
    name: "Ford Fiesta", filters: { make: "Ford", model: "Fiesta" }, preferences: {}, radiusKm: null, hasLocation: false, sources: [], ...props,
  }));
  it("Pro: «Solo particulares» among the main facts", () => {
    const out = html({ filters: { make: "Ford", model: "Fiesta", seller_types: ["private"] }, sellerFilter: true });
    expect(out).toContain(">Vendedor<");
    expect(out).toContain("Solo particulares");
    expect(out).not.toContain("<details");
    expect(html({ filters: { make: "Ford", model: "Fiesta", seller_types: ["dealer"] }, sellerFilter: true }))
      .toContain("Solo agencias (incluye posibles agencias)");
  });
  it("downgraded: the preference, and that the strict filter is Pro's", () => {
    const out = html({ filters: { make: "Ford", model: "Fiesta", seller_types: ["private"] } });
    expect(out).toContain("Particulares (preferido; filtro estricto solo Pro)");
    expect(out).not.toContain("Solo particulares");
  });
  it("a plain preference is as before", () => {
    const out = html({ preferences: { seller_type: "private" } });
    expect(out).toContain("Vendedor preferido");
    expect(out).not.toContain("Solo particulares");
  });
});

describe("modo asistido (asumido, a confirmar por Juan: pregunta 2)", () => {
  const base = { ...v({}), make: "", model: "" };
  const draft = (seller_type: "" | "private" | "dealer"): AssistedDraft => ({
    values: {
      make: "Ford", model: "Fiesta", trim: "", trims: [], trim_strict: false, year_min: null, year_max: null, price_max: null,
      price_target: null, currency: "USD", km_max: null, km_target: null, transmission: "", fuel: "", body_types: [],
      seller_type, location: "", locations: [], radius_km: null,
    },
    resolved: true,
    notes: [],
  });
  it("for Pro «particular» is the strict filter, with a note", () => {
    const { values, notes } = draftToValues(draft("private"), base, true, null, true);
    expect([values.seller_type, values.seller_strict]).toEqual(["private", true]);
    expect(notes).toContain("Solo particulares (filtro estricto). Podés cambiarlo editando la búsqueda.");
  });
  it("for any other plan it stays a preference, without a note", () => {
    const { values, notes } = draftToValues(draft("private"), base);
    expect([values.seller_type, values.seller_strict]).toEqual(["private", false]);
    expect(notes).toEqual([]);
    expect(draftToValues(draft(""), base, true, null, true).values.seller_strict).toBe(false);
  });
});
