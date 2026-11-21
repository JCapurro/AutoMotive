import { beforeEach, describe, expect, it, vi } from "vitest";

// Oferta cuando la prueba oculta autos (docs/OFERTA_PRUEBA.md): the events of trackTrialOffer.
const state = vi.hoisted(() => ({
  track: vi.fn<(...args: unknown[]) => Promise<void>>(async () => undefined),
  requireUser: vi.fn(async () => ({ id: "account" })),
}));
vi.mock("server-only", () => ({}));
vi.mock("next/cache", () => ({ refresh: vi.fn() }));
vi.mock("@/lib/auth", () => ({ requireUser: state.requireUser }));
vi.mock("@/lib/events", () => ({ track: state.track }));
vi.mock("@/lib/supabase/server", () => ({ createClient: async () => ({}) }));

import { trackTrialOffer } from "@/app/app/pro/actions";

const counts = { shown: 30, hidden: 48 };

describe("trackTrialOffer", () => {
  beforeEach(() => {
    state.track.mockClear();
    state.requireUser.mockClear();
    state.requireUser.mockResolvedValue({ id: "account" });
  });

  it("records the three events with the search, where the offer was and what the person saw", async () => {
    await trackTrialOffer("viewed", 7, "sheet", counts);
    await trackTrialOffer("dismissed", 7, "sheet", counts);
    await trackTrialOffer("plan_selected", 7, "card", counts, "pass_7");
    expect(state.track.mock.calls.map((c) => [c[2], c[3]])).toEqual([
      ["trial_offer_viewed", { search_profile_id: 7, surface: "sheet", shown: 30, hidden: 48 }],
      ["trial_offer_dismissed", { search_profile_id: 7, surface: "sheet", shown: 30, hidden: 48 }],
      ["trial_offer_plan_selected", { search_profile_id: 7, surface: "card", shown: 30, hidden: 48, plan: "pass_7" }],
    ]);
    expect(state.track.mock.calls.every((c) => c[1] === "account")).toBe(true);
  });

  it("ignores an unknown action, surface or plan, a non-integer search and counts that aren't counts", async () => {
    await trackTrialOffer("hacked" as never, 7, "sheet", counts);
    await trackTrialOffer("viewed", 1.5, "sheet", counts);
    await trackTrialOffer("viewed", 7, "popup" as never, counts);
    await trackTrialOffer("viewed", 7, "strip", { shown: -1, hidden: 48 });
    await trackTrialOffer("viewed", 7, "strip", { shown: 30, hidden: 4.5 });
    await trackTrialOffer("viewed", 7, "strip", null as never);
    expect(state.track).not.toHaveBeenCalled();
    await trackTrialOffer("plan_selected", 7, "strip", counts, "free" as never);
    expect(state.track.mock.calls).toHaveLength(1);
    expect(state.track.mock.calls[0][3]).toEqual({ search_profile_id: 7, surface: "strip", shown: 30, hidden: 48 });
  });

  it("marks the complete variant of «40 + N» with complete: true, and only with a boolean", async () => {
    await trackTrialOffer("viewed", 7, "sheet", { shown: 45, hidden: 0, complete: true });
    await trackTrialOffer("plan_selected", 7, "sheet", { shown: 45, hidden: 0, complete: true }, "pass_7");
    await trackTrialOffer("dismissed", 7, "sheet", { shown: 45, hidden: 0, complete: false });
    await trackTrialOffer("viewed", 7, "sheet", { shown: 45, hidden: 0, complete: "yes" as never });
    expect(state.track.mock.calls.map((c) => [c[2], c[3]])).toEqual([
      ["trial_offer_viewed", { search_profile_id: 7, surface: "sheet", shown: 45, hidden: 0, complete: true }],
      ["trial_offer_plan_selected", { search_profile_id: 7, surface: "sheet", shown: 45, hidden: 0, complete: true, plan: "pass_7" }],
      ["trial_offer_dismissed", { search_profile_id: 7, surface: "sheet", shown: 45, hidden: 0 }],
    ]);
  });

  it("never throws: a failed event cannot get in the way of the checkout", async () => {
    const log = vi.spyOn(console, "error").mockImplementation(() => undefined);
    state.requireUser.mockRejectedValueOnce(new Error("no session"));
    await expect(trackTrialOffer("viewed", 7, "sheet", counts)).resolves.toBeUndefined();
    expect(state.track).not.toHaveBeenCalled();
    log.mockRestore();
  });
});
