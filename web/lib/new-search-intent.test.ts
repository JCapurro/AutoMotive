import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, expect, it, vi } from "vitest";
import type { SearchLimit } from "./assisted";
import type { DetectedLocation } from "./search-location";

const state = vi.hoisted(() => ({ headers: {} as Record<string, string>, access: null as unknown }));
beforeEach(() => { state.headers = {}; state.access = null; });
vi.mock("next/headers", () => ({ headers: async () => new Headers(state.headers) }));

vi.mock("@/lib/auth", () => ({ requireUser: vi.fn().mockResolvedValue({ id: "user" }) }));
vi.mock("@/lib/supabase/server", () => ({ createClient: async () => ({ rpc: async () => ({ data: state.access }) }) }));
vi.mock("@/lib/config", async () => {
  const { DEFAULT_PLAN_LIMITS, DEFAULT_PRO_OFFER } = await import("@/lib/pro");
  return { webConfig: async () => ({ planLimits: DEFAULT_PLAN_LIMITS, proOffer: DEFAULT_PRO_OFFER }) };
});
vi.mock("@/app/app/searches/form-data", () => ({
  loadFormData: async () => ({ catalog: [], sources: [], defaultFrequency: "daily" }),
}));
vi.mock("@/components/app/search-form", () => ({
  SearchForm: ({ approximateLocation }: { approximateLocation: DetectedLocation | null }) =>
    createElement("span", { "data-form-zone": approximateLocation?.label }),
}));
vi.mock("@/components/app/assisted-search", () => ({
  AssistedSearch: ({ initialText, approximateLocation, limit }: {
    initialText: string; approximateLocation: DetectedLocation | null; limit: SearchLimit | null;
  }) => createElement("textarea", {
    defaultValue: initialText, "data-assisted-zone": approximateLocation?.label,
    "data-capacity": limit?.capacity, "data-upsell": limit?.upsell ?? undefined,
  }),
}));

import NewSearchPage from "@/app/app/searches/new/page";

it("hands the landing prompt to the assisted flow after authentication", async () => {
  const html = renderToStaticMarkup(await NewSearchPage({
    params: Promise.resolve({}), searchParams: Promise.resolve({ prompt: "Fiesta manual en Córdoba" }),
  }));
  expect(html).toContain("Fiesta manual en Córdoba");
});

it("keeps the empty assisted form for a visit without a prompt", async () => {
  const html = renderToStaticMarkup(await NewSearchPage({ params: Promise.resolve({}), searchParams: Promise.resolve({}) }));
  expect(html).toContain("<textarea></textarea>");
});

it("passes the automatic connection zone to the assisted and structured flows", async () => {
  state.headers = {
    "x-vercel-ip-country": "AR", "x-vercel-ip-city": "C%C3%B3rdoba",
    "x-vercel-ip-latitude": "-31.4201", "x-vercel-ip-longitude": "-64.1888",
  };
  const tree = await NewSearchPage({ params: Promise.resolve({}), searchParams: Promise.resolve({}) });
  const html = renderToStaticMarkup(tree);
  expect(html).toContain('data-assisted-zone="Córdoba (zona aproximada)"');
  // The inactive structured tab is unmounted by Radix; inspect its props too.
  const children = tree.props.children;
  const tabs = children[1];
  const structuredTab = tabs.props.children[1];
  expect(structuredTab.props.children.props.approximateLocation).toEqual({
    label: "Córdoba (zona aproximada)", lat: -31.42, lon: -64.19, approximate: true,
  });
});

it("hands the plan's room and the Particular offer to a trial", async () => {
  state.access = { plan: "free", enforced: true, state: "available", active_searches: 0, limits: { max_profiles: 1 } };
  const html = renderToStaticMarkup(await NewSearchPage({ params: Promise.resolve({}), searchParams: Promise.resolve({}) }));
  expect(html).toContain('data-capacity="1"');
  expect(html).toContain("data-upsell=\"Con Particular seguís hasta 3 modelos a la vez por $\u00a015.000.\"");
});

it("doesn't limit the request while the pilot doesn't enforce limits", async () => {
  state.access = { plan: "free", enforced: false, state: "pilot", active_searches: 4, limits: { max_profiles: 1 } };
  const html = renderToStaticMarkup(await NewSearchPage({ params: Promise.resolve({}), searchParams: Promise.resolve({}) }));
  expect(html).not.toContain("data-capacity");
});
