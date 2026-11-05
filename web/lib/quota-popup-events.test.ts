import { beforeEach, describe, expect, it, vi } from "vitest";

// Pop-up del tope de la prueba (FreeResultLimit): the events of trackQuotaPopup.
const state = vi.hoisted(() => ({
  track: vi.fn<(...args: unknown[]) => Promise<void>>(async () => undefined),
  requireUser: vi.fn(async () => ({ id: "account" })),
}));
vi.mock("server-only", () => ({}));
vi.mock("next/cache", () => ({ refresh: vi.fn() }));
vi.mock("@/lib/auth", () => ({ requireUser: state.requireUser }));
vi.mock("@/lib/events", () => ({ track: state.track }));
vi.mock("@/lib/supabase/server", () => ({ createClient: async () => ({}) }));

import { trackQuotaPopup } from "@/app/app/pro/actions";

describe("trackQuotaPopup", () => {
  beforeEach(() => {
    state.track.mockClear();
    state.requireUser.mockClear();
    state.requireUser.mockResolvedValue({ id: "account" });
  });

  it("records the three events with the search, and the plan only when picked", async () => {
    await trackQuotaPopup("viewed", 7);
    await trackQuotaPopup("dismissed", 7);
    await trackQuotaPopup("plan_selected", 7, "pass_30");
    expect(state.track.mock.calls.map((c) => [c[2], c[3]])).toEqual([
      ["quota_popup_viewed", { search_profile_id: 7 }],
      ["quota_popup_dismissed", { search_profile_id: 7 }],
      ["quota_plan_selected", { search_profile_id: 7, plan: "pass_30" }],
    ]);
    expect(state.track.mock.calls.every((c) => c[1] === "account")).toBe(true);
  });

  it("ignores an unknown action, a non-integer search and an unknown plan", async () => {
    await trackQuotaPopup("hacked" as never, 7);
    await trackQuotaPopup("viewed", 1.5);
    await trackQuotaPopup("plan_selected", 7, "free" as never);
    expect(state.track.mock.calls).toHaveLength(1);
    expect(state.track.mock.calls[0][3]).toEqual({ search_profile_id: 7 });
  });

  it("never throws: a failed event cannot get in the way of the checkout", async () => {
    const log = vi.spyOn(console, "error").mockImplementation(() => undefined);
    state.requireUser.mockRejectedValueOnce(new Error("no session"));
    await expect(trackQuotaPopup("viewed", 7)).resolves.toBeUndefined();
    expect(state.track).not.toHaveBeenCalled();
    log.mockRestore();
  });
});
