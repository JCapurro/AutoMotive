import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, expect, it, vi } from "vitest";
import type { PlanLimits } from "./pro";

const state = vi.hoisted(() => ({ used: 50, count: 50, plan: "free" as PlanLimits["plan"] }));
// PAR-01: the cards' total cost line has its own tests (lib/cost-estimate.test.ts).
vi.mock("@/lib/cost-estimate-data", () => ({ costLinesFor: async () => new Map() }));
vi.mock("@/lib/auth", () => ({ requireUser: async () => ({ id: "account" }) }));
vi.mock("@/lib/config", () => ({ webConfig: async () => ({ proOffer: {}, automaticPayments: true, commercialPilot: true }) }));
vi.mock("@/lib/search-collection-server", () => ({ loadSearchCollection: async () => [] }));
vi.mock("@/components/app/auto-refresh", () => ({ AutoRefresh: () => null }));
vi.mock("@/components/app/search-actions", () => ({ FrequencySelect: () => null, PauseButton: () => null }));
vi.mock("@/components/app/sort-select", () => ({ SortSelect: () => null }));
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
    eq: () => ({ maybeSingle: async () => ({ data: {
      id: 1, name: "Fiesta", filters: {}, preferences: {}, enabled: true, bootstrapped_at: "2026-10-01",
    } }) }),
  } }),
  rpc: async (name: string) => ({ data: name === "my_plan_limits" ? {
    plan: state.plan, enforced: true, state: state.plan === "free" ? "trial" : "paid",
    free_results_used: state.used, free_results_limit: state.plan === "free" ? 50 : null,
    limits: state.plan === "free" ? { max_visible_results: 50 } : {},
  } : name === "search_result_counts" ? [{ all_count: state.count }] :
    Array.from({ length: state.count }, (_, n) => ({ listing_id: n + 1 })) }),
}) }));

import SearchResultsPage from "@/app/app/searches/[id]/page";

beforeEach(() => Object.assign(state, { used: 50, count: 50, plan: "free" }));
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
it("waits until 50 distinct publications have been received", async () => {
  state.used = state.count = 49;
  expect(await render()).not.toContain("data-quota-popup");
});
it("keeps paid plans unrestricted", async () => {
  state.plan = "pass";
  expect(await render()).not.toContain("data-quota-popup");
});
