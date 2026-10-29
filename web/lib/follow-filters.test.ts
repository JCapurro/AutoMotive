import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({
  rpcs: [] as [string, Record<string, unknown> | undefined][],
  follow: { data: [{ contacted_count: 2, visit_scheduled_count: 0, purchased_count: 1 }], error: null } as { data: unknown; error: unknown },
  results: [] as { listing_id: number }[],
}));
vi.mock("server-only", () => ({}));
vi.mock("@/lib/auth", () => ({ requireUser: async () => ({ id: "account" }) }));
vi.mock("@/lib/config", () => ({ webConfig: async () => ({ proOffer: {}, automaticPayments: false, commercialPilot: false }) }));
vi.mock("@/lib/search-collection-server", () => ({ loadSearchCollection: async () => [] }));
vi.mock("@/components/app/auto-refresh", () => ({ AutoRefresh: () => null }));
vi.mock("@/components/app/search-actions", () => ({ FrequencySelect: () => null, PauseButton: () => null }));
vi.mock("@/components/app/sort-select", () => ({ SortSelect: () => null }));
vi.mock("@/components/app/search-criteria-summary", () => ({ SearchCriteriaSummary: () => null }));
vi.mock("@/components/app/pro-cta", () => ({ ProBanner: () => null, VisibleResultsReport: () => null }));
vi.mock("@/components/app/listing-card", () => ({
  LISTING_ROWS: "rows", ListingCard: () => createElement("article", { "data-result": true }),
}));
vi.mock("@/lib/supabase/server", () => ({ createClient: async () => ({
  from: (table: string) => ({ select: () => table === "sources" ? { order: async () => ({ data: [] }) } : {
    eq: () => ({ maybeSingle: async () => ({ data: {
      id: 1, name: "Fiesta", filters: {}, preferences: {}, enabled: true, bootstrapped_at: "2026-10-01",
    } }) }),
  } }),
  rpc: async (name: string, args?: Record<string, unknown>) => {
    state.rpcs.push([name, args]);
    if (name === "search_follow_counts") return state.follow;
    if (name === "search_result_counts") {
      return { data: [{ new_count: 1, opportunities_count: 0, all_count: 4, saved_count: 1, discarded_count: 0 }], error: null };
    }
    if (name === "my_plan_limits") return { data: { plan: "pass", enforced: false, limits: {} }, error: null };
    return { data: state.results, error: null };
  },
}) }));

import SearchResultsPage from "@/app/app/searches/[id]/page";

beforeEach(() => {
  state.rpcs = [];
  state.follow = { data: [{ contacted_count: 2, visit_scheduled_count: 0, purchased_count: 1 }], error: null };
  state.results = [];
});
async function render(f?: string) {
  return renderToStaticMarkup(await SearchResultsPage({ params: Promise.resolve({ id: "1" }), searchParams: Promise.resolve(f ? { f } : {}) }));
}
const filterSent = () => state.rpcs.find(([name]) => name === "search_results")?.[1]?.p_filter;
const pill = (html: string, label: string) =>
  html.match(new RegExp(`<a[^>]*>${label}<span[^>]*>([^<]*)</span></a>`))?.[1];

it.each(["contacted", "visit_scheduled", "purchased"])("passes ?f=%s to search_results (X-01)", async (f) => {
  await render(f);
  expect(filterSent()).toBe(f);
});

it("falls back to Todos on an unknown ?f=", async () => {
  await render("comprados");
  expect(filterSent()).toBe("all");
});

it("always draws the three follow-up pills with their counts, zero included", async () => {
  const html = await render();
  expect(state.rpcs.map(([name]) => name)).toContain("search_follow_counts");
  expect(pill(html, "Contactados")).toBe("2");
  expect(pill(html, "Visita agendada")).toBe("0");
  expect(pill(html, "Comprados")).toBe("1");
  expect(pill(html, "Todos")).toBe("4");
});

it("tolerates search_follow_counts missing or failing: zeros, never NaN", async () => {
  for (const follow of [{ data: null, error: { message: "function does not exist" } }, { data: null, error: null }, { data: [{ listing_id: 1 }], error: null }]) {
    state.follow = follow;
    const html = await render();
    expect(html).not.toContain("NaN");
    expect(pill(html, "Contactados")).toBe("0");
    expect(pill(html, "Comprados")).toBe("0");
  }
});

it.each([
  ["contacted", "No marcaste publicaciones como contactadas."],
  ["visit_scheduled", "No marcaste publicaciones con visita agendada."],
  ["purchased", "No marcaste publicaciones como compradas."],
])("says what an empty %s filter means", async (f, text) => {
  expect(await render(f)).toContain(text);
});
