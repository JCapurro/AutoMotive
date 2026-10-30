import { beforeEach, describe, expect, it, vi } from "vitest";

const mock = vi.hoisted(() => ({ track: vi.fn() }));
vi.mock("@/lib/auth", () => ({ requireUser: async () => ({ id: "user-1" }) }));
vi.mock("next/cache", () => ({ refresh: vi.fn() }));
vi.mock("@/lib/events", () => ({ track: mock.track }));
vi.mock("@/lib/config", () => ({ webConfig: async () => ({}) }));
vi.mock("@/lib/supabase/server", () => ({ createClient: async () => ({}) }));
import { trackRiskChecklist } from "@/app/app/listings/actions";

describe("trackRiskChecklist (PAR-02)", () => {
  beforeEach(() => vi.clearAllMocks());

  it("records the view and the copy with the listing id only", async () => {
    await trackRiskChecklist(42, "viewed");
    await trackRiskChecklist(42, "copied");
    expect(mock.track.mock.calls.map((call) => call.slice(1))).toEqual([
      ["user-1", "risk_checklist_viewed", { listing_id: 42 }],
      ["user-1", "risk_checklist_copied", { listing_id: 42 }],
    ]);
  });

  it.each([
    [42, "shared"],
    [42, ""],
    [0, "copied"],
    [-1, "viewed"],
    [1.5, "copied"],
    [Number.NaN, "copied"],
    ["42", "copied"],
  ])("ignores listing %j with action %j", async (listingId, action) => {
    await trackRiskChecklist(listingId as number, action as "viewed");
    expect(mock.track).not.toHaveBeenCalled();
  });
});
