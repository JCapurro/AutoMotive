import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({ phase: "waiting" }));

vi.mock("react", async (importOriginal) => {
  const react = await importOriginal<typeof import("react")>();
  return {
    ...react,
    useState: (initial: unknown) => react.useState(
      state.phase === "waiting" && initial && typeof initial === "object" && "kind" in initial && initial.kind === "idle"
        ? { kind: "waiting", jobId: 42 }
        : initial,
    ),
    useTransition: () => [state.phase === "sending", vi.fn()],
  };
});
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), replace: vi.fn() }) }));
vi.mock("@/app/app/searches/actions", () => ({ startAssisted: vi.fn() }));
vi.mock("@/components/app/search-form", () => ({ SearchForm: () => null }));
vi.mock("@/lib/supabase/client", () => ({ createClient: () => ({}) }));

import { AssistedSearch } from "@/components/app/assisted-search";
import type { SearchValues } from "@/lib/search-form";

it.each(["sending", "waiting"])("shows only one progress indicator while %s a prompt", (phase) => {
  state.phase = phase;
  const html = renderToStaticMarkup(createElement(AssistedSearch, {
    catalog: [],
    sources: [],
    base: {} as SearchValues,
  }));
  expect(html).toContain("Interpretando tu búsqueda");
  expect(html.match(/animate-spin/g)).toHaveLength(1);
  expect(html.match(/role="status"/g)).toHaveLength(1);
});
