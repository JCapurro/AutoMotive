import { beforeEach, expect, it, vi } from "vitest";

const mock = vi.hoisted(() => ({ rows: [] as { key: string; value: unknown }[], keys: [] as string[] }));
vi.mock("server-only", () => ({}));
vi.mock("@/lib/mercadopago-server", () => ({ paymentsEnabled: () => false }));
vi.mock("@/lib/supabase/admin", () => ({
  createAdminClient: () => ({
    from: () => ({
      select: () => ({
        in: async (_column: string, keys: string[]) => {
          mock.keys = keys;
          return { data: mock.rows.filter((r) => keys.includes(r.key)) };
        },
      }),
    }),
  }),
}));

import { webConfig } from "@/lib/config";

beforeEach(() => {
  mock.rows = [];
  mock.keys = [];
});

// webConfig is wrapped in React's cache(), a no-op outside a request: each call reads again.
it("defaults the note limit to 500 while app_config.listing_tracking is missing (X-01)", async () => {
  const cfg = await webConfig();
  expect(mock.keys).toContain("listing_tracking");
  expect(cfg.listingTracking).toEqual({ noteMaxChars: 500 });
});

it("reads app_config.listing_tracking.note_max_chars", async () => {
  mock.rows = [{ key: "listing_tracking", value: { note_max_chars: 300 } }];
  expect((await webConfig()).listingTracking).toEqual({ noteMaxChars: 300 });
});

it("falls back to 500 on a malformed or non-positive limit", async () => {
  for (const value of [{ note_max_chars: "x" }, { note_max_chars: 0 }, { note_max_chars: -1 }, "500"]) {
    mock.rows = [{ key: "listing_tracking", value }];
    expect((await webConfig()).listingTracking).toEqual({ noteMaxChars: 500 });
  }
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
