import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, expect, it, vi } from "vitest";

type Call = [table: string, method: string, ...args: unknown[]];
const state = vi.hoisted(() => ({
  calls: [] as Call[],
  interactions: [] as Record<string, unknown>[],
  listings: [] as Record<string, unknown>[],
}));
// PAR-01: the cards' total cost line has its own tests (lib/cost-estimate.test.ts).
vi.mock("@/lib/cost-estimate-data", () => ({ costLinesFor: async () => new Map() }));
vi.mock("@/lib/auth", () => ({ requireUser: async () => ({ id: "account" }) }));
vi.mock("@/lib/config", () => ({ webConfig: async () => ({ watchlistStaleDays: 30 }) }));
vi.mock("@/app/app/listings/actions", () => ({ setStatus: vi.fn(), setSaved: vi.fn(), recordPurchase: vi.fn(), setNote: vi.fn() }));
vi.mock("@/lib/supabase/server", () => ({
  createClient: async () => ({
    from: (table: string) => {
      const rows = () =>
        table === "user_listing_interactions" ? state.interactions : table === "listings" ? state.listings : [];
      const builder: Record<string, unknown> = new Proxy({}, {
        get: (_target, method: string) =>
          method === "then"
            ? (resolve: (value: unknown) => void) => resolve({ data: rows() })
            : (...args: unknown[]) => {
                state.calls.push([table, method, ...args]);
                return builder;
              },
      });
      return builder;
    },
  }),
}));

import SavedPage from "@/app/app/saved/page";

const listing = {
  id: 5, title: "Ford Fiesta", make: "Ford", model: "Fiesta", trim: null, year: 2018, price: 9000, currency: "USD",
  price_usd: 9000, mileage_km: 80000, location_text: "Rosario", published_at: null, first_seen_at: new Date().toISOString(),
  images: [], status: "active", probable_repost_of: null, body_type: null,
};

beforeEach(() => {
  state.calls = [];
  state.interactions = [{ listing_id: 5, status: "contacted", saved: false, note: "Llamé\nel martes <b>", updated_at: "2026-10-28" }];
  state.listings = [listing];
});

async function render(e?: string) {
  return renderToStaticMarkup(await SavedPage({ params: Promise.resolve({}), searchParams: Promise.resolve(e ? { e } : {}) }));
}
const interactionCalls = () => state.calls.filter((c) => c[0] === "user_listing_interactions");

it("lists saved and followed listings, purchased included, with their note (X-01)", async () => {
  await render();
  const calls = interactionCalls();
  expect(calls.find((c) => c[1] === "select")?.[2]).toContain("note");
  expect(calls).toContainEqual(["user_listing_interactions", "or", "saved.eq.true,status.in.(interested,contacted,visit_scheduled,purchased)"]);
  expect(calls.some((c) => c[1] === "eq")).toBe(false);
});

it.each(["contacted", "visit_scheduled", "purchased"])("filters by status with ?e=%s", async (e) => {
  await render(e);
  const calls = interactionCalls();
  expect(calls).toContainEqual(["user_listing_interactions", "eq", "status", e]);
  expect(calls.some((c) => c[1] === "or")).toBe(false);
});

it("falls back to Todos on an unknown ?e=", async () => {
  const html = await render("interested");
  expect(interactionCalls().some((c) => c[1] === "eq")).toBe(false);
  expect(html).toMatch(/<a[^>]*aria-current="page"[^>]*>Todos<\/a>/);
});

it("draws the filter pills with the active one marked", async () => {
  const html = await render("visit_scheduled");
  for (const label of ["Todos", "Contactados", "Visita agendada", "Comprados"]) expect(html).toContain(`>${label}</a>`);
  expect(html).toMatch(/<a[^>]*aria-current="page"[^>]*>Visita agendada<\/a>/);
  expect(html.match(/aria-current="page"/g)).toHaveLength(1);
});

it("shows each card's status, its note on one line and a compact status select", async () => {
  const html = await render();
  expect(html).toContain(">Contactado</span>");
  const note = html.match(/<p[^>]*data-testid="card-note"[^>]*>([\s\S]*?)<\/p>/);
  expect(note?.[0]).toContain("truncate");
  expect(note?.[1]).toContain("Llamé\nel martes &lt;b&gt;");
  expect(html).toMatch(/<div[^>]*class="[^"]*relative z-10[^"]*"[^>]*>[\s\S]*?<select[^>]*aria-label="Estado"/);
});

it("says what an empty filter means, without the first-time screen", async () => {
  state.interactions = [];
  const html = await render("contacted");
  expect(html).toContain("No marcaste publicaciones como contactadas.");
  expect(html).not.toContain("Todavía no guardaste publicaciones");
  expect(await render()).toContain("Todavía no guardaste publicaciones");
});
