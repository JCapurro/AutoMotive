import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({ profile: {} as Record<string, unknown>, results: [] as Record<string, unknown>[],
  collectionState: "done" as "done" | "loading" | "waiting" | "failed" | "unknown" }));
vi.mock("@/lib/search-collection-server", () => ({ loadSearchCollection: async (profile: { enabled: boolean }, _userId: string,
  sources: { id: string; name: string; enabled: boolean }[]) => sources.map((source) => ({
    ...source, collectionState: profile.enabled ? state.collectionState : "paused",
  })) }));
vi.mock("@/components/app/auto-refresh", () => ({ AutoRefresh: ({ every = 3000 }: { every?: number }) => createElement("span", { "data-refresh-every": every }) }));
vi.mock("@/lib/auth", () => ({ requireUser: vi.fn().mockResolvedValue({ id: "user" }) }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }), notFound: () => { throw Error("not-found"); } }));
vi.mock("@/components/app/search-actions", () => ({ FrequencySelect: () => null, PauseButton: () => null }));
vi.mock("@/components/app/sort-select", () => ({ SortSelect: () => null }));
vi.mock("@/components/app/pro-cta", () => ({ ProBanner: () => null, VisibleResultsReport: () => null }));
vi.mock("@/components/app/listing-card", () => ({
  LISTING_ROWS: "listings",
  ListingCard: ({ card }: { card: { listing_id: number } }) => createElement("article", null, `Publicación ${card.listing_id}`),
}));
vi.mock("@/lib/supabase/server", () => ({
  createClient: async () => ({
    from: (table: string) => {
      const builder = {
        select: () => builder,
        eq: () => builder,
        order: () => builder,
        maybeSingle: async () => ({ data: state.profile }),
        then: (resolve: (value: unknown) => unknown) => Promise.resolve({ data: table === "sources"
          ? [{ id: "mercadolibre", name: "MercadoLibre", enabled: true }]
          : [state.profile] }).then(resolve),
      };
      return builder;
    },
    rpc: async (name: string) => ({ data: name === "search_results" ? state.results
      : name === "search_result_counts" ? [{ all_count: state.results.length }]
      : name === "dashboard_summary" ? [{ profile_id: 1, name: "Mi Fiesta", filters: {}, enabled: state.profile.enabled,
          pending: !state.profile.bootstrapped_at || Boolean(state.profile.rematch_requested_at), new_this_week: 0, opportunities_this_week: 0 }]
      : null }),
  }),
}));

import SearchResultsPage from "@/app/app/searches/[id]/page";
import Dashboard from "@/app/app/page";
import { SearchPreparation } from "@/components/app/search-preparation";

const now = Date.parse("2026-10-06T15:00:00Z");
beforeEach(() => {
  state.profile = { id: 1, user_id: "user", name: "Mi Fiesta", filters: {}, enabled: true, radius_km: 30,
    created_at: new Date(now - 30_000).toISOString(), bootstrapped_at: null, rematch_requested_at: null };
  state.results = [];
  state.collectionState = "done";
});

async function resultsHtml() {
  return renderToStaticMarkup(await SearchResultsPage({ params: Promise.resolve({ id: "1" }), searchParams: Promise.resolve({}) }));
}

describe("first search preparation", () => {
  it("keeps polling and avoids an empty result while a platform is still collecting after backfill", async () => {
    state.profile.bootstrapped_at = new Date(now).toISOString();
    state.collectionState = "loading";
    const html = await resultsHtml();
    expect(html).toContain('data-collection-state="loading"');
    expect(html).toContain('data-testid="search-preparation"');
    expect(html).toContain('data-refresh-every="3000"');
    expect(html).not.toContain("Todavía no hay publicaciones");
    state.collectionState = "done";
    const completed = await resultsHtml();
    expect(completed).toContain('data-collection-state="done"');
    expect(completed).not.toContain("data-refresh-every");
    expect(completed).not.toContain('data-testid="search-preparation"');
  });
  it("refreshes failed collection at a slower cadence without a false tick", async () => {
    state.profile.bootstrapped_at = new Date(now).toISOString();
    state.collectionState = "failed";
    const html = await resultsHtml();
    expect(html).toContain('data-refresh-every="10000"');
    expect(html).toContain('data-collection-state="failed"');
    expect(html).not.toContain('data-collection-state="done"');
    expect(html).not.toContain('data-testid="search-preparation"');
  });
  it("shows the saved criteria and source catalog below the search title", async () => {
    state.profile.filters = { year_min: 2016, year_max: 2018, transmission: "manual" };
    const html = await resultsHtml();
    expect(html).toContain('data-testid="search-criteria"');
    expect(html).toContain("2016–2018");
    expect(html).toContain("Manual");
    expect(html).toContain("MercadoLibre");
    expect(html.indexOf("Mi Fiesta")).toBeLessThan(html.indexOf('data-testid="search-criteria"'));
    expect(html.indexOf('data-testid="search-criteria"')).toBeLessThan(html.indexOf('data-testid="search-preparation"'));
  });
  it("explains the wait briefly and hides zero-result controls before the first pass completes", async () => {
    const html = await resultsHtml();
    expect(html).toContain("Cargando…");
    expect(html).toContain('disabled=""');
    expect(html).toContain("Estamos preparando tus resultados");
    expect(html).toContain("al menos 2 minutos");
    expect(html).toContain("Los resultados se actualizan solos");
    expect(html).not.toContain("Tiempo transcurrido");
    expect(html).not.toContain("No hay publicaciones");
    expect(html).not.toContain('data-testid="result-filters"');
    expect(html).not.toContain("Buscando…");
  });
  it("shows a true empty result only after processing finishes", async () => {
    state.profile.bootstrapped_at = new Date(now).toISOString();
    const html = await resultsHtml();
    expect(html).not.toContain('data-testid="search-preparation"');
    expect(html).toContain("Todavía no hay publicaciones que coincidan");
    expect(html).toContain('data-testid="result-filters"');
  });
  it("keeps the same compact loading state when returning after a long wait", async () => {
    state.profile.created_at = new Date(now - 6 * 60_000).toISOString();
    const html = await resultsHtml();
    expect(html).toContain("Cargando…");
    expect(html).not.toContain("más tiempo del esperado");
    expect(html).not.toContain("6:00");
    expect(html).not.toContain("No hay publicaciones");
  });
  it("keeps previous results visible while recalculating edited filters", async () => {
    state.profile.bootstrapped_at = new Date(now - 86_400_000).toISOString();
    state.profile.created_at = new Date(now - 86_400_000).toISOString();
    state.profile.rematch_requested_at = new Date(now - 20_000).toISOString();
    state.results = [{ listing_id: 1 }];
    const html = await resultsHtml();
    expect(html).toContain("Cargando…");
    expect(html).toContain("Publicación 1");
    expect(html).not.toContain("0:20");
    expect(html).not.toContain("más tiempo del esperado");
  });
  it("does not promise active processing or keep polling a paused search", async () => {
    state.profile.enabled = false;
    const html = await resultsHtml();
    expect(html).toContain("Reanudá la búsqueda");
    expect(html).not.toContain('data-testid="search-preparation"');
    expect(html).not.toContain("Cargando…");
    expect(html).not.toContain("data-refresh-every");
  });
  it("shows pending status and an automatic refresh on the dashboard, including the assisted flow", async () => {
    const html = renderToStaticMarkup(await Dashboard());
    expect(html).toContain("Cargando…");
    expect(html).toContain('disabled=""');
    expect(html).not.toContain("minutos");
    expect(html).not.toContain('data-testid="dashboard-preparation"');
    expect(html).not.toContain("Todavía no hay oportunidades");
  });
  it("renders completed results as soon as the real completion flag arrives", async () => {
    state.profile.bootstrapped_at = new Date(now).toISOString();
    state.results = [{ listing_id: 1 }];
    const html = await resultsHtml();
    expect(html).toContain("Publicación 1");
    expect(html).not.toContain('data-testid="search-preparation"');
  });
});

it("renders an accessible loading state with brief guidance and no timer", () => {
  const html = renderToStaticMarkup(createElement(SearchPreparation));
  expect(html).toContain('role="status"');
  expect(html).toContain('disabled=""');
  expect(html).toContain("motion-reduce:animate-none");
  expect(html).toContain("al menos 2 minutos");
  expect(html).not.toContain("Tiempo transcurrido");
  expect(html).not.toContain("Acá van a aparecer");
});
