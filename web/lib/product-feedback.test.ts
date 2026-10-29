import { beforeEach, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ liveAccount: vi.fn(), rpc: vi.fn() }));
vi.mock("@/lib/auth", () => ({ liveAccount: mocks.liveAccount }));
vi.mock("@/lib/supabase/server", () => ({ createClient: async () => ({ rpc: mocks.rpc }) }));

import { submitProductFeedback } from "@/app/app/feedback/actions";

const input = { message: "Me gustaría poder comparar las versiones.", profileId: 12, requestId: "50505050-5050-4050-8050-505050505050" };
beforeEach(() => {
  vi.clearAllMocks();
  mocks.liveAccount.mockResolvedValue({ id: "account", email: "user@example.test" });
  mocks.rpc.mockResolvedValue({ data: "saved-feedback-id", error: null });
});

it("saves feedback through the authenticated RPC, with a retry-safe request id", async () => {
  expect(await submitProductFeedback(input)).toEqual({ ok: true });
  expect(mocks.rpc).toHaveBeenCalledWith("submit_product_feedback", {
    p_message: input.message, p_profile: 12, p_request: input.requestId,
  });
});
it.each(["", "corto", "x".repeat(2001)])("rejects an invalid message before saving", async (message) => {
  expect(await submitProductFeedback({ ...input, message })).toHaveProperty("error");
  expect(mocks.rpc).not.toHaveBeenCalled();
});
it("does not accept feedback from a revoked session", async () => {
  mocks.liveAccount.mockResolvedValue(null);
  expect(await submitProductFeedback(input)).toHaveProperty("error");
  expect(mocks.rpc).not.toHaveBeenCalled();
});
it("explains the daily limit without discarding the user's text", async () => {
  mocks.rpc.mockResolvedValue({ error: { message: "feedback_rate_limited" } });
  expect((await submitProductFeedback(input)).error).toContain("por hoy");
});
it("does not report success when persistence fails", async () => {
  mocks.rpc.mockRejectedValue(new Error("network failed"));
  expect(await submitProductFeedback(input)).toHaveProperty("error");
});
