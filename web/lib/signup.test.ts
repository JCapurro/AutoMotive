import { beforeEach, expect, it, vi } from "vitest";
import type { SupabaseClient } from "@supabase/supabase-js";
import type { Database } from "@/types/database";

const mocks = vi.hoisted(() => ({ track: vi.fn(), queuePixel: vi.fn(), getClaims: vi.fn(), eq: vi.fn() }));
vi.mock("server-only", () => ({}));
vi.mock("@/lib/events", () => ({ track: mocks.track }));
vi.mock("@/lib/meta-pixel-server", () => ({ queuePixel: mocks.queuePixel }));
import { afterSignIn } from "./signup";

const supabase = {
  auth: { getClaims: mocks.getClaims },
  from: () => ({ select: () => ({ eq: mocks.eq }) }),
} as unknown as SupabaseClient<Database>;

beforeEach(() => {
  vi.resetAllMocks();
  mocks.getClaims.mockResolvedValue({ data: { claims: { sub: "user-id" } } });
  mocks.eq.mockResolvedValue({ count: 0 });
});

it.each(["email", "google"] as const)("records a first confirmed sign-in with method %s", async (method) => {
  await afterSignIn(supabase, method);
  expect(mocks.track).toHaveBeenCalledWith(supabase, "user-id", "signup_completed", { method });
  expect(mocks.queuePixel).toHaveBeenCalledWith("CompleteRegistration", { content_name: method }, "signup:user-id");
});

it("preserves email attribution for existing callers", async () => {
  await afterSignIn(supabase);
  expect(mocks.track).toHaveBeenCalledWith(supabase, "user-id", "signup_completed", { method: "email" });
});

it("does not repeat registration on later Google logins", async () => {
  mocks.eq.mockResolvedValue({ count: 1 });
  await afterSignIn(supabase, "google");
  expect(mocks.track).not.toHaveBeenCalled();
  expect(mocks.queuePixel).not.toHaveBeenCalled();
});

it("does not record registration without verified claims", async () => {
  mocks.getClaims.mockResolvedValue({ data: null });
  await afterSignIn(supabase, "google");
  expect(mocks.track).not.toHaveBeenCalled();
  expect(mocks.queuePixel).not.toHaveBeenCalled();
});
