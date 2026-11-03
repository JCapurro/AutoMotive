import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, expect, it, vi } from "vitest";
import type { PlanLimits } from "./pro";

const state = vi.hoisted(() => ({ used: 50, count: 50, plan: "free" as PlanLimits["plan"], hidden: 0, diagnosis: null as object | null }));
// PAR-01: the cards' total cost line has its own tests (lib/cost-estimate.test.ts).
vi.mock("@/lib/cost-estimate-data", () => ({ costLinesFor: async () => new Map() }));
vi.mock("@/lib/margin-data", () => ({ marginAccess: async () => null, marginLinesFor: async () => new Map(), marginTeasersFor: async () => new Set() }));
vi.mock("@/lib/auth", () => ({ requireUser: async () => ({ id: "account" }) }));
vi.mock("@/lib/config", () => ({ webConfig: async () => ({ proOffer: {}, automaticPayments: true, commercialPilot: true, planLimits: { pro: { dealerMargin: true } }, zoneNotice: { enabled: true } }) }));
vi.mock("@/lib/search-collection-server", () => ({ loadSearchCollection: async () => [] }));
// Aviso de zona: its own page test (lib/zone-notice-page.test.ts).
vi.mock("@/lib/zone-notice-server", () => ({ allCount: () => null, dismissedZones: async () => [], zoneNotice: async () => ({ state: "none" }) }));
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
vi.mock("@/components/app/listing-card", () => ({
  LISTING_ROWS: "rows", ListingCard: () => createElement("article", { "data-result": true }),
}));
vi.mock("@/lib/supabase/server", () => ({ createClient: async () => ({
  from: (table: string) => ({ select: () => table === "sources" ? { order: async () => ({ data: [] }) } : {
    eq: () => ({ maybeSingle: async () => ({ data: table === "search_diagnoses" ? state.diagnosis : {
      id: 1, name: "Fiesta", filters: {}, preferences: {}, enabled: true, bootstrapped_at: "2026-10-01",
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

beforeEach(() => Object.assign(state, { used: 50, count: 50, plan: "free", hidden: 0, diagnosis: null }));
async function render() {
  return renderToStaticMarkup(await SearchResultsPage({ params: Promise.resolve({ id: "1" }), searchParams: Promise.resolve({}) }));
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
it("says how many matches the trial hides instead of «no results» (docs/PRUEBA_HONESTA.md)", async () => {
  state.count = 0;
  state.hidden = 12;
  const empty = await render();
  expect(empty).toContain("Hay 12 publicaciones que coinciden y tu prueba no muestra.");
  expect(empty).toContain('href="/app/pro?plan=pass_30"');
  expect(empty).not.toContain("Todavía no hay publicaciones");
  state.hidden = 1;
  expect(await render()).toContain("Hay 1 publicación que coincide y tu prueba no muestra.");
  state.count = 3;
  state.hidden = 7;
  const some = await render();
  expect(some.match(/data-result="true"/g)).toHaveLength(3);
  expect(some).toContain("Y 7 más que coinciden y tu prueba no muestra.");
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
