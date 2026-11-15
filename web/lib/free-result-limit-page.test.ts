import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, expect, it, vi } from "vitest";
import type { PlanLimits } from "./pro";

const state = vi.hoisted(() => ({ used: 50, count: 50, plan: "free" as PlanLimits["plan"], hidden: 0, diagnosis: null as object | null, ready: true }));
// PAR-01: the cards' total cost line has its own tests (lib/cost-estimate.test.ts).
vi.mock("@/lib/cost-estimate-data", () => ({ costLinesFor: async () => new Map() }));
vi.mock("@/lib/margin-data", () => ({ marginAccess: async () => null, marginLinesFor: async () => new Map(), marginTeasersFor: async () => new Set() }));
vi.mock("@/lib/auth", () => ({ requireUser: async () => ({ id: "account" }) }));
vi.mock("@/lib/config", () => ({ webConfig: async () => ({ proOffer: {}, automaticPayments: true, commercialPilot: true, planLimits: { pro: { dealerMargin: true } }, zoneNotice: { enabled: true } }) }));
vi.mock("@/lib/search-collection-server", () => ({ loadSearchCollection: async () => [] }));
// Aviso de zona: its own page test (lib/zone-notice-page.test.ts).
vi.mock("@/lib/zone-notice-server", () => ({ allCount: () => null, dismissedZones: async () => [], zoneNotice: async () => ({ state: "none" }) }));
vi.mock("@/components/app/phone-form", () => ({ PhonePrompt: () => createElement("aside", { "data-phone-prompt": true }) }));
vi.mock("@/components/app/zone-notice", () => ({ ZoneNoticePanel: () => null }));
vi.mock("@/components/app/auto-refresh", () => ({ AutoRefresh: () => null }));
// The low-results bot imports the searches' server actions, which are server-only.
vi.mock("@/components/app/low-results-notice", () => ({ LowResultsNotice: () => createElement("aside", { "data-low-results": true }) }));
vi.mock("@/components/app/search-actions", () => ({ FrequencySelect: () => null, PauseButton: () => null }));
vi.mock("@/components/app/sort-select", () => ({
  SortSelect: ({ locked = [] }: { locked?: string[] }) => createElement("span", { "data-locked-sorts": locked.join(",") }),
}));
vi.mock("@/components/app/search-criteria-summary", () => ({ SearchCriteriaSummary: () => null }));
vi.mock("@/components/app/pro-cta", () => ({ ProBanner: () => null, VisibleResultsReport: () => null }));
vi.mock("@/components/app/free-result-limit", () => ({
  FreeResultLimit: ({ limit }: { limit: number }) => createElement("aside", { "data-quota-popup": limit }),
}));
// Oferta cuando la prueba oculta autos: the components have their own test (lib/trial-hidden-offer.test.ts).
vi.mock("@/components/app/trial-hidden-offer", () => ({
  TrialHiddenOffer: ({ offer, autoOpen }: { offer: { shown: number; hidden: number }; autoOpen: boolean }) =>
    createElement("aside", { "data-trial-offer": `${offer.shown}/${offer.hidden}`, "data-auto-open": String(autoOpen) }),
  TrialHiddenCard: ({ offer }: { offer: { shown: number; hidden: number } }) =>
    createElement("section", { "data-testid": "trial-hidden", "data-trial-card": `${offer.shown}/${offer.hidden}` }),
}));
vi.mock("@/components/app/listing-card", () => ({
  LISTING_ROWS: "rows", ListingCard: () => createElement("article", { "data-result": true }),
}));
vi.mock("@/lib/supabase/server", () => ({ createClient: async () => ({
  from: (table: string) => ({ select: () => table === "sources" ? { order: async () => ({ data: [] }) } : {
    eq: () => ({ maybeSingle: async () => ({ data: table === "search_diagnoses" ? state.diagnosis : {
      id: 1, name: "Fiesta", filters: {}, preferences: {}, enabled: true, bootstrapped_at: state.ready ? "2026-10-01" : null,
    } }) }),
  } }),
  rpc: async (name: string) => ({ data: name === "my_plan_limits" ? {
    plan: state.plan, enforced: true, state: state.plan === "free" ? "trial" : "paid",
    free_results_used: state.used, free_results_limit: state.plan === "free" ? 50 : null,
    limits: state.plan === "free" ? { max_visible_results: 50 } : {},
  } : name === "search_result_counts" ? [{ all_count: state.count }] :
    name === "my_search_hidden_results" ? state.hidden :
    Array.from({ length: state.count }, (_, n) => ({ listing_id: n + 1 })) }),
}) }));

import SearchResultsPage from "@/app/app/searches/[id]/page";

beforeEach(() => Object.assign(state, { used: 50, count: 50, plan: "free", hidden: 0, diagnosis: null, ready: true }));
async function render(query: Record<string, string> = {}) {
  return renderToStaticMarkup(await SearchResultsPage({ params: Promise.resolve({ id: "1" }), searchParams: Promise.resolve(query) }));
}
it("renders the offer at exactly 50 and never offers a page beyond the cap", async () => {
  const html = await render();
  expect(html).toContain('data-quota-popup="50"');
  expect(html.match(/data-result="true"/g)).toHaveLength(50);
  expect(html).not.toContain("Ver más");
});
it("uses account consumption even when a recreated search has no results", async () => {
  state.count = 0;
  expect(await render()).toContain('data-quota-popup="50"');
});
it("offers the pass where the trial hides matches, instead of «no results» (docs/OFERTA_PRUEBA.md)", async () => {
  state.count = 0;
  state.hidden = 12;
  const empty = await render();
  expect(empty).toContain('data-trial-card="0/12"');
  expect(empty).not.toContain("Todavía no hay publicaciones");
  state.count = 3;
  state.hidden = 7;
  const some = await render();
  expect(some.match(/data-result="true"/g)).toHaveLength(3);
  expect(some.match(/data-trial-card="3\/7"/g)).toHaveLength(1);
  // The card comes after the list, where the grey line used to be.
  expect(some.lastIndexOf('data-result="true"')).toBeLessThan(some.indexOf("data-trial-card"));
});
it("says it from the first screen, short of the 50: the strip and the sheet that opens once", async () => {
  Object.assign(state, { used: 30, count: 30, hidden: 48 });
  const html = await render();
  expect(html).toContain('data-trial-offer="30/48"');
  expect(html).toContain('data-auto-open="true"');
  expect(html).toContain('data-trial-card="30/48"');
  expect(html).not.toContain("data-quota-popup");
  // Above the list: the strip is the first thing after the header.
  expect(html.indexOf("data-trial-offer")).toBeLessThan(html.indexOf('data-result="true"'));
});
it("leaves the 50th result to its own pop-up: no strip, no second sheet, the card stays", async () => {
  state.hidden = 20;
  const html = await render();
  expect(html).toContain('data-quota-popup="50"');
  expect(html).not.toContain("data-trial-offer");
  expect(html).toContain('data-trial-card="50/20"');
});
it("never opens the sheet over another filter, and keeps the card to «Todos»", async () => {
  Object.assign(state, { used: 30, count: 30, hidden: 48 });
  const html = await render({ f: "saved" });
  expect(html).toContain('data-auto-open="false"');
  expect(html).not.toContain("data-trial-card");
});
it("waits for the search to be ready: the counts move while it prepares", async () => {
  Object.assign(state, { used: 12, count: 12, hidden: 30, ready: false });
  const html = await render();
  expect(html).not.toContain("data-trial-offer");
});
it("offers nothing when the trial hides nothing, or on a paid plan", async () => {
  Object.assign(state, { used: 30, count: 30, hidden: 0 });
  expect(await render()).not.toMatch(/data-trial-(offer|card)/);
  Object.assign(state, { plan: "pass", hidden: 0 });
  expect(await render()).not.toMatch(/data-trial-(offer|card)/);
});
it("drops the low-results bot's card while the trial hides matches: it's not the zone or the filters", async () => {
  Object.assign(state, { used: 10, count: 2, diagnosis: {
    explanation: "Pocas", suggestions: [], max_results: 3, created_at: "2026-10-02", dismissed_at: null } });
  expect(await render()).toContain('data-low-results="true"');
  state.hidden = 4;
  expect(await render()).not.toContain('data-low-results="true"');
});
it("never promises alerts the used-up trial won't send, and keeps today's text otherwise", async () => {
  state.count = 0;
  expect(await render()).toContain("Tu prueba ya usó sus 50 resultados: con Particular te avisamos de las nuevas.");
  state.used = 10;
  const open = await render();
  expect(open).toContain("Todavía no hay publicaciones que coincidan. Te avisamos cuando aparezca una.");
  expect(open).not.toContain('data-testid="trial-hidden"');
});
it("waits until 50 distinct publications have been received", async () => {
  state.used = state.count = 49;
  expect(await render()).not.toContain("data-quota-popup");
});
it("keeps paid plans unrestricted", async () => {
  state.plan = "pass";
  expect(await render()).not.toContain("data-quota-popup");
});
it("shows «Mayor margen estimado» locked without Pro (Juan, 02/11), never to Pro", async () => {
  expect(await render()).toContain('data-locked-sorts="margin"');
  state.plan = "pass";
  expect(await render()).toContain('data-locked-sorts="margin"');
  state.plan = "pro";
  expect(await render()).toContain('data-locked-sorts=""');
});
