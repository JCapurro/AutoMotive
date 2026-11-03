import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ZoneNoticeAnswer, ZoneNoticeData } from "@/lib/zone-notice";

// Aviso de zona (docs/AVISO_ZONA.md) on the results page: it takes the low-results bot's place while it shows.
const state = vi.hoisted(() => ({
  answer: { state: "none" } as ZoneNoticeAnswer,
  zoneNotice: vi.fn(),
  dismissed: [] as unknown[],
  diagnosis: null as Record<string, unknown> | null,
  limitsError: false,
  firstRead: false,
  /** app_config.zone_notice as webConfig reads it; null: unread. */
  zoneSwitch: { enabled: true } as { enabled: boolean } | null,
}));
vi.mock("server-only", () => ({}));
vi.mock("@/lib/cost-estimate-data", () => ({ costLinesFor: async () => new Map() }));
vi.mock("@/lib/margin-data", () => ({ marginAccess: async () => null, marginLinesFor: async () => new Map(), marginTeasersFor: async () => new Set() }));
vi.mock("@/lib/search-collection-server", () => ({
  loadSearchCollection: async () => [{ id: "mercadolibre", name: "MercadoLibre", enabled: true, collectionState: "done", firstRead: state.firstRead }],
}));
vi.mock("@/lib/auth", () => ({ requireUser: async () => ({ id: "user", email: "persona@example.com" }) }));
vi.mock("@/lib/config", () => ({ webConfig: async () => ({ zoneNotice: state.zoneSwitch }) }));
vi.mock("@/components/app/auto-refresh", () => ({ AutoRefresh: ({ every }: { every?: number }) => createElement("i", { "data-refresh": every }) }));
vi.mock("@/components/app/free-result-limit", () => ({ FreeResultLimit: () => null }));
vi.mock("@/components/app/search-actions", () => ({ FrequencySelect: () => null, PauseButton: () => null }));
vi.mock("@/components/app/sort-select", () => ({ SortSelect: () => null }));
vi.mock("@/components/app/search-criteria-summary", () => ({ SearchCriteriaSummary: () => null }));
vi.mock("@/components/app/pro-cta", () => ({ ProBanner: () => null, VisibleResultsReport: () => null }));
vi.mock("@/components/app/listing-card", () => ({ LISTING_ROWS: "listings", ListingCard: () => createElement("article") }));
vi.mock("@/components/app/low-results-notice", () => ({ LowResultsNotice: () => createElement("aside", { "data-testid": "low-results" }) }));
// The notice's buttons call the searches' server actions.
vi.mock("@/app/app/searches/actions", () => ({
  dismissZoneNotice: vi.fn(), trackZoneNoticeShown: vi.fn(), widenSearchZone: vi.fn(), zoneNoticeFor: vi.fn(),
}));
vi.mock("@/lib/zone-notice-server", async (importActual) => ({
  ...(await importActual<typeof import("@/lib/zone-notice-server")>()),
  dismissedZones: async () => state.dismissed,
  zoneNotice: state.zoneNotice,
}));
vi.mock("@/lib/supabase/server", () => ({
  createClient: async () => ({
    from: (table: string) => {
      const builder = {
        select: () => builder,
        eq: () => builder,
        order: () => builder,
        maybeSingle: async () => ({ data: table === "search_diagnoses" ? state.diagnosis : PROFILE }),
        then: (resolve: (value: unknown) => unknown) => Promise.resolve({ data: [] }).then(resolve),
      };
      return builder;
    },
    rpc: async (name: string) => name === "my_plan_limits" && state.limitsError
      ? { data: null, error: { message: "timeout" } }
      : { data: name === "search_result_counts" ? [{ all_count: 1 }] : name === "search_results" ? [] : null },
  }),
}));

import SearchResultsPage from "@/app/app/searches/[id]/page";

const PROFILE = {
  id: 1, user_id: "user", name: "Mi Corolla", enabled: true, notification_frequency: "immediate",
  filters: { make: "Toyota", model: "Corolla", location_label: "Mi zona aproximada" }, preferences: {},
  origin_lat: -34.6, origin_lon: -58.4, radius_km: 30,
  created_at: "2026-10-30T11:58:00Z", bootstrapped_at: "2026-10-30T12:00:00Z", rematch_requested_at: null,
};
const NOTICE: ZoneNoticeData = {
  profileId: 1, count: 1, place: "tu zona aproximada", kind: "ip", zone: [-34.6, -58.4, 30],
  options: [{ to: 100, count: 6, capped: false }, { to: "pais", count: 50, capped: true }], cold: false,
};

beforeEach(() => {
  state.zoneNotice.mockReset();
  state.zoneNotice.mockImplementation(async () => state.answer);
  state.answer = { state: "none" };
  state.dismissed = [];
  state.limitsError = false;
  state.firstRead = false;
  state.zoneSwitch = { enabled: true };
  state.diagnosis = { explanation: "Hay pocas publicaciones cerca.", suggestions: [], max_results: 3, created_at: "2026-10-30T13:00:00Z", dismissed_at: null };
});

async function render() {
  return renderToStaticMarkup(await SearchResultsPage({ params: Promise.resolve({ id: "1" }), searchParams: Promise.resolve({}) }));
}

describe("the zone notice on the results page", () => {
  it("shows the count, the zone and the options instead of the bot's card", async () => {
    state.answer = { state: "show", notice: NOTICE };
    const html = await render();
    expect(html).toContain('data-testid="zone-notice"');
    expect(html).not.toContain('data-testid="low-results"');
    expect(html).toContain("En tu zona hay solo 1 publicación ahora.");
    expect(html).toContain("Buscamos a 30 km de tu zona aproximada.");
    expect(html).toContain("La zona sale de tu conexión y puede no ser exacta.");
    expect(html).toContain("Hasta 100 km · 6");
    expect(html).toContain("Todo el país · 50+");
    expect(html).toContain("Dejar así");
  });
  it("leaves the bot's card when the notice doesn't show", async () => {
    const html = await render();
    expect(html).toContain('data-testid="low-results"');
    expect(html).not.toContain('data-testid="zone-notice"');
  });
  it("counts with the profile, the «Todos» count, the sources and the zones hidden before", async () => {
    state.dismissed = [[-34.6, -58.4, 20]];
    await render();
    expect(state.zoneNotice).toHaveBeenCalledOnce();
    expect(state.zoneNotice.mock.calls[0][1]).toEqual({
      profile: PROFILE,
      count: 1,
      access: null,
      sources: [{ id: "mercadolibre", name: "MercadoLibre", enabled: true, collectionState: "done", firstRead: false }],
      dismissed: [[-34.6, -58.4, 20]],
    });
  });
  it("hides the bot's card too for a zone kept with «Dejar así»", async () => {
    // On the card, «Dejar así» comes before the bot writes its diagnosis.
    state.dismissed = [[-34.6, -58.4, 30]];
    const html = await render();
    expect(html).not.toContain('data-testid="low-results"');
    expect(html).not.toContain('data-testid="zone-notice"');
  });
  it("asks again by itself while a first read holds the notice, after the preparation's refresher goes", async () => {
    // The read is done, its batch still being matched: the notice waits.
    state.firstRead = true;
    state.answer = { state: "pending" };
    expect(await render()).toContain('data-refresh="15000"');
    state.answer = { state: "none" };
    expect(await render()).not.toContain("data-refresh");
    state.firstRead = false;
    state.answer = { state: "pending" };
    expect(await render()).not.toContain("data-refresh");
  });
  it("neither counts nor shows it with its switch off: the bot's card comes back, except for a zone kept", async () => {
    state.zoneSwitch = { enabled: false };
    state.answer = { state: "show", notice: NOTICE };
    const html = await render();
    expect(html).not.toContain('data-testid="zone-notice"');
    expect(html).toContain('data-testid="low-results"');
    expect(state.zoneNotice).not.toHaveBeenCalled();
    state.dismissed = [[-34.6, -58.4, 30]];
    expect(await render()).not.toContain('data-testid="low-results"');
  });
  it("waits when the switch can't be read: no notice, the bot's card stays, and it keeps asking during a first read", async () => {
    state.zoneSwitch = null;
    state.answer = { state: "show", notice: NOTICE };
    state.firstRead = true;
    const html = await render();
    expect(html).not.toContain('data-testid="zone-notice"');
    expect(html).toContain('data-testid="low-results"');
    expect(html).toContain('data-refresh="15000"');
    expect(state.zoneNotice).not.toHaveBeenCalled();
  });
  it("counts nothing without the plan's limits: the trial's quota and cap are unknown", async () => {
    state.limitsError = true;
    state.answer = { state: "show", notice: NOTICE };
    expect(await render()).not.toContain('data-testid="zone-notice"');
    expect(state.zoneNotice).not.toHaveBeenCalled();
  });
});
