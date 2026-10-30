import { beforeEach, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ track: vi.fn(async () => {}), supabase: { tag: "user-client" } }));
vi.mock("server-only", () => ({}));
vi.mock("next/cache", () => ({ refresh: vi.fn() }));
vi.mock("@/lib/auth", () => ({ requireUser: async () => ({ id: "u1" }) }));
vi.mock("@/lib/events", () => ({ track: mocks.track }));
vi.mock("@/lib/supabase/server", () => ({ createClient: async () => mocks.supabase }));
vi.mock("@/lib/config", () => ({ webConfig: vi.fn() }));

import { trackTotalCostExpanded } from "@/app/app/listings/actions";

beforeEach(() => mocks.track.mockClear());

// PAR-01: opening «Ver detalle» under the total cost estimate.
it("logs total_cost_expanded with the listing, the jurisdiction and how many terms were missing", async () => {
  await trackTotalCostExpanded(501, ["caba", "rest"], 1);
  expect(mocks.track).toHaveBeenCalledWith(mocks.supabase, "u1", "total_cost_expanded", { listing_id: 501, jurisdiction: ["caba", "rest"], missing: 1 });
  await trackTotalCostExpanded(502, null, 2);
  expect(mocks.track).toHaveBeenLastCalledWith(mocks.supabase, "u1", "total_cost_expanded", { listing_id: 502, jurisdiction: null, missing: 2 });
});

it("validates its input with zod and logs nothing otherwise", async () => {
  for (const args of [[0, ["caba"], 0], [1.5, null, 0], [7, ["mars"], 0], [7, ["caba"], 5], [7, ["caba"], -1], [7, "caba", 0]] as const) {
    await trackTotalCostExpanded(...(args as unknown as [number, string[] | null, number]));
  }
  expect(mocks.track).not.toHaveBeenCalled();
});
