import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, expect, it, vi } from "vitest";
import type { SearchLimit } from "./assisted";
import type { DetectedLocation } from "./search-location";

const state = vi.hoisted(() => ({
  headers: {} as Record<string, string>, access: null as unknown, modelLessSearch: false, emailOnly: false,
  searches: 0, recorded: 0, tracked: [] as string[],
}));
beforeEach(() => {
  state.headers = {}; state.access = null; state.modelLessSearch = false; state.emailOnly = false;
  state.searches = 0; state.recorded = 0; state.tracked = [];
});
vi.mock("next/headers", () => ({ headers: async () => new Headers(state.headers) }));

vi.mock("@/lib/auth", () => ({ requireUser: vi.fn().mockResolvedValue({ id: "user", email: "user@example.com" }), isEmailOnly: async () => state.emailOnly }));
vi.mock("@/lib/supabase/server", () => ({
  createClient: async () => ({
    rpc: async () => ({ data: state.access }),
    from: (table: string) => {
      const result = { count: table === "events" ? state.recorded : state.searches };
      const query = { eq: async () => result, then: (resolve: (r: typeof result) => void) => resolve(result) };
      return { select: () => query };
    },
  }),
}));
vi.mock("@/lib/events", () => ({ track: async (_s: unknown, _u: string, name: string) => { state.tracked.push(name); } }));
vi.mock("@/lib/config", async () => {
  const { DEFAULT_PLAN_LIMITS, DEFAULT_PRO_OFFER } = await import("@/lib/pro");
  return { webConfig: async () => ({ planLimits: DEFAULT_PLAN_LIMITS, proOffer: DEFAULT_PRO_OFFER }) };
});
vi.mock("@/app/app/searches/form-data", () => ({
  loadFormData: async () => ({ catalog: [], sources: [], defaultFrequency: "daily", thresholdAlerts: false, modelLessSearch: state.modelLessSearch }),
}));
vi.mock("@/components/app/search-form", () => ({
  SearchForm: ({ approximateLocation, trialFull, trialComplete }: {
    approximateLocation: DetectedLocation | null; trialFull?: number | null; trialComplete?: number | null;
  }) => createElement("span", {
    "data-form-zone": approximateLocation?.label, "data-form-full": trialFull ?? undefined, "data-form-complete": trialComplete ?? undefined,
  }),
}));
vi.mock("@/components/app/assisted-search", () => ({
  AssistedSearch: ({ initialText, approximateLocation, limit, modelLessSearch, trialFull, trialComplete }: {
    initialText: string; approximateLocation: DetectedLocation | null; limit: SearchLimit | null; modelLessSearch?: boolean;
    trialFull?: number | null; trialComplete?: number | null;
  }) => createElement("textarea", {
    "data-assisted-full": trialFull ?? undefined, "data-assisted-complete": trialComplete ?? undefined,
    defaultValue: initialText, "data-assisted-zone": approximateLocation?.label,
    "data-capacity": limit?.capacity, "data-upsell": limit?.upsell ?? undefined,
    "data-model-less": modelLessSearch ? "yes" : undefined,
  }),
}));

import NewSearchPage from "@/app/app/searches/new/page";

it("tells an email-only account where the alerts go", async () => {
  state.emailOnly = true;
  const html = renderToStaticMarkup(await NewSearchPage({ params: Promise.resolve({}), searchParams: Promise.resolve({}) }));
  expect(html).toContain("Te vamos a avisar a <b>user@example.com</b>");
  state.emailOnly = false;
  expect(renderToStaticMarkup(await NewSearchPage({ params: Promise.resolve({}), searchParams: Promise.resolve({}) }))).not.toContain("Te vamos a avisar");
});

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
  const tabs = children.find((child: { props?: { defaultValue?: string } } | null) => child?.props?.defaultValue === "assisted");
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

it("hands the search by body type to both flows when the plan has it (docs/CARROCERIA.md)", async () => {
  state.modelLessSearch = true;
  const tree = await NewSearchPage({ params: Promise.resolve({}), searchParams: Promise.resolve({}) });
  expect(renderToStaticMarkup(tree)).toContain('data-model-less="yes"');
  const tabs = tree.props.children.find((child: { props?: { defaultValue?: string } } | null) => child?.props?.defaultValue === "assisted");
  const structuredTab = tabs.props.children[1];
  expect(structuredTab.props.children.props.modelLessSearch).toBe(true);
  expect(structuredTab.props.children.props.initial.body_types).toEqual([]);
});

it("records an email-only account without searches that arrives without its prompt, once", async () => {
  state.emailOnly = true;
  await NewSearchPage({ params: Promise.resolve({}), searchParams: Promise.resolve({}) });
  expect(state.tracked).toEqual(["search_intent_missing"]);

  state.tracked = [];
  await NewSearchPage({ params: Promise.resolve({}), searchParams: Promise.resolve({ prompt: "Hilux SRV" }) });
  state.searches = 1;
  await NewSearchPage({ params: Promise.resolve({}), searchParams: Promise.resolve({}) });
  state.searches = 0;
  state.recorded = 1;
  await NewSearchPage({ params: Promise.resolve({}), searchParams: Promise.resolve({}) });
  state.emailOnly = false;
  state.recorded = 0;
  await NewSearchPage({ params: Promise.resolve({}), searchParams: Promise.resolve({}) });
  expect(state.tracked).toEqual([]);
});

// «40 + N» (docs/PRUEBA_COMPLETA.md): a trial complete by its cap is told so; a quota reached without it keeps «usó sus 50».
it.each([
  { name: "complete", used: 45, newUsed: 5, newMax: 5, full: null, complete: 5 },
  { name: "complete and full", used: 50, newUsed: 6, newMax: 5, full: null, complete: 6 },
  { name: "full, cap not used", used: 50, newUsed: 2, newMax: 5, full: 50, complete: null },
  { name: "neither", used: 30, newUsed: 2, newMax: 5, full: null, complete: null },
  { name: "legacy, full", used: 50, newUsed: 0, newMax: null, full: 50, complete: null },
])("hands both forms the trial's state: $name", async ({ used, newUsed, newMax, full, complete }) => {
  state.access = {
    enforced: true, plan: "free", limits: {}, active_searches: 0,
    free_results_used: used, free_results_limit: 50, free_new_used: newUsed, free_new_max: newMax,
  };
  const html = renderToStaticMarkup(await NewSearchPage({ params: Promise.resolve({}), searchParams: Promise.resolve({}) }));
  const attr = (name: string, value: number | null) => (value == null ? expect(html).not.toContain(`${name}=`) : expect(html).toContain(`${name}="${value}"`));
  attr("data-assisted-full", full);
  attr("data-assisted-complete", complete);
  // The structured tab is unmounted by Radix: its props, from the tree.
  const tree = await NewSearchPage({ params: Promise.resolve({}), searchParams: Promise.resolve({}) });
  const form = findProps(tree, "trialComplete");
  expect(form?.trialFull ?? null).toBe(full);
  expect(form?.trialComplete ?? null).toBe(complete);
});

function findProps(node: unknown, key: string): Record<string, unknown> | null {
  if (!node || typeof node !== "object") return null;
  if (Array.isArray(node)) { for (const n of node) { const r = findProps(n, key); if (r) return r; } return null; }
  const props = (node as { props?: Record<string, unknown> }).props;
  if (!props) return null;
  if (key in props && "initial" in props) return props;
  return findProps(props.children, key);
}
