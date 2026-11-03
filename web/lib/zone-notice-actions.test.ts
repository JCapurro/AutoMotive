import { beforeEach, describe, expect, it, vi } from "vitest";

// Aviso de zona (docs/AVISO_ZONA.md): the server actions against a fake Supabase client.
const state = vi.hoisted(() => ({
  profile: null as Record<string, unknown> | null,
  updateError: null as { code?: string; message: string } | null,
  updatedRows: [{ id: 7 }] as unknown[],
  /** [table, row, eq filters] of each update, in order. */
  updates: [] as [string, Record<string, unknown>, [string, unknown][]][],
  /** [table, eq filters] of each read, in order. */
  reads: [] as [string, [string, unknown][]][],
  /** A table or function whose read fails. */
  failing: null as string | null,
  events: [] as { props: unknown }[],
  rpc: [] as [string, Record<string, unknown> | undefined][],
  counts: [{ all_count: 1 }] as unknown,
  /** Whether the event was recorded. */
  track: vi.fn<(...args: unknown[]) => Promise<boolean>>(async () => true),
  refresh: vi.fn(),
  collection: vi.fn(),
}));
vi.mock("server-only", () => ({}));
vi.mock("next/cache", () => ({ refresh: state.refresh }));
vi.mock("next/navigation", () => ({ redirect: vi.fn() }));
vi.mock("@/lib/auth", () => ({ requireUser: vi.fn().mockResolvedValue({ id: "account" }) }));
vi.mock("@/lib/events", () => ({ track: state.track }));
vi.mock("@/lib/meta-pixel-server", () => ({ queuePixel: vi.fn() }));
vi.mock("@/lib/supabase/admin", () => ({ createAdminClient: vi.fn() }));
vi.mock("@/lib/search-collection-server", () => ({ loadSearchCollection: state.collection }));
vi.mock("@/lib/supabase/server", () => ({
  createClient: async () => ({
    rpc: async (name: string, args?: Record<string, unknown>) => {
      state.rpc.push([name, args]);
      if (name === state.failing) return { data: null, error: { message: "timeout" } };
      if (name === "search_result_counts") return { data: state.counts, error: null };
      if (name === "my_plan_limits") return { data: { plan: "pass", enforced: false, limits: {} }, error: null };
      if (name === "preview_search") return { data: { count: args?.p_radius_km == null ? 50 : args.p_radius_km === 30 ? 1 : 6 }, error: null };
      return { data: null, error: null };
    },
    from: (table: string) => {
      let update: Record<string, unknown> | null = null;
      const eqs: [string, unknown][] = [];
      const result = () => {
        if (update) {
          state.updates.push([table, update, eqs]);
          return table === "search_profiles" ? { data: state.updateError ? null : state.updatedRows, error: state.updateError } : { data: null, error: null };
        }
        state.reads.push([table, eqs]);
        if (table === state.failing) return { data: null, error: { message: "timeout" } };
        if (table === "events") return { data: state.events, error: null };
        if (table === "sources") return { data: [{ id: "mercadolibre", name: "Mercado Libre", enabled: true }], error: null };
        return { data: state.profile, error: null };
      };
      const query: Record<string, unknown> = {};
      for (const method of ["select", "order", "limit"]) query[method] = () => query;
      query.eq = (column: string, value: unknown) => { eqs.push([column, value]); return query; };
      query.update = (row: Record<string, unknown>) => { update = row; return query; };
      query.maybeSingle = async () => result();
      query.then = (resolve: (value: unknown) => unknown, reject: (error: unknown) => unknown) => Promise.resolve(result()).then(resolve, reject);
      return query;
    },
  }),
}));

import { dismissZoneNotice, trackZoneNoticeShown, widenSearchZone, zoneNoticeFor } from "@/app/app/searches/actions";
import type { Zone, ZoneNoticeData } from "@/lib/zone-notice";

const WIDEN_FAILED = { error: "No pudimos ampliar la zona. Probá de nuevo." };
const FILTERS = { make: "Toyota", model: "Corolla", location_label: "Laferrere", sources: ["mercadolibre"] };
const PROFILE = {
  id: 7, user_id: "account", enabled: true, filters: FILTERS, origin_lat: -34.75, origin_lon: -58.58, radius_km: 30,
  bootstrapped_at: "2026-10-30T12:00:00Z", rematch_requested_at: null, created_at: "2026-10-30T11:58:00Z",
};
const ZONE: Zone = [-34.75, -58.58, 30];
const SHOWN = { zone: ZONE, count: 1, options: 2 };
const tracked = () => state.track.mock.calls.map(([, user, name, props]) => [user, name, props]);

beforeEach(() => {
  state.profile = { ...PROFILE };
  state.updateError = null;
  state.updatedRows = [{ id: 7 }];
  state.updates = [];
  state.reads = [];
  state.failing = null;
  state.events = [];
  state.rpc = [];
  state.counts = [{ all_count: 1 }];
  state.track.mockClear();
  state.refresh.mockClear();
  state.collection.mockReset();
  state.collection.mockResolvedValue([{ id: "mercadolibre", name: "Mercado Libre", enabled: true, collectionState: "done", firstRead: false, newTarget: false }]);
});

describe("widenSearchZone", () => {
  it("widens the radius around the same place and asks the worker to redo the backfill", async () => {
    expect(await widenSearchZone(7, 100, "card", SHOWN)).toEqual({});
    const [[table, row, eqs], diagnoses] = state.updates;
    expect([table, eqs]).toEqual(["search_profiles", [["id", 7]]]);
    expect(row).toEqual({ radius_km: 100, rematch_requested_at: expect.any(String) });
    // The bot's card spoke of the old zone.
    expect(diagnoses).toEqual(["search_diagnoses", { dismissed_at: row.rematch_requested_at }, [["search_profile_id", 7]]]);
    expect(tracked()).toEqual([
      ["account", "search_zone_widened", { profile_id: 7, place: "card", zone_kind: "named", from_radius: 30, to: 100, all_count: 1, option_count: 2 }],
      ["account", "search_profile_updated", { profile_id: 7, filters_changed: true, via: "zone_notice" }],
    ]);
    // The card updates itself; only the results page refreshes.
    expect(state.refresh).not.toHaveBeenCalled();
  });
  it("searches the whole country as the form saves it: no place, no zone", async () => {
    state.profile = { ...PROFILE, filters: { ...FILTERS, location_label: "Mi zona aproximada" } };
    expect(await widenSearchZone(7, "pais", "page", SHOWN)).toEqual({});
    expect(state.updates[0][1]).toEqual({
      origin_lat: null, origin_lon: null, radius_km: null,
      filters: { make: "Toyota", model: "Corolla", sources: ["mercadolibre"] },
      rematch_requested_at: expect.any(String),
    });
    expect(tracked()[0][2]).toMatchObject({ place: "page", zone_kind: "ip", to: "pais" });
    expect(state.refresh).toHaveBeenCalledOnce();
  });
  it("refuses what the notice never offers, without touching the search", async () => {
    expect(await widenSearchZone(7, 150 as never, "card", SHOWN)).toEqual(WIDEN_FAILED);
    expect(await widenSearchZone(7, 100, "email" as never, SHOWN)).toEqual(WIDEN_FAILED);
    expect(await widenSearchZone(-1, 100, "card", SHOWN)).toEqual(WIDEN_FAILED);
    expect(await widenSearchZone(7, 100, "card", { count: 1, options: 2 } as never)).toEqual(WIDEN_FAILED);
    state.profile = { ...PROFILE, radius_km: 100 };
    expect(await widenSearchZone(7, 100, "card", { ...SHOWN, zone: [-34.75, -58.58, 100] })).toEqual(WIDEN_FAILED);
    state.profile = { ...PROFILE, enabled: false };
    expect(await widenSearchZone(7, 100, "card", SHOWN)).toEqual({ error: "Reanudá la búsqueda para ampliar la zona." });
    state.profile = null;
    expect(await widenSearchZone(7, 100, "card", SHOWN)).toEqual({ error: "La búsqueda no existe." });
    expect(state.updates).toEqual([]);
    expect(state.track).not.toHaveBeenCalled();
  });
  it("leaves a search edited since the notice: its counts were for the zone it showed", async () => {
    const CHANGED = { error: "La búsqueda cambió. Volvé a abrirla para ver su zona." };
    // Another tab widened it already, moved it, took its zone away or added a place.
    state.profile = { ...PROFILE, radius_km: 100 };
    expect(await widenSearchZone(7, 100, "card", SHOWN)).toEqual(CHANGED);
    state.profile = { ...PROFILE, origin_lat: -31.42, origin_lon: -64.18 };
    expect(await widenSearchZone(7, 100, "card", SHOWN)).toEqual(CHANGED);
    state.profile = { ...PROFILE, origin_lat: null, origin_lon: null, radius_km: null };
    expect(await widenSearchZone(7, "pais", "card", SHOWN)).toEqual(CHANGED);
    state.profile = { ...PROFILE, filters: { ...FILTERS, extra_locations: [{ label: "Morón", lat: -34.65, lon: -58.62, radius_km: 30 }] } };
    expect(await widenSearchZone(7, 100, "card", SHOWN)).toEqual(CHANGED);
    expect(state.updates).toEqual([]);
    expect(state.track).not.toHaveBeenCalled();
  });
  it("asks to try again when the search can't be read, not that it's gone", async () => {
    state.failing = "search_profiles";
    expect(await widenSearchZone(7, 100, "card", SHOWN)).toEqual(WIDEN_FAILED);
    expect(state.updates).toEqual([]);
    expect(state.track).not.toHaveBeenCalled();
  });
  it("says why the database refused it, and records nothing", async () => {
    state.updateError = { code: "23505", message: 'duplicate key value violates unique constraint "search_profiles_active_unique_idx"' };
    expect((await widenSearchZone(7, 200, "card", SHOWN)).error).toMatch(/^Ya tenés otra búsqueda activa igual/);
    state.updateError = { message: "plan_access_expired" };
    expect(await widenSearchZone(7, 200, "card", SHOWN)).toEqual({ error: "Tu acceso venció. Elegí un plan para volver a buscar." });
    state.updateError = null;
    state.updatedRows = [];
    expect(await widenSearchZone(7, 200, "card", SHOWN)).toEqual(WIDEN_FAILED);
    expect(state.updates.map(([table]) => table)).toEqual(["search_profiles", "search_profiles", "search_profiles"]);
    expect(state.track).not.toHaveBeenCalled();
  });
});

describe("dismissZoneNotice", () => {
  it("hides the notice for this zone, and the bot's card with it", async () => {
    expect(await dismissZoneNotice(7, "page", ZONE)).toEqual({});
    expect(tracked()).toEqual([["account", "zone_notice_dismissed", { profile_id: 7, zone: [-34.75, -58.58, 30], place: "page" }]]);
    expect(state.updates).toEqual([["search_diagnoses", { dismissed_at: expect.any(String) }, [["search_profile_id", 7]]]]);
    expect(state.refresh).toHaveBeenCalledOnce();
    expect(await dismissZoneNotice(7, "card", ZONE)).toEqual({});
    expect(state.refresh).toHaveBeenCalledOnce();
  });
  it("records nothing for a search whose zone changed since the notice", async () => {
    state.profile = { ...PROFILE, origin_lat: null, origin_lon: null, radius_km: null };
    expect(await dismissZoneNotice(7, "page", ZONE)).toEqual({});
    state.profile = { ...PROFILE, radius_km: 100 };
    expect(await dismissZoneNotice(7, "card", ZONE)).toEqual({});
    expect(state.track).not.toHaveBeenCalled();
    expect(state.updates).toEqual([]);
    // The page shows the search as it is now.
    expect(state.refresh).toHaveBeenCalledOnce();
  });
  it("says so when the choice wasn't saved, and the notice stays to try again", async () => {
    const KEEP_FAILED = { error: "No pudimos guardar tu elección. Probá de nuevo." };
    state.failing = "search_profiles";
    expect(await dismissZoneNotice(7, "page", ZONE)).toEqual(KEEP_FAILED);
    expect(state.track).not.toHaveBeenCalled();
    state.failing = null;
    state.track.mockResolvedValueOnce(false);
    expect(await dismissZoneNotice(7, "page", ZONE)).toEqual(KEEP_FAILED);
    expect(await dismissZoneNotice(7, "page", [1, 2] as never)).toEqual(KEEP_FAILED);
    expect(state.updates).toEqual([]);
    expect(state.refresh).not.toHaveBeenCalled();
  });
});

describe("trackZoneNoticeShown", () => {
  const NOTICE: ZoneNoticeData = {
    profileId: 7, count: 1, place: "Laferrere", kind: "named", zone: [-34.75, -58.58, 30],
    options: [{ to: 100, count: 6, capped: false }, { to: "pais", count: 50, capped: true }], cold: true,
  };

  it("records it once per search and zone, whatever the placement", async () => {
    await trackZoneNoticeShown("card", NOTICE);
    expect(state.reads).toEqual([["events", [["name", "zone_notice_shown"], ["props->>profile_id", "7"]]]]);
    expect(tracked()).toEqual([["account", "zone_notice_shown", {
      profile_id: 7, place: "card", zone: [-34.75, -58.58, 30], zone_kind: "named", cold: true,
      count_source: "all_count", all_count: 1, options: ["100:6", "pais:50+"],
    }]]);
    state.track.mockClear();
    state.events = [{ props: { profile_id: 7, zone: [-34.75, -58.58, 30] } }];
    await trackZoneNoticeShown("page", NOTICE);
    expect(state.track).not.toHaveBeenCalled();
    // A zone widened since asks again.
    await trackZoneNoticeShown("page", { ...NOTICE, zone: [-34.75, -58.58, 100] });
    expect(tracked()[0][2]).toMatchObject({ place: "page", zone: [-34.75, -58.58, 100] });
  });
  it("ignores a notice that doesn't name a search and a zone", async () => {
    await trackZoneNoticeShown("card", { ...NOTICE, profileId: 0 });
    await trackZoneNoticeShown("card", { ...NOTICE, zone: [1, 2] as never });
    expect(state.track).not.toHaveBeenCalled();
  });
});

describe("zoneNoticeFor", () => {
  it("waits for a search still being prepared without reading its sources", async () => {
    state.profile = { ...PROFILE, bootstrapped_at: null };
    expect(await zoneNoticeFor(7)).toEqual({ state: "pending" });
    expect(state.collection).not.toHaveBeenCalled();
    expect(state.rpc.map(([name]) => name)).not.toContain("preview_search");
  });
  it("counts a ready search, holding it while a source is on its first read", async () => {
    expect(await zoneNoticeFor(7)).toEqual({
      state: "show",
      notice: {
        profileId: 7, count: 1, place: "Laferrere", kind: "named", zone: [-34.75, -58.58, 30],
        options: [{ to: 100, count: 6, capped: false }, { to: "pais", count: 50, capped: false }], cold: false,
      },
    });
    expect(state.collection).toHaveBeenCalledWith(expect.objectContaining({ id: 7 }), "account", [{ id: "mercadolibre", name: "Mercado Libre", enabled: true }]);
    state.collection.mockResolvedValue([{ id: "mercadolibre", name: "Mercado Libre", enabled: true, collectionState: "loading", firstRead: true }]);
    expect(await zoneNoticeFor(7)).toEqual({ state: "pending" });
  });
  it("answers none for a search that isn't there or has enough results", async () => {
    expect(await zoneNoticeFor(0)).toEqual({ state: "none" });
    state.counts = [{ all_count: 9 }];
    expect(await zoneNoticeFor(7)).toEqual({ state: "none" });
    state.profile = null;
    expect(await zoneNoticeFor(7)).toEqual({ state: "none" });
    expect(state.collection).not.toHaveBeenCalled();
  });
  it("waits when a read fails, so the card asks again: none would end its polling", async () => {
    for (const failing of ["search_profiles", "search_result_counts", "my_plan_limits", "events"]) {
      state.failing = failing;
      expect([failing, await zoneNoticeFor(7)]).toEqual([failing, { state: "pending" }]);
    }
    expect(state.collection).not.toHaveBeenCalled();
    // The sources unread, and a count that fails.
    state.failing = null;
    state.collection.mockResolvedValue(null);
    expect(await zoneNoticeFor(7)).toEqual({ state: "pending" });
    state.collection.mockResolvedValue([{ id: "mercadolibre", name: "Mercado Libre", enabled: true, collectionState: "done", firstRead: false, newTarget: false }]);
    state.failing = "preview_search";
    expect(await zoneNoticeFor(7)).toEqual({ state: "pending" });
  });
});
