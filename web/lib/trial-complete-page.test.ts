import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, expect, it, vi } from "vitest";

// Prueba de 50 publicaciones (docs/PRUEBA_COMPLETA.md) on the results page, in
// its states: legacy (lib/free-result-limit-page.test.ts has the rest), notice
// mode before the quota fills, and notice mode once it did.
const state = vi.hoisted(() => ({
  used: 30, count: 30, hidden: 0, ready: true,
  noticeSince: null as string | null, randomStock: false,
}));
vi.mock("@/lib/cost-estimate-data", () => ({ costLinesFor: async () => new Map() }));
vi.mock("@/lib/margin-data", () => ({ marginAccess: async () => null, marginLinesFor: async () => new Map(), marginTeasersFor: async () => new Set() }));
vi.mock("@/lib/auth", () => ({ requireUser: async () => ({ id: "account" }) }));
vi.mock("@/lib/config", () => ({ webConfig: async () => ({
  proOffer: {}, automaticPayments: true, commercialPilot: true, planLimits: { pro: { dealerMargin: true } }, zoneNotice: { enabled: true },
  trialReserve: { enabled: true, backfillMax: 45, randomStock: state.randomStock, noticeSince: state.noticeSince },
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
  TrialHiddenOffer: ({ offer, autoOpen, notice = false, complete = null }: { offer: { shown: number; hidden: number }; autoOpen: boolean; notice?: boolean; complete?: number | null }) =>
    createElement("aside", { "data-trial-offer": `${offer.shown}/${offer.hidden}`, "data-auto-open": String(autoOpen), "data-notice": String(notice), "data-complete": String(complete) }),
  TrialHiddenCard: ({ offer, plain = false }: { offer: { shown: number; hidden: number }; plain?: boolean }) =>
    createElement("section", { "data-trial-card": `${offer.shown}/${offer.hidden}`, "data-plain": String(plain) }),
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
    free_results_used: state.used, free_results_limit: 50, limits: { max_visible_results: 50 },
  } : name === "search_result_counts" ? [{ all_count: state.count }] :
    name === "my_search_hidden_results" ? state.hidden :
    Array.from({ length: state.count }, (_, n) => ({ listing_id: n + 1 })) }),
}) }));

import SearchResultsPage from "@/app/app/searches/[id]/page";

const SINCE = "2026-11-21T12:00:00Z";
beforeEach(() => Object.assign(state, { used: 30, count: 30, hidden: 0, ready: true, noticeSince: null, randomStock: false }));
async function render(query: Record<string, string> = {}) {
  return renderToStaticMarkup(await SearchResultsPage({ params: Promise.resolve({ id: "1" }), searchParams: Promise.resolve(query) }));
}

it("legacy: the legacy strip and card, and FreeResultLimit at 50, as on main", async () => {
  Object.assign(state, { hidden: 48 });
  const open = await render();
  expect(open).toContain('data-trial-offer="30/48"');
  expect(open).toContain('data-notice="false"');
  expect(open).toContain('data-complete="null"');
  expect(open).toContain('data-plain="false"');
  Object.assign(state, { used: 50, count: 50, hidden: 20 });
  const full = await render();
  expect(full).toContain('data-quota-popup="50"');
  expect(full).not.toContain("data-trial-offer");
});

it("legacy with a random sample: the card's plain lead, nothing else changes", async () => {
  Object.assign(state, { hidden: 48, randomStock: true });
  const html = await render();
  expect(html).toContain('data-plain="true"');
  expect(html).toContain('data-notice="false"');
});

it("notice mode, quota not full: the notice strip and the plain card; FreeResultLimit never", async () => {
  Object.assign(state, { used: 43, count: 43, hidden: 38, noticeSince: SINCE });
  const html = await render();
  expect(html).toContain('data-trial-offer="43/38"');
  expect(html).toContain('data-notice="true"');
  expect(html).toContain('data-complete="null"');
  expect(html).toContain('data-trial-card="43/38"');
  expect(html).toContain('data-plain="true"');
  expect(html).not.toContain("data-quota-popup");
});

it("notice mode, quota full: the complete variant with the limit, in place of FreeResultLimit", async () => {
  Object.assign(state, { used: 50, count: 50, hidden: 23, noticeSince: SINCE });
  const html = await render();
  expect(html).toContain('data-trial-offer="50/23"');
  expect(html).toContain('data-complete="50"');
  expect(html).toContain('data-auto-open="true"');
  expect(html).toContain('data-trial-card="50/23"');
  expect(html).not.toContain("data-quota-popup");
  state.hidden = 0;
  const none = await render();
  expect(none).toContain('data-trial-offer="50/0"');
  expect(none).toContain('data-complete="50"');
  expect(none).not.toContain("data-trial-card");
  // Over another filter it waits, as the sheet always did.
  expect(await render({ f: "saved" })).toContain('data-auto-open="false"');
});

it("notice mode, quota full: the honest notices stay as on main", async () => {
  Object.assign(state, { used: 50, count: 0, hidden: 0, noticeSince: SINCE });
  const empty = await render();
  expect(empty).toContain("Todavía no hay publicaciones que coincidan. Tu prueba ya usó sus 50 resultados: con Particular te avisamos de las nuevas.");
  Object.assign(state, { ready: false });
  const preparing = await render();
  expect(preparing).toContain("tu prueba ya usó sus 50 resultados");
  expect(preparing).not.toContain("data-trial-offer");
});

it("without notice_since: legacy, FreeResultLimit at 50", async () => {
  Object.assign(state, { used: 50, count: 50, hidden: 4, noticeSince: null });
  expect(await render()).toContain('data-quota-popup="50"');
});
