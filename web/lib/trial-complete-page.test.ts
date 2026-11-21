import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, expect, it, vi } from "vitest";

// «40 + N» (docs/PRUEBA_COMPLETA.md) on the results page, in its three states:
// legacy (no cap: lib/free-result-limit-page.test.ts has the rest), new mode
// before the trial completes, and new mode once it did.
const state = vi.hoisted(() => ({
  used: 30, count: 30, hidden: 0, ready: true,
  newMax: null as number | null, newUsed: 0, randomStock: false,
}));
vi.mock("@/lib/cost-estimate-data", () => ({ costLinesFor: async () => new Map() }));
vi.mock("@/lib/margin-data", () => ({ marginAccess: async () => null, marginLinesFor: async () => new Map(), marginTeasersFor: async () => new Set() }));
vi.mock("@/lib/auth", () => ({ requireUser: async () => ({ id: "account" }) }));
vi.mock("@/lib/config", () => ({ webConfig: async () => ({
  proOffer: {}, automaticPayments: true, commercialPilot: true, planLimits: { pro: { dealerMargin: true } }, zoneNotice: { enabled: true },
  trialReserve: { enabled: true, backfillMax: 40, newMax: state.newMax, randomStock: state.randomStock, noticeSince: null },
}) }));
vi.mock("@/lib/search-collection-server", () => ({ loadSearchCollection: async () => [] }));
vi.mock("@/lib/zone-notice-server", () => ({ allCount: () => null, dismissedZones: async () => [], zoneNotice: async () => ({ state: "none" }) }));
vi.mock("@/components/app/phone-form", () => ({ PhonePrompt: () => null }));
vi.mock("@/components/app/zone-notice", () => ({ ZoneNoticePanel: () => null }));
vi.mock("@/components/app/auto-refresh", () => ({ AutoRefresh: () => null }));
vi.mock("@/components/app/low-results-notice", () => ({ LowResultsNotice: () => null }));
vi.mock("@/components/app/search-actions", () => ({ FrequencySelect: () => null, PauseButton: () => null }));
vi.mock("@/components/app/sort-select", () => ({ SortSelect: () => null }));
vi.mock("@/components/app/search-criteria-summary", () => ({ SearchCriteriaSummary: () => null }));
vi.mock("@/components/app/pro-cta", () => ({ ProBanner: () => null, VisibleResultsReport: () => null }));
vi.mock("@/components/app/results-viewed-report", () => ({ ResultsViewedReport: () => null }));
vi.mock("@/components/app/free-result-limit", () => ({
  FreeResultLimit: ({ limit }: { limit: number }) => createElement("aside", { "data-quota-popup": limit }),
}));
vi.mock("@/components/app/trial-hidden-offer", () => ({
  TrialHiddenOffer: ({ offer, autoOpen, complete = null }: { offer: { shown: number; hidden: number }; autoOpen: boolean; complete?: number | null }) =>
    createElement("aside", { "data-trial-offer": `${offer.shown}/${offer.hidden}`, "data-auto-open": String(autoOpen), "data-complete": String(complete) }),
  TrialHiddenCard: ({ offer, randomStock = false }: { offer: { shown: number; hidden: number }; randomStock?: boolean }) =>
    createElement("section", { "data-trial-card": `${offer.shown}/${offer.hidden}`, "data-random": String(randomStock) }),
}));
vi.mock("@/components/app/listing-card", () => ({
  LISTING_ROWS: "rows", ListingCard: () => createElement("article", { "data-result": true }),
}));
vi.mock("@/lib/supabase/server", () => ({ createClient: async () => ({
  from: (table: string) => ({ select: () => table === "sources" ? { order: async () => ({ data: [] }) } : {
    eq: () => ({ maybeSingle: async () => ({ data: table === "search_diagnoses" ? null : {
      id: 1, name: "Fiesta", filters: {}, preferences: {}, enabled: true,
      bootstrapped_at: state.ready ? "2026-10-01" : null, rematch_requested_at: null,
    } }) }),
  } }),
  rpc: async (name: string) => ({ data: name === "my_plan_limits" ? {
    plan: "free", enforced: true, state: "trial", expires_at: "2026-11-23T12:00:00Z",
    free_results_used: state.used, free_results_limit: 50, free_new_used: state.newUsed, free_new_max: state.newMax,
    limits: { max_visible_results: 50 },
  } : name === "search_result_counts" ? [{ all_count: state.count }] :
    name === "my_search_hidden_results" ? state.hidden :
    Array.from({ length: state.count }, (_, n) => ({ listing_id: n + 1 })) }),
}) }));

import SearchResultsPage from "@/app/app/searches/[id]/page";

beforeEach(() => Object.assign(state, { used: 30, count: 30, hidden: 0, ready: true, newMax: null, newUsed: 0, randomStock: false }));
async function render(query: Record<string, string> = {}) {
  return renderToStaticMarkup(await SearchResultsPage({ params: Promise.resolve({ id: "1" }), searchParams: Promise.resolve(query) }));
}

it("legacy (no cap): the sheet opens by itself and FreeResultLimit asks at 50, as today", async () => {
  Object.assign(state, { hidden: 48 });
  const open = await render();
  expect(open).toContain('data-trial-offer="30/48"');
  expect(open).toContain('data-auto-open="true"');
  expect(open).toContain('data-complete="null"');
  Object.assign(state, { used: 50, count: 50, hidden: 20 });
  const full = await render();
  expect(full).toContain('data-quota-popup="50"');
  expect(full).not.toContain("data-trial-offer");
});

it("new mode, not complete: nothing opens by itself; the strip and the card stay", async () => {
  Object.assign(state, { used: 43, count: 43, hidden: 38, newMax: 5, newUsed: 3 });
  const html = await render();
  expect(html).toContain('data-trial-offer="43/38"');
  expect(html).toContain('data-auto-open="false"');
  expect(html).toContain('data-complete="null"');
  expect(html).toContain('data-trial-card="43/38"');
  expect(html).not.toContain("data-quota-popup");
});

it("new mode, complete: the complete variant opens instead of FreeResultLimit, even with nothing hidden", async () => {
  Object.assign(state, { used: 45, count: 45, hidden: 23, newMax: 5, newUsed: 5 });
  const html = await render();
  expect(html).toContain('data-trial-offer="45/23"');
  expect(html).toContain('data-complete="5"');
  expect(html).toContain('data-auto-open="true"');
  expect(html).toContain('data-trial-card="45/23"');
  expect(html).not.toContain("data-quota-popup");
  state.hidden = 0;
  const none = await render();
  expect(none).toContain('data-trial-offer="45/0"');
  expect(none).toContain('data-complete="5"');
  expect(none).not.toContain("data-trial-card");
  // Over another filter it waits, as the sheet always did.
  expect(await render({ f: "saved" })).toContain('data-auto-open="false"');
});

it("new mode, quota filled before the cap was used: today's path, never the complete variant", async () => {
  Object.assign(state, { used: 50, count: 50, hidden: 4, newMax: 5, newUsed: 0 });
  const html = await render();
  expect(html).toContain('data-quota-popup="50"');
  expect(html).not.toContain('data-complete="');
  expect(html).not.toContain("te mostró");
  Object.assign(state, { count: 0, hidden: 0 });
  const empty = await render();
  expect(empty).toContain("Tu prueba ya usó sus 50 resultados");
  expect(empty).not.toContain("te mostró");
  Object.assign(state, { ready: false });
  const preparing = await render();
  expect(preparing).toContain("tu prueba ya usó sus 50 resultados");
  expect(preparing).not.toContain("te mostró");
});

it("new mode, complete at the whole quota too: the complete variant, never FreeResultLimit", async () => {
  Object.assign(state, { used: 50, count: 50, hidden: 4, newMax: 5, newUsed: 5 });
  const html = await render();
  expect(html).toContain('data-complete="5"');
  expect(html).not.toContain("data-quota-popup");
});

it("new mode, a trial running at the switch-on got more new ones than the cap: says how many it got", async () => {
  Object.assign(state, { used: 50, count: 0, hidden: 0, newMax: 5, newUsed: 12 });
  const html = await render();
  expect(html).toContain('data-complete="12"');
  expect(html).toContain("Tu prueba ya te mostró sus 12 autos nuevos");
  expect(html).not.toContain("sus 5 autos nuevos");
  expect(html).not.toContain("data-quota-popup");
});

it("new mode, complete: an empty list says what happened, never «50 resultados»", async () => {
  Object.assign(state, { used: 45, count: 0, hidden: 0, newMax: 5, newUsed: 5 });
  const html = await render();
  expect(html).toContain("Todavía no hay publicaciones que coincidan. Tu prueba ya te mostró sus 5 autos nuevos: con Particular te avisamos de las nuevas.");
  expect(html).not.toContain("50 resultados");
});

it("new mode, complete: the preparation notice says what happened", async () => {
  Object.assign(state, { used: 45, count: 0, hidden: 0, newMax: 5, newUsed: 5, ready: false });
  const html = await render();
  expect(html).toContain("tu prueba ya te mostró sus 5 autos nuevos, así que no vamos a avisarte de otros.");
  expect(html).not.toContain("50 resultados");
  expect(html).not.toContain("data-trial-offer");
});

it("tells the card when the stock is a random sample", async () => {
  Object.assign(state, { hidden: 38, randomStock: true });
  expect(await render()).toContain('data-random="true"');
  state.randomStock = false;
  expect(await render()).toContain('data-random="false"');
});
