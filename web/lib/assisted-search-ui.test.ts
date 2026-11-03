import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({ phase: "waiting", active: null as unknown, notice: null as unknown }));

vi.mock("react", async (importOriginal) => {
  const react = await importOriginal<typeof import("react")>();
  const start = () => (state.phase === "active" ? state.active : { kind: "waiting", jobId: 42 });
  return {
    ...react,
    useState: (initial: unknown) => react.useState(
      state.phase !== "sending" && initial && typeof initial === "object" && "kind" in initial && initial.kind === "idle"
        ? start()
        : initial,
    ),
    useTransition: () => [state.phase === "sending", vi.fn()],
  };
});
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), replace: vi.fn() }) }));
vi.mock("@/app/app/searches/actions", () => ({ startAssisted: vi.fn() }));
vi.mock("@/components/app/search-form", () => ({ SearchForm: () => null }));
// Aviso de zona (docs/AVISO_ZONA.md): the poll's answer, with the real options.
vi.mock("@/components/app/zone-notice", async (importActual) => ({
  ...(await importActual<typeof import("@/components/app/zone-notice")>()),
  useZoneNoticePoll: () => state.notice,
}));
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
import { SearchInput, type SearchValues } from "@/lib/search-form";
import type { ZoneNoticeData } from "@/lib/zone-notice";

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
  // No second "suele tardar" message, and no shortcut to the form: the user just waits.
  expect(html).not.toContain("suele tardar");
  expect(html).not.toContain("Completar el formulario a mano");
});

it("offers the zone notice on the card of a search just saved, until a tap answers it", () => {
  state.phase = "active";
  const values = SearchInput.parse({ make: "Toyota", model: "Corolla", location: { label: "Laferrere", lat: -34.75, lon: -58.58, radius_km: 30 } });
  state.active = { kind: "active", jobId: 42, savedId: 7, draft: { title: "Toyota Corolla", values, notes: [], state: "saved", savedId: 7 } };
  const notice: ZoneNoticeData = {
    profileId: 7, count: 1, place: "Laferrere", kind: "named", zone: [-34.75, -58.58, 30],
    options: [{ to: 100, count: 6, capped: false }, { to: "pais", count: 50, capped: false }], cold: false,
  };
  const render = () => renderToStaticMarkup(createElement(AssistedSearch, { catalog: [], sources: [], base: {} as SearchValues }));
  state.notice = notice;
  const html = render();
  expect(html).toContain("A 30 km de Laferrere hay solo 1 publicación ahora.");
  expect(html).toContain("Hasta 100 km · 6");
  expect(html).toContain("Todo el país · 50");
  expect(html).toContain("Dejar así");
  // «Ver mi búsqueda» stays, and the status line waits, empty, for what a tap changes.
  expect(html).toMatch(/<a [^>]*href="\/app\/searches\/7"/);
  expect(html).toContain('<p role="status" class="text-sm font-medium"></p>');
  state.notice = null;
  const quiet = render();
  expect(quiet).toContain("Ya estamos buscando «Toyota Corolla».");
  expect(quiet).not.toContain("Ampliá tu rango");
  state.phase = "waiting";
});
