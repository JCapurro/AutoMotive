import { beforeEach, expect, it, vi } from "vitest";
import type { SupabaseClient } from "@supabase/supabase-js";
import type { Database } from "@/types/database";

const mocks = vi.hoisted(() => ({ track: vi.fn(), queuePixel: vi.fn(), getClaims: vi.fn(), eq: vi.fn(), cookies: new Map<string, string>() }));
vi.mock("next/headers", () => ({ cookies: async () => ({ get: (name: string) => (mocks.cookies.has(name) ? { value: mocks.cookies.get(name) } : undefined) }) }));
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
  mocks.cookies.clear();
});

it.each(["email", "google"] as const)("records a first confirmed sign-in with method %s", async (method) => {
  await afterSignIn(supabase, method);
  expect(mocks.track).toHaveBeenCalledWith(supabase, "user-id", "signup_completed", { method, channel: "unknown" });
  expect(mocks.queuePixel).toHaveBeenCalledWith("CompleteRegistration", { content_name: method }, "signup:user-id");
});

it("preserves email attribution for existing callers", async () => {
  await afterSignIn(supabase);
  expect(mocks.track).toHaveBeenCalledWith(supabase, "user-id", "signup_completed", { method: "email", channel: "unknown" });
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

it("copies the first visit kept by the proxy into the signup event", async () => {
  mocks.cookies.set("first_touch", encodeURIComponent(JSON.stringify({ source: "facebook", medium: "paid", landing: "/", evil: "x" })));
  await afterSignIn(supabase, "email_only");
  expect(mocks.track).toHaveBeenCalledWith(supabase, "user-id", "signup_completed", {
    method: "email_only", origin: { source: "facebook", medium: "paid", landing: "/" }, channel: "meta_ads",
  });
});

it("drops the first visit when tracking was refused", async () => {
  mocks.cookies.set("first_touch", encodeURIComponent(JSON.stringify({ source: "facebook" })));
  mocks.cookies.set("ads_consent", "denied");
  await afterSignIn(supabase, "email_only");
  expect(mocks.track).toHaveBeenCalledWith(supabase, "user-id", "signup_completed", { method: "email_only", channel: "unknown" });
});
