import { beforeEach, describe, expect, it, vi } from "vitest";

import type { PlanLimits } from "@/lib/pro";
import type { SearchSource } from "@/lib/search-collection";

// Aviso de zona (docs/AVISO_ZONA.md): what the server helper asks preview_search, and what it answers.
const state = vi.hoisted(() => ({
  rpc: [] as Record<string, unknown>[],
  /** preview_search's count by radius ("pais": no zone); null fails. */
  previews: {} as Record<string, number | null>,
  events: { data: [] as unknown, error: null as unknown },
  filters: [] as [string, unknown][],
}));
vi.mock("server-only", () => ({}));
import { allCount, dismissedZones, zoneNotice } from "@/lib/zone-notice-server";

const supabase = {
  rpc: async (name: string, args: Record<string, unknown>) => {
    state.rpc.push({ name, ...args });
    const count = state.previews[args.p_radius_km == null ? "pais" : String(args.p_radius_km)];
    return count == null ? { data: null, error: { message: "timeout" } } : { data: { count, sample: [] }, error: null };
  },
  from: (table: string) => {
    const query = {
      select: () => query,
      eq: (column: string, value: unknown) => { state.filters.push([`${table}.${column}`, value]); return query; },
      then: (resolve: (value: unknown) => unknown) => Promise.resolve(state.events).then(resolve),
    };
    return query;
  },
} as unknown as Parameters<typeof zoneNotice>[0];

const FILTERS = { make: "Toyota", model: "Corolla", location_label: "Mi zona aproximada", sources: ["mercadolibre", "kavak"] };
const PROFILE = {
  id: 7, enabled: true, filters: FILTERS, origin_lat: -34.6, origin_lon: -58.4, radius_km: 30,
  bootstrapped_at: "2026-10-30T12:00:00Z", rematch_requested_at: null,
};
const source = (patch: Partial<SearchSource> = {}): SearchSource => ({
  id: "mercadolibre", name: "Mercado Libre", enabled: true, collectionState: "done", firstRead: false, newTarget: false, ...patch,
});
const ask = (patch: Partial<Parameters<typeof zoneNotice>[1]> = {}) =>
  zoneNotice(supabase, { profile: PROFILE, count: 1, access: null, sources: [source()], dismissed: [], ...patch });
const previews = () => state.rpc.filter((call) => call.name === "preview_search");

beforeEach(() => {
  state.rpc = [];
  state.previews = { 30: 1, 100: 6, 200: 14, pais: 50 };
  state.events = { data: [], error: null };
  state.filters = [];
});

describe("zoneNotice", () => {
  it("counts the zone, each wider radius and the whole country with the stored filters", async () => {
    expect(await ask({ sources: [source({ newTarget: true }), source({ id: "kavak", name: "Kavak" })] })).toEqual({
      state: "show",
      notice: {
        profileId: 7, count: 1, place: "tu zona aproximada", kind: "ip", zone: [-34.6, -58.4, 30],
        options: [{ to: 100, count: 6, capped: false }, { to: "pais", count: 50, capped: false }],
        cold: true,
      },
    });
    const at = (lat: number, lon: number, radius: number) => ({ p_origin_lat: lat, p_origin_lon: lon, p_radius_km: radius });
    expect(previews()).toEqual([
      { name: "preview_search", p_filters: FILTERS, ...at(-34.6, -58.4, 30) },
      // The whole country: no place in the filters, no zone.
      { name: "preview_search", p_filters: { make: "Toyota", model: "Corolla", sources: ["mercadolibre", "kavak"] } },
      { name: "preview_search", p_filters: FILTERS, ...at(-34.6, -58.4, 100) },
      { name: "preview_search", p_filters: FILTERS, ...at(-34.6, -58.4, 200) },
    ]);
  });
  it("only counts the radii above the search's own", async () => {
    await ask({ profile: { ...PROFILE, radius_km: 150 } });
    expect(previews().map((call) => call.p_radius_km ?? "pais")).toEqual([150, "pais", 200]);
  });
  it("asks preview_search nothing while the search is not ready or the notice doesn't apply", async () => {
    expect(await ask({ sources: [source({ firstRead: true })] })).toEqual({ state: "pending" });
    expect(await ask({ profile: { ...PROFILE, bootstrapped_at: null } })).toEqual({ state: "pending" });
    expect(await ask({ count: 4 })).toEqual({ state: "none" });
    expect(await ask({ dismissed: [[-34.6, -58.4, 30]] })).toEqual({ state: "none" });
    const reached: PlanLimits = { plan: "free", enforced: true, free_results_used: 50, free_results_limit: 50, limits: { max_visible_results: 50 } };
    expect(await ask({ access: reached })).toEqual({ state: "none" });
    expect(previews()).toEqual([]);
  });
  it("waits while something can't be read: the card asks again", async () => {
    expect(await ask({ sources: null })).toEqual({ state: "pending" });
    expect(await ask({ sources: [source(), source({ id: "kavak", name: "Kavak", collectionState: "unknown" })] })).toEqual({ state: "pending" });
    expect(await ask({ dismissed: null })).toEqual({ state: "pending" });
    expect(previews()).toEqual([]);
    state.previews[100] = null;
    expect(await ask()).toEqual({ state: "pending" });
  });
  it("shows nothing when no option gets to four", async () => {
    state.previews = { 30: 1, 100: 2, 200: 3, pais: 3 };
    expect(await ask()).toEqual({ state: "none" });
  });
  it("caps the options at what an enforced free trial can still show", async () => {
    state.previews = { 30: 1, 100: 6, 200: 30, pais: 80 };
    const trial: PlanLimits = { plan: "free", enforced: true, free_results_used: 40, free_results_limit: 50, limits: { max_visible_results: 50 } };
    const answer = await ask({ access: trial });
    // One visible now plus the ten left of the trial's fifty.
    expect(answer.state === "show" && answer.notice.options).toEqual([
      { to: 100, count: 6, capped: false },
      { to: "pais", count: 11, capped: true },
    ]);
    // The pilot doesn't enforce the plan: no cap.
    const pilot = await ask({ access: { ...trial, enforced: false } });
    expect(pilot.state === "show" && pilot.notice.options.at(-1)).toEqual({ to: "pais", count: 80, capped: false });
  });
  it("names a place the person chose", async () => {
    const answer = await ask({ profile: { ...PROFILE, filters: { ...FILTERS, location_label: "Laferrere" } } });
    expect(answer.state === "show" && [answer.notice.place, answer.notice.kind, answer.notice.cold]).toEqual(["Laferrere", "named", false]);
  });
});

describe("dismissedZones and allCount", () => {
  it("reads the zones «Dejar así» hid for this search, skipping what doesn't parse", async () => {
    state.events = { data: [{ props: { zone: [-34.6, -58.4, 30] } }, { props: { zone: "x" } }, { props: null }], error: null };
    expect(await dismissedZones(supabase, 7)).toEqual([[-34.6, -58.4, 30]]);
    expect(state.filters).toEqual([["events.name", "zone_notice_dismissed"], ["events.props->>profile_id", "7"]]);
    // Unread is not «none hidden»: the notice waits.
    state.events = { data: null, error: { message: "denied" } };
    expect(await dismissedZones(supabase, 7)).toBeNull();
  });
  it("takes the «Todos» count only when it is a number", () => {
    expect(allCount([{ all_count: 2 }])).toBe(2);
    expect(allCount([{ all_count: 0 }])).toBe(0);
    expect(allCount([])).toBeNull();
    expect(allCount(null)).toBeNull();
    expect(allCount([{ all_count: "2" }])).toBeNull();
  });
});
