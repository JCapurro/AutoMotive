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
// Radix portals don't render on the server: the dialog's content inline, only while open.
vi.mock("@/components/ui/dialog", async () => {
  const { createElement: h, Fragment } = await import("react");
  const pass = ({ children }: { children?: React.ReactNode }) => h(Fragment, null, children);
  return {
    Dialog: ({ open, children }: { open: boolean; children?: React.ReactNode }) => (open ? h(Fragment, null, children) : null),
    DialogContent: pass,
    DialogTitle: pass,
    DialogDescription: pass,
  };
});

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
  // No second "suele tardar" message, and no shortcut to the form until it's slow.
  expect(html).not.toContain("suele tardar");
  expect(html).not.toContain("Completar el formulario a mano");
});
