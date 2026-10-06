import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

const mocks = vi.hoisted(() => ({
  fetch: vi.fn(), signInWithOAuth: vi.fn(), exchangeCodeForSession: vi.fn(), afterSignIn: vi.fn(),
}));
vi.mock("@/lib/env", () => ({ supabaseUrl: "https://auth.example.com", supabaseAnonKey: "public-key" }));
vi.mock("@/lib/supabase/server", () => ({ createClient: async () => ({ auth: mocks }) }));
vi.mock("@/lib/signup", () => ({ afterSignIn: mocks.afterSignIn }));
vi.mock("next/headers", () => ({ headers: async () => new Headers({ origin: "https://eseauto.com.ar" }) }));
vi.mock("next/navigation", () => ({ redirect: (path: string) => { throw new Error(`redirect:${path}`); } }));

import { signInWithGoogle } from "@/app/login/actions";
import { GET as callback } from "@/app/auth/callback/route";

beforeEach(() => {
  vi.resetAllMocks();
  vi.stubEnv("SITE_URL", "https://eseauto.com.ar");
  vi.stubGlobal("fetch", mocks.fetch);
  mocks.fetch.mockResolvedValue({ ok: true, json: async () => ({ external: { google: true } }) });
  mocks.signInWithOAuth.mockResolvedValue({ data: { url: "https://auth.example.com/auth/v1/authorize?provider=google" }, error: null });
  mocks.exchangeCodeForSession.mockResolvedValue({ data: { user: { identities: [{ provider: "google" }] } }, error: null });
});
afterEach(() => vi.unstubAllGlobals());

describe("Google login", () => {
  it("starts PKCE independently of email/password and preserves the destination", async () => {
    await expect(signInWithGoogle({ next: "/app/searches/new" }, new FormData())).rejects.toThrow("redirect:https://auth.example.com/auth/v1/authorize?provider=google");
    expect(mocks.fetch).toHaveBeenCalledWith("https://auth.example.com/auth/v1/settings", { headers: { apikey: "public-key" }, cache: "no-store", signal: expect.any(AbortSignal) });
    expect(mocks.signInWithOAuth).toHaveBeenCalledWith({ provider: "google", options: {
      redirectTo: "https://eseauto.com.ar/auth/callback?next=%2Fapp%2Fsearches%2Fnew&provider=google", skipBrowserRedirect: true,
    } });
    expect(mocks.afterSignIn).not.toHaveBeenCalled();
  });

  it.each(["https://evil.example", "//evil.example", "/\\evil.example"])("rejects external destinations: %s", async (next) => {
    const form = new FormData();
    form.set("next", next);
    await expect(signInWithGoogle({ next: "/app" }, form)).rejects.toThrow("redirect:");
    const url = new URL(mocks.signInWithOAuth.mock.calls[0][0].options.redirectTo);
    expect(url.searchParams.get("next")).toBe("/app");
  });

  it("shows an actionable message when Google is disabled", async () => {
    mocks.fetch.mockResolvedValue({ ok: true, json: async () => ({ external: { google: false } }) });
    expect((await signInWithGoogle({ next: "/app" }, new FormData())).error).toContain("todavía no está disponible");
    expect(mocks.signInWithOAuth).not.toHaveBeenCalled();
  });

  it("handles settings outages without redirecting to an Auth error page", async () => {
    mocks.fetch.mockResolvedValue({ ok: false });
    expect((await signInWithGoogle({ next: "/app" }, new FormData())).error).toContain("No pudimos conectar");
    mocks.fetch.mockRejectedValue(new Error("network detail"));
    expect((await signInWithGoogle({ next: "/app" }, new FormData())).error).toContain("No pudimos conectar");
    expect(mocks.signInWithOAuth).not.toHaveBeenCalled();
  });

  it.each([
    { data: { url: null }, error: null },
    { data: { url: "https://auth.example.com" }, error: { message: "internal detail" } },
  ])("handles a failed OAuth initiation without exposing provider details", async (result) => {
    mocks.signInWithOAuth.mockResolvedValue(result);
    expect((await signInWithGoogle({ next: "/app" }, new FormData())).error).toBe("No pudimos iniciar el ingreso con Google. Probá de nuevo.");
  });
});

describe("Google callback", () => {
  it("exchanges the code before completing registration and redirects to the requested page", async () => {
    const response = await callback(new NextRequest("https://eseauto.com.ar/auth/callback?provider=google&code=valid&next=/app/settings"));
    expect(response.headers.get("location")).toBe("https://eseauto.com.ar/app/settings");
    expect(mocks.exchangeCodeForSession).toHaveBeenCalledWith("valid");
    expect(mocks.afterSignIn).toHaveBeenCalledWith(expect.anything(), "google");
    expect(mocks.exchangeCodeForSession.mock.invocationCallOrder[0]).toBeLessThan(mocks.afterSignIn.mock.invocationCallOrder[0]);
  });

  it("takes registration attribution from the verified identity, not the URL marker", async () => {
    mocks.exchangeCodeForSession.mockResolvedValue({ data: { user: { identities: [{ provider: "email" }] } }, error: null });
    await callback(new NextRequest("https://eseauto.com.ar/auth/callback?provider=google&code=valid"));
    expect(mocks.afterSignIn).toHaveBeenCalledWith(expect.anything());
  });

  it("attributes Google when signing in to a linked email account", async () => {
    mocks.exchangeCodeForSession.mockResolvedValue({ data: { user: {
      app_metadata: { provider: "email" }, identities: [{ provider: "email" }, { provider: "google" }],
    } }, error: null });
    await callback(new NextRequest("https://eseauto.com.ar/auth/callback?provider=google&code=valid"));
    expect(mocks.afterSignIn).toHaveBeenCalledWith(expect.anything(), "google");
  });

  it.each(["error=access_denied&code=unused", "", "code=expired"])("returns failures to login while preserving next: %s", async (params) => {
    mocks.exchangeCodeForSession.mockResolvedValue({ data: null, error: { message: "internal detail" } });
    const response = await callback(new NextRequest(`https://eseauto.com.ar/auth/callback?provider=google&next=/app/settings&${params}`));
    const url = new URL(response.headers.get("location")!);
    expect(url.pathname).toBe("/login");
    expect(url.searchParams.get("error")).toBe("google");
    expect(url.searchParams.get("next")).toBe("/app/settings");
    expect(url.searchParams.has("mode")).toBe(false);
    expect(mocks.afterSignIn).not.toHaveBeenCalled();
    if (params !== "code=expired") expect(mocks.exchangeCodeForSession).not.toHaveBeenCalled();
  });

  it("sanitizes callback destinations", async () => {
    const response = await callback(new NextRequest("https://eseauto.com.ar/auth/callback?provider=google&code=valid&next=https://evil.example"));
    expect(response.headers.get("location")).toBe("https://eseauto.com.ar/app");
  });
});
