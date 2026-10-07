import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, expect, it, vi } from "vitest";
import type { DetectedLocation } from "./search-location";

const state = vi.hoisted(() => ({ headers: {} as Record<string, string> }));
beforeEach(() => { state.headers = {}; });
vi.mock("next/headers", () => ({ headers: async () => new Headers(state.headers) }));

vi.mock("@/lib/auth", () => ({ requireUser: vi.fn().mockResolvedValue({ id: "user" }) }));
vi.mock("@/lib/supabase/server", () => ({ createClient: async () => ({}) }));
vi.mock("@/app/app/searches/form-data", () => ({
  loadFormData: async () => ({ catalog: [], sources: [], defaultFrequency: "daily" }),
}));
vi.mock("@/components/app/search-form", () => ({
  SearchForm: ({ approximateLocation }: { approximateLocation: DetectedLocation | null }) =>
    createElement("span", { "data-form-zone": approximateLocation?.label }),
}));
vi.mock("@/components/app/assisted-search", () => ({
  AssistedSearch: ({ initialText, approximateLocation }: { initialText: string; approximateLocation: DetectedLocation | null }) =>
    createElement("textarea", { defaultValue: initialText, "data-assisted-zone": approximateLocation?.label }),
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
