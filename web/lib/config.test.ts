import { beforeEach, expect, it, vi } from "vitest";

const mock = vi.hoisted(() => ({ rows: [] as { key: string; value: unknown }[], keys: [] as string[], error: null as { message: string } | null }));
vi.mock("server-only", () => ({}));
vi.mock("@/lib/mercadopago-server", () => ({ paymentsEnabled: () => false }));
vi.mock("@/lib/supabase/admin", () => ({
  createAdminClient: () => ({
    from: () => ({
      select: () => ({
        in: async (_column: string, keys: string[]) => {
          mock.keys = keys;
          return mock.error ? { data: null, error: mock.error } : { data: mock.rows.filter((r) => keys.includes(r.key)), error: null };
        },
      }),
    }),
  }),
}));

import { webConfig } from "@/lib/config";

beforeEach(() => {
  mock.rows = [];
  mock.keys = [];
  mock.error = null;
});

// webConfig is wrapped in React's cache(), a no-op outside a request: each call reads again.
it("no longer reads app_config.listing_tracking: the note is gone (Juan 02/11)", async () => {
  mock.rows = [{ key: "listing_tracking", value: { note_max_chars: 300 } }];
  const cfg = await webConfig();
  expect(mock.keys).not.toContain("listing_tracking");
  expect(cfg).not.toHaveProperty("listingTracking");
});

// PAR-01: the cost estimator's parameters, parsed tolerantly.
it("reads app_config.cost_estimator: null without the row or a valid as_of, partial blocks as they are", async () => {
  expect(mock.keys).toEqual([]);
  expect((await webConfig()).costEstimator).toBeNull();
  expect(mock.keys).toContain("cost_estimator");
  mock.rows = [{ key: "cost_estimator", value: { as_of: "30/10/2026", fx: { max_age_days: 3, source: "x", as_of: "2026-10-30" } } }];
  expect((await webConfig()).costEstimator).toBeNull();
  mock.rows = [{ key: "cost_estimator", value: { as_of: "2026-10-30", fx: { max_age_days: 3, source: "x", as_of: "2026-10-30" }, dnrpa: { source: "x" } } }];
  const cfg = (await webConfig()).costEstimator;
  expect(cfg?.as_of).toBe("2026-10-30");
  expect(cfg?.blocks.fx).toEqual({ max_age_days: 3, source: "x", as_of: "2026-10-30" });
  expect(cfg?.blocks.dnrpa).toBeNull();
});

// Aviso de zona (docs/AVISO_ZONA.md): the switch, on only when enabled is true.
it("reads app_config.zone_notice: off without the row, null when app_config can't be read", async () => {
  expect((await webConfig()).zoneNotice).toEqual({ enabled: false });
  expect(mock.keys).toContain("zone_notice");
  mock.rows = [{ key: "zone_notice", value: { enabled: true } }];
  expect((await webConfig()).zoneNotice).toEqual({ enabled: true });
  mock.error = { message: "timeout" };
  expect((await webConfig()).zoneNotice).toBeNull();
});
