import { beforeEach, describe, expect, it, vi } from "vitest";

// saveSearch and previewSearch against a fake Supabase client: what reaches
// search_profiles and preview_search for searches with body types (docs/CARROCERIA.md).
const state = vi.hoisted(() => ({
  features: {} as Record<string, boolean>,
  catalog: null as { make: string; model: string; body_types: string[] } | null,
  dbError: null as { code?: string; message: string } | null,
  inserted: null as Record<string, unknown> | null,
  /** The stored row an edit reads first (PRO-01: its filters.seller_types). */
  before: null as Record<string, unknown> | null,
  updated: null as Record<string, unknown> | null,
  active: [] as Record<string, unknown>[],
  /** Answers for successive active-search lookups, before falling back to `active`. */
  activeQueue: [] as Record<string, unknown>[][],
  rpc: [] as [string, Record<string, unknown> | undefined][],
  tables: [] as string[],
  track: vi.fn(),
}));

vi.mock("server-only", () => ({}));
vi.mock("next/cache", () => ({ refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ redirect: vi.fn() }));
vi.mock("@/lib/auth", () => ({ requireUser: vi.fn().mockResolvedValue({ id: "account" }) }));
vi.mock("@/lib/events", () => ({ track: state.track }));
vi.mock("@/lib/meta-pixel-server", () => ({ queuePixel: vi.fn() }));
vi.mock("@/lib/supabase/admin", () => ({ createAdminClient: vi.fn() }));
vi.mock("@/lib/supabase/server", () => ({
  createClient: async () => ({
    rpc: async (name: string, args?: Record<string, unknown>) => {
      state.rpc.push([name, args]);
      if (name === "my_plan_feature") return { data: state.features[String(args?.p_feature)] === true };
      if (name === "preview_search") return { data: { count: 1, sample: [] } };
      return { data: { plan: "pass" } };
    },
    from: (table: string) => {
      state.tables.push(table);
      let activeList = false;
      const result = () => {
        // The user's active searches, checked for an identical one before inserting.
        if (activeList) return { data: state.activeQueue.shift() ?? state.active };
        if (table === "vehicle_catalog") return { data: state.catalog };
        if (table === "sources") return { data: [{ id: "mercadolibre" }, { id: "kavak" }] };
        if (table === "profiles") return { data: { default_channels: ["email"] } };
        return { data: state.before ?? { id: 9, filters: {}, preferences: {}, origin_lat: null, origin_lon: null, radius_km: null }, error: state.dbError, count: 1 };
      };
      const query: Record<string, unknown> = {};
      for (const method of ["select", "eq", "ilike", "is", "limit", "in", "order"]) query[method] = () => query;
      query.eq = (column: string) => { if (table === "search_profiles" && column === "enabled") activeList = true; return query; };
      query.insert = (row: Record<string, unknown>) => { state.inserted = row; return query; };
      query.update = (row: Record<string, unknown>) => { state.updated = row; return query; };
      query.single = query.maybeSingle = async () => result();
      query.then = (resolve: (value: unknown) => unknown, reject: (error: unknown) => unknown) => Promise.resolve(result()).then(resolve, reject);
      return query;
    },
  }),
}));

import { previewSearch, relaxSuggestions, saveSearch, setSearchEnabled } from "@/app/app/searches/actions";
import { MODEL_LESS_UNAVAILABLE } from "@/lib/search-form";

const STAY = { mode: "assisted" as const, jobId: null, edited: false, stay: true };
const SUV = { body_types: ["suv" as const, "pickup" as const], price_max: 20000, sources: ["mercadolibre", "kavak"] };
const CORSA = { make: "chevrolet", model: "corsa", sources: ["mercadolibre", "kavak"] };

beforeEach(() => {
  state.features = {};
  state.catalog = null;
  state.dbError = null;
  state.inserted = null;
  state.before = null;
  state.active = [];
  state.activeQueue = [];
  state.updated = null;
  state.rpc = [];
  state.tables = [];
  state.track.mockClear();
});

describe("saveSearch", () => {
  it("refuses a model-less search without model_less_search, before touching the catalog or the table", async () => {
    expect(await saveSearch(null, SUV, STAY)).toEqual({ error: MODEL_LESS_UNAVAILABLE });
    expect(state.inserted).toBeNull();
    expect(state.tables).not.toContain("vehicle_catalog");
  });

  it("saves a model-less search without make or model, named by its body types", async () => {
    state.features.model_less_search = true;
    expect(await saveSearch(null, SUV, STAY)).toEqual({ savedId: 9 });
    expect(state.inserted).toMatchObject({
      name: "SUV o Pick-up hasta USD 20.000",
      filters: { body_types: ["suv", "pickup"], price_max: 20000, currency: "USD" },
    });
    expect(state.inserted?.filters).not.toHaveProperty("make");
    expect(state.track).toHaveBeenCalledWith(expect.anything(), "account", "search_profile_created", expect.objectContaining({ by_body_type: true }));
  });

  it("asks for the max price before saving", async () => {
    state.features.model_less_search = true;
    const result = await saveSearch(null, { ...SUV, price_max: null }, STAY);
    expect(result.fields).toEqual({ price_max: "Poné un precio máximo para buscar por carrocería." });
    expect(state.inserted).toBeNull();
  });

  it("keeps within a model only the body types the catalog offers for it", async () => {
    state.catalog = { make: "Chevrolet", model: "Corsa", body_types: ["hatchback", "sedan", "rural"] };
    await saveSearch(null, { ...CORSA, body_types: ["rural", "suv"] }, STAY);
    expect(state.inserted).toMatchObject({ name: "Chevrolet Corsa", filters: { make: "Chevrolet", model: "Corsa", body_types: ["rural"] } });
    expect(state.rpc.map(([name, args]) => args?.p_feature ?? name)).not.toContain("model_less_search");
    // One body type is certain: no filter.
    state.catalog = { make: "Chevrolet", model: "S10", body_types: ["pickup"] };
    await saveSearch(null, { ...CORSA, model: "s10", body_types: ["pickup"] }, STAY);
    expect(state.inserted?.filters).not.toHaveProperty("body_types");
  });

  it("opens the identical active search instead of creating a second one", async () => {
    state.catalog = { make: "Chevrolet", model: "Corsa", body_types: [] };
    await saveSearch(null, CORSA, STAY);
    const first = state.inserted!;
    state.inserted = null;
    state.active = [{ id: 5, filters: first.filters, origin_lat: null, origin_lon: null, radius_km: null }];
    expect(await saveSearch(null, CORSA, STAY)).toEqual({ savedId: 5 });
    expect(state.inserted).toBeNull();
  });

  it("recognizes the identical search whatever order the database returns the filters' keys in", async () => {
    state.catalog = { make: "Chevrolet", model: "Corsa", body_types: [] };
    const zones = [{ label: "Corrientes, Corrientes", lat: -27.4692, lon: -58.8306, radius_km: 30 }];
    const withZones = { ...CORSA, location: { label: "Resistencia, Chaco", lat: -27.4519, lon: -58.9867, radius_km: 30 }, extra_locations: zones };
    await saveSearch(null, withZones, STAY);
    const sent = state.inserted!;
    state.inserted = null;
    // jsonb gives short keys first and orders nested ones its own way.
    const reordered = Object.fromEntries(Object.entries(sent.filters as Record<string, unknown>).reverse().map(([k, v]) =>
      [k, k === "extra_locations" ? (v as Record<string, unknown>[]).map((z) => Object.fromEntries(Object.entries(z).reverse())) : v]));
    state.dbError = { code: "23505", message: 'duplicate key value violates unique constraint "search_profiles_active_unique_idx"' };
    state.activeQueue = [[], [{ id: 11, filters: reordered, origin_lat: sent.origin_lat, origin_lon: sent.origin_lon, radius_km: sent.radius_km }]];
    expect(await saveSearch(null, withZones, STAY)).toEqual({ savedId: 11 });
  });

  it("opens the winner when an identical submit got in first (the database's unique index)", async () => {
    state.catalog = { make: "Chevrolet", model: "Corsa", body_types: [] };
    await saveSearch(null, CORSA, STAY);
    const filters = state.inserted!.filters;
    state.activeQueue = [[], [{ id: 7, filters, origin_lat: null, origin_lon: null, radius_km: null }]];
    state.dbError = { code: "23505", message: 'duplicate key value violates unique constraint "search_profiles_active_unique_idx"' };
    expect(await saveSearch(null, CORSA, STAY)).toEqual({ savedId: 7 });
  });

  it("explains an edit or a resume that would duplicate another active search", async () => {
    state.catalog = { make: "Chevrolet", model: "Corsa", body_types: [] };
    state.dbError = { code: "23505", message: 'duplicate key value violates unique constraint "search_profiles_active_unique_idx"' };
    const duplicate = { error: expect.stringContaining("Ya tenés otra búsqueda activa igual") };
    expect(await saveSearch(9, CORSA)).toEqual(duplicate);
    expect(await setSearchEnabled(9, true)).toEqual(duplicate);
  });

  it("records a refused creation (search_save_failed), not a refused edit", async () => {
    state.dbError = { message: "plan_limit_exceeded" };
    state.catalog = { make: "Chevrolet", model: "Corsa", body_types: [] };
    const auto = { mode: "assisted_auto" as const, jobId: 42, edited: false, stay: true };
    expect(await saveSearch(null, CORSA, auto)).toEqual({ error: "Llegaste al máximo de búsquedas de tu plan." });
    expect(state.track).toHaveBeenCalledWith(expect.anything(), "account", "search_save_failed", {
      reason: "Llegaste al máximo de búsquedas de tu plan.", fields: [], llm_job_id: 42, mode: "assisted_auto",
    });
    state.track.mockClear();
    state.catalog = null;
    await saveSearch(9, CORSA);
    expect(state.track).not.toHaveBeenCalledWith(expect.anything(), "account", "search_save_failed", expect.anything());
  });

  it.each([
    ["plan_feature_unavailable", { error: MODEL_LESS_UNAVAILABLE }],
    ["search_needs_model_or_body_type", { error: "Elegí un modelo o al menos una carrocería.",
      fields: { model: "Elegí un modelo.", body_types: "Elegí al menos una carrocería." } }],
    ["search_needs_max_price", { error: "Poné un precio máximo para buscar por carrocería.",
      fields: { price_max: "Poné un precio máximo para buscar por carrocería." } }],
  ])("words the database's %s when creating and editing", async (code, expected) => {
    state.features.model_less_search = true;
    state.dbError = { message: code };
    expect(await saveSearch(null, SUV, STAY)).toEqual(expected);
    expect(await saveSearch(9, SUV)).toEqual(expected);
  });
});

describe("previewSearch", () => {
  it("counts a model-less search only for a plan that can save it", async () => {
    expect(await previewSearch(SUV)).toBeNull();
    expect(state.rpc.map(([name]) => name)).not.toContain("preview_search");
    state.features.model_less_search = true;
    expect(await previewSearch(SUV)).toEqual({ count: 1, sample: [] });
    const [, args] = state.rpc.find(([name]) => name === "preview_search")!;
    expect(args?.p_filters).toEqual({ body_types: ["suv", "pickup"], price_max: 20000, currency: "USD" });
  });
});

describe("relaxSuggestions", () => {
  it("counts each loosened variant once, with only that filter changed", async () => {
    const audi = { make: "Audi", model: "A3", year_min: 2010, year_max: 2012, price_max: 11000, km_max: 150000, sources: ["mercadolibre", "kavak"] };
    const suggestions = await relaxSuggestions(audi);
    expect(suggestions.map((s) => s.label)).toEqual(["2008–2014", "Hasta USD 13.000", "Sin tope de km"]);
    expect(suggestions.every((s) => s.count === 1)).toBe(true);
    const filters = state.rpc.filter(([name]) => name === "preview_search").map(([, args]) => args?.p_filters as Record<string, unknown>);
    expect(filters).toHaveLength(3);
    expect(filters[0]).toMatchObject({ year_min: 2008, year_max: 2014, price_max: 11000, km_max: 150000 });
    expect(filters[1]).toMatchObject({ year_min: 2010, price_max: 13000, km_max: 150000 });
    expect(filters[2]).not.toHaveProperty("km_max");
  });

  it("asks nothing for a model-less search or an invalid one", async () => {
    expect(await relaxSuggestions(SUV)).toEqual([]);
    expect(await relaxSuggestions({ ...CORSA, year_min: 2020, year_max: 2010 })).toEqual([]);
    expect(state.rpc.map(([name]) => name)).not.toContain("preview_search");
  });
});

describe("PRO-01: the strict seller filter (decisión 8)", () => {
  const FIESTA = { make: "ford", model: "fiesta", sources: ["mercadolibre", "kavak"] };
  const stored = (filters: Record<string, unknown>) => ({
    id: 9, filters: { make: "Ford", model: "Fiesta", trims: [], trim_strict: false, ...filters }, preferences: {}, origin_lat: null, origin_lon: null, radius_km: null,
  });
  const events = (name: string) => state.track.mock.calls.filter((c) => c[2] === name).map((c) => c[3]);
  beforeEach(() => { state.catalog = { make: "Ford", model: "Fiesta", body_types: [] }; });

  it("Pro stores it and records seller_filter_set", async () => {
    state.features.seller_filter = true;
    await saveSearch(null, { ...FIESTA, seller_type: "private", seller_strict: true }, STAY);
    expect(state.inserted?.filters).toMatchObject({ seller_types: ["private"] });
    expect(state.inserted?.preferences).not.toHaveProperty("seller_type");
    expect(events("seller_filter_set")).toEqual([{ profile_id: 9, seller_types: ["private"], mode: "assisted" }]);
  });

  it("without the feature a new one is not stored: the type is the preference", async () => {
    await saveSearch(null, { ...FIESTA, seller_type: "private", seller_strict: true }, STAY);
    expect(state.inserted?.filters).not.toHaveProperty("seller_types");
    expect(state.inserted?.preferences).toMatchObject({ seller_type: "private" });
    expect(events("seller_filter_set")).toEqual([]);
  });

  it("without the feature an edit keeps the stored one (no spurious rematch) and never replaces it", async () => {
    state.before = stored({ seller_types: ["private"] });
    await saveSearch(9, { ...FIESTA, seller_type: "private", seller_strict: true });
    expect(state.updated?.filters).toMatchObject({ seller_types: ["private"] });
    expect(state.updated).not.toHaveProperty("rematch_requested_at");
    expect(events("seller_filter_set")).toEqual([]);
    await saveSearch(9, { ...FIESTA, seller_type: "dealer", seller_strict: true });
    expect(state.updated?.filters).toMatchObject({ seller_types: ["private"] });
  });

  it("any plan clears it («Quitar filtro estricto»), with a rematch and the event", async () => {
    state.before = stored({ seller_types: ["private"] });
    await saveSearch(9, { ...FIESTA, seller_type: "private", seller_strict: false });
    expect(state.updated?.filters).not.toHaveProperty("seller_types");
    expect(state.updated?.preferences).toMatchObject({ seller_type: "private" });
    expect(state.updated).toHaveProperty("rematch_requested_at");
    expect(events("seller_filter_set")).toEqual([{ profile_id: 9, seller_types: [], mode: "edit" }]);
  });

  it("Pro with a malformed value: an error and nothing written", async () => {
    state.features.seller_filter = true;
    for (const bad of [
      { seller_type: "dealer_inferred", seller_strict: true },
      { seller_type: "private", seller_strict: "true" },
      { seller_type: "", seller_strict: true },
      { seller_type: ["private", "dealer"], seller_strict: true },
    ]) {
      const result = await saveSearch(null, { ...FIESTA, ...bad } as never, STAY);
      expect(result.error).toBe("Revisá los campos marcados.");
      expect(state.inserted).toBeNull();
    }
  });

  it("seller_filter_set only when it changes", async () => {
    state.features.seller_filter = true;
    state.before = stored({ seller_types: ["private"] });
    await saveSearch(9, { ...FIESTA, seller_type: "private", seller_strict: true, km_max: 100000 });
    expect(events("seller_filter_set")).toEqual([]);
    await saveSearch(9, { ...FIESTA, seller_type: "dealer", seller_strict: true });
    expect(events("seller_filter_set")).toEqual([{ profile_id: 9, seller_types: ["dealer"], mode: "edit" }]);
  });
});
