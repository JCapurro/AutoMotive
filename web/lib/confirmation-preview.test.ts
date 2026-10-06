import { beforeEach, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
const auth = vi.hoisted(() => ({ verifyOtp: vi.fn(), getUser: vi.fn() }));
vi.mock("@/lib/supabase/server", () => ({ createClient: async () => ({ auth }) }));
vi.mock("@/lib/signup", () => ({ afterSignIn: vi.fn() }));
import { GET, HEAD, POST } from "@/app/auth/confirm/route";
import { GET as callback, HEAD as callbackHead } from "@/app/auth/callback/route";
beforeEach(() => {
  vi.resetAllMocks();
  auth.verifyOtp.mockResolvedValue({ error: null });
  auth.getUser.mockResolvedValue({ data: { user: null }, error: null });
});
it("HEAD previews on both legacy email endpoints do not consume tokens", () => {
  for (const head of [HEAD, callbackHead]) {
    expect(head().status).toBe(200);
    expect(auth.verifyOtp).not.toHaveBeenCalled();
  }
});
it("rejects confirmation form submissions from another site", async () => {
  const response = await POST(new NextRequest("https://www.eseauto.com.ar/auth/confirm", {
    method: "POST", headers: { origin: "https://evil.example" },
    body: new URLSearchParams({ token_hash: "test", type: "signup" }),
  }));
  expect(response.status).toBe(403);
  expect(auth.verifyOtp).not.toHaveBeenCalled();
});
it("opening or previewing the email must not consume its one-use signup token", async () => {
  for (const handler of [GET, callback]) {
    const response = await handler(new NextRequest("https://www.eseauto.com.ar/auth/confirm?token_hash=preview-token&type=signup&next=/app/settings"));
    expect(response.headers.get("location")).toContain("/auth/confirm-email?");
    expect(auth.verifyOtp).not.toHaveBeenCalled();
  }
});
