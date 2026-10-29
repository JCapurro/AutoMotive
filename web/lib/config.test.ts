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
