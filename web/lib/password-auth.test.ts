import { beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
const mocks = vi.hoisted(() => ({ auth: {
  signUp: vi.fn(), signInWithPassword: vi.fn(), resetPasswordForEmail: vi.fn(), resend: vi.fn(),
  signOut: vi.fn(), getUser: vi.fn(), updateUser: vi.fn(), verifyOtp: vi.fn(), exchangeCodeForSession: vi.fn(),
}, afterSignIn: vi.fn(), profile: null as { email_only: boolean } | null, accountForEmail: vi.fn(), sendEntryLink: vi.fn(), afterRecoveryLink: vi.fn() }));
vi.mock("@/lib/supabase/server", () => ({ createClient: async () => ({
  auth: mocks.auth,
  from: () => ({ select: () => ({ eq: () => ({ maybeSingle: async () => ({ data: mocks.profile }) }) }) }),
}) }));
vi.mock("@/lib/signup", () => ({ afterSignIn: mocks.afterSignIn }));
vi.mock("@/lib/email-only", () => ({
  accountForEmail: mocks.accountForEmail, sendEntryLink: mocks.sendEntryLink,
  linkError: (result: string) => result === "busy" ? "Ya te mandamos un link hace un momento." : "No se pudo.",
}));
vi.mock("@/lib/account-proof", () => ({ afterRecoveryLink: mocks.afterRecoveryLink, completeWithGoogle: vi.fn() }));
vi.mock("next/headers", () => ({ headers: async () => new Headers({ origin: "https://eseauto.com.ar" }) }));
vi.mock("next/navigation", () => ({ redirect: (path: string) => { throw new Error(`redirect:${path}`); } }));
import { authenticate, resendConfirmation } from "@/app/login/actions";
import { updatePassword } from "@/app/auth/reset-password/actions";
import { POST as confirm } from "@/app/auth/confirm/route";
import { GET as callback } from "@/app/auth/callback/route";
const form = (values: Record<string, string>) => { const data = new FormData(); for (const [k, v] of Object.entries(values)) data.set(k, v); return data; };
const confirmationRequest = (url: string) => new NextRequest("https://eseauto.com.ar/auth/confirm", { method: "POST", headers: { origin: "https://eseauto.com.ar" }, body: new URLSearchParams(new URL(url).searchParams) });
const credentials = { email: "Person@Example.com", password: "good-password", confirmPassword: "good-password" };
beforeEach(() => {
  vi.resetAllMocks();
  vi.stubEnv("SITE_URL", "https://eseauto.com.ar");
  for (const mock of Object.values(mocks.auth)) mock.mockResolvedValue({ error: null });
  mocks.auth.signUp.mockResolvedValue({ data: { session: null }, error: null });
  mocks.auth.getUser.mockResolvedValue({ data: { user: { id: "user" } }, error: null });
  mocks.profile = { email_only: false };
  mocks.accountForEmail.mockResolvedValue(null);
  mocks.sendEntryLink.mockResolvedValue("sent");
  // A full account: the password form, with the inner destination.
  mocks.afterRecoveryLink.mockImplementation(async (_client: unknown, next: string) => {
    const { afterRecovery } = await import("@/lib/navigation");
    return `/auth/reset-password?${new URLSearchParams({ next: afterRecovery(next) })}`;
  });
});
describe("password authentication", () => {
  it("signs up without completing registration until confirmation", async () => {
    const result = await authenticate("signup", { next: "/app/searches/new" }, form(credentials));
    expect(result).toEqual({ sent: true, email: "person@example.com", next: "/app/searches/new" });
    expect(mocks.auth.signUp).toHaveBeenCalledWith({ email: "person@example.com", password: credentials.password, options: { emailRedirectTo: "https://eseauto.com.ar/auth/callback?next=%2Fapp%2Fsearches%2Fnew" } });
    expect(mocks.afterSignIn).not.toHaveBeenCalled();
  });
  it("preserves the landing prompt in signup emails and password login", async () => {
    const next = `/app/searches/new?${new URLSearchParams({ prompt: "Fiesta & Polo en Córdoba" })}`;
    await authenticate("signup", { next }, form(credentials));
    const callbackUrl = new URL(mocks.auth.signUp.mock.calls[0][0].options.emailRedirectTo);
    expect(callbackUrl.searchParams.get("next")).toBe(next);
    await expect(authenticate("login", { next }, form(credentials))).rejects.toThrow(`redirect:${next}`);
  });
  it("rejects short and mismatched passwords before contacting Auth", async () => {
    expect((await authenticate("signup", { next: "/app" }, form({ ...credentials, password: "short" }))).error).toBeTruthy();
    expect((await authenticate("signup", { next: "/app" }, form({ ...credentials, confirmPassword: "different" }))).error).toBeTruthy();
    expect(mocks.auth.signUp).not.toHaveBeenCalled();
  });
  it("rejects an invalid email", async () => {
    expect((await authenticate("login", { next: "/app" }, form({ ...credentials, email: "invalid" }))).error).toBeTruthy();
    expect(mocks.auth.signInWithPassword).not.toHaveBeenCalled();
  });
  it("discards an unexpected automatic signup session", async () => {
    mocks.auth.signUp.mockResolvedValue({ data: { session: {} }, error: null });
    const result = await authenticate("signup", { next: "/app" }, form(credentials));
    expect(mocks.auth.signOut).toHaveBeenCalled();
    expect(result.error).toContain("no está habilitada");
    expect(result.sent).not.toBe(true);
  });
  it("signs in and sanitizes the destination without returning passwords", async () => {
    await expect(authenticate("login", { next: "/app" }, form({ ...credentials, next: "https://evil.example" }))).rejects.toThrow("redirect:/app");
    expect(mocks.auth.signInWithPassword).toHaveBeenCalledWith({ email: "person@example.com", password: credentials.password });
    expect(mocks.afterSignIn).toHaveBeenCalledOnce();
  });
  it("reports confirmation required without exposing provider errors", async () => {
    mocks.auth.signInWithPassword.mockResolvedValue({ error: { code: "email_not_confirmed" } });
    const result = await authenticate("login", { next: "/app" }, form(credentials));
    expect(result.error).toContain("Confirmá tu email");
    expect(result).not.toHaveProperty("password");
    expect(mocks.afterSignIn).not.toHaveBeenCalled();
  });
  it("returns generic invalid-credentials feedback", async () => {
    mocks.auth.signInWithPassword.mockResolvedValue({ error: { code: "invalid_credentials", message: "secret detail" } });
    const result = await authenticate("login", { next: "/app" }, form(credentials));
    expect(result.error).not.toContain("secret detail");
  });
  it("sends the link to enter without enumerating accounts", async () => {
    expect((await authenticate("recover", { next: "/app/pro?plan=pass_30" }, form({ email: credentials.email }))).sent).toBe(true);
    expect(mocks.sendEntryLink).toHaveBeenCalledWith("person@example.com", "/app/pro?plan=pass_30");
    expect(mocks.afterSignIn).not.toHaveBeenCalled();
  });
  it("handles email rate limits", async () => {
    mocks.sendEntryLink.mockResolvedValue("busy");
    expect((await authenticate("recover", { next: "/app" }, form(credentials))).error).toContain("Ya te mandamos");
  });
  it("sends the link to an email-only account that tried a password", async () => {
    const account = { user_id: "lite", email_only: true, confirmed: true };
    mocks.auth.signInWithPassword.mockResolvedValue({ error: { code: "invalid_credentials" } });
    mocks.accountForEmail.mockResolvedValue(account);
    const result = await authenticate("login", { next: "/app/listings/1" }, form(credentials));
    expect(result).toMatchObject({ sent: true, entry: "password" });
    expect(mocks.sendEntryLink).toHaveBeenCalledWith("person@example.com", "/app/listings/1", account);
    expect(mocks.afterSignIn).not.toHaveBeenCalled();
  });
  it("keeps a wrong password on a full account generic, without sending anything", async () => {
    mocks.auth.signInWithPassword.mockResolvedValue({ error: { code: "invalid_credentials" } });
    mocks.accountForEmail.mockResolvedValue({ user_id: "full", email_only: false, confirmed: true });
    expect((await authenticate("login", { next: "/app" }, form(credentials))).error).toBeTruthy();
    expect(mocks.sendEntryLink).not.toHaveBeenCalled();
  });
  it("answers a signup over a free search with the link instead of Auth's signup", async () => {
    const account = { user_id: "lite", email_only: true, confirmed: true };
    mocks.accountForEmail.mockResolvedValue(account);
    const result = await authenticate("signup", { next: "/app/pro?plan=pass_30" }, form(credentials));
    expect(result).toMatchObject({ sent: true, entry: "signup" });
    expect(mocks.auth.signUp).not.toHaveBeenCalled();
    expect(mocks.sendEntryLink).toHaveBeenCalledWith("person@example.com", "/app/pro?plan=pass_30", account);
  });
  it("resends the signup confirmation", async () => {
    await resendConfirmation({ next: "/app" }, form(credentials));
    expect(mocks.auth.resend).toHaveBeenCalledWith({ type: "signup", email: "person@example.com", options: { emailRedirectTo: "https://eseauto.com.ar/auth/callback?next=%2Fapp" } });
  });
});
describe("password updates", () => {
  it("rejects unsigned requests", async () => {
    mocks.auth.getUser.mockResolvedValue({ data: { user: null }, error: null });
    expect((await updatePassword("/app", {}, form(credentials))).error).toContain("venció");
    expect(mocks.auth.updateUser).not.toHaveBeenCalled();
  });
  it("validates repeated password on the server", async () => {
    expect((await updatePassword("/app", {}, form({ ...credentials, confirmPassword: "different" }))).error).toContain("no coinciden");
    expect(mocks.auth.updateUser).not.toHaveBeenCalled();
  });
  it("updates through Supabase and signs out", async () => {
    await expect(updatePassword("/app/pro?plan=pass_30", {}, form(credentials))).rejects.toThrow("redirect:/login?password=updated&next=%2Fapp%2Fpro%3Fplan%3Dpass_30");
    expect(mocks.auth.updateUser).toHaveBeenCalledWith({ password: credentials.password });
    expect(mocks.auth.signOut).toHaveBeenCalled();
  });
  it("keeps provider rejection visible without claiming success", async () => {
    mocks.auth.updateUser.mockResolvedValue({ error: { code: "same_password" } });
    expect((await updatePassword("/app", {}, form(credentials))).error).toContain("distinta");
    expect(mocks.auth.signOut).not.toHaveBeenCalled();
  });
  it("never sets a password on an email-only account here", async () => {
    mocks.profile = { email_only: true };
    await expect(updatePassword("/app/settings", {}, form(credentials))).rejects.toThrow("redirect:/app/cuenta?next=%2Fapp%2Fsettings");
    expect(mocks.auth.updateUser).not.toHaveBeenCalled();
  });
});
describe("email links", () => {
  it("forces recovery to the password form and skips registration metrics", async () => {
    const response = await confirm(confirmationRequest("https://eseauto.com.ar/auth/confirm?token_hash=test&type=recovery&next=/admin"));
    expect(response.headers.get("location")).toBe("https://eseauto.com.ar/auth/reset-password?next=%2Fapp");
    expect(mocks.afterRecoveryLink.mock.calls[0][1]).toBe("/auth/reset-password");
    expect(mocks.auth.verifyOtp).toHaveBeenCalledWith({ type: "recovery", token_hash: "test" });
    expect(mocks.afterSignIn).not.toHaveBeenCalled();
  });
  it("accepts signup token hashes through the template callback", async () => {
    const response = await callback(new NextRequest("https://eseauto.com.ar/auth/callback?token_hash=test&type=signup&next=/app/searches/new"));
    expect(response.headers.get("location")).toContain("/auth/confirm-email?");
    expect(mocks.auth.verifyOtp).not.toHaveBeenCalled();
    expect(mocks.afterSignIn).not.toHaveBeenCalled();
  });
  it("carries the destination of a recovery link through its password step", async () => {
    const next = `/auth/reset-password?${new URLSearchParams({ next: "/app/pro?plan=pass_30" })}`;
    const response = await confirm(confirmationRequest(`https://eseauto.com.ar/auth/confirm?${new URLSearchParams({ token_hash: "test", type: "recovery", next })}`));
    expect(response.headers.get("location")).toBe("https://eseauto.com.ar/auth/reset-password?next=%2Fapp%2Fpro%3Fplan%3Dpass_30");
    expect(mocks.afterRecoveryLink.mock.calls[0][1]).toBe(next);
  });
  it("drops an external destination nested in a recovery link", async () => {
    const next = `/auth/reset-password?${new URLSearchParams({ next: "/\tevil.example" })}`;
    const response = await confirm(confirmationRequest(`https://eseauto.com.ar/auth/confirm?${new URLSearchParams({ token_hash: "test", type: "recovery", next })}`));
    expect(response.headers.get("location")).toBe("https://eseauto.com.ar/auth/reset-password?next=%2Fapp");
  });
  it("exchanges a PKCE recovery code without marking registration", async () => {
    const response = await callback(new NextRequest("https://eseauto.com.ar/auth/callback?code=test&next=/auth/reset-password"));
    expect(response.headers.get("location")).toBe("https://eseauto.com.ar/auth/reset-password?next=%2Fapp");
    expect(mocks.auth.exchangeCodeForSession).toHaveBeenCalledWith("test");
    expect(mocks.afterSignIn).not.toHaveBeenCalled();
  });
  it("expired recovery links return to the recovery request", async () => {
    mocks.auth.verifyOtp.mockResolvedValue({ error: { code: "otp_expired" } });
    const response = await confirm(confirmationRequest("https://eseauto.com.ar/auth/confirm?token_hash=test&type=recovery"));
    expect(response.headers.get("location")).toContain("mode=recover");
    expect(mocks.afterSignIn).not.toHaveBeenCalled();
  });
  it("rejects invalid token types and external redirect destinations", async () => {
    const invalid = await confirm(confirmationRequest("https://eseauto.com.ar/auth/confirm?token_hash=test&type=invalid"));
    expect(invalid.headers.get("location")).toContain("error=link");
    expect(mocks.auth.verifyOtp).not.toHaveBeenCalled();
    const valid = await confirm(confirmationRequest("https://eseauto.com.ar/auth/confirm?token_hash=test&type=signup&next=https://evil.example"));
    expect(valid.headers.get("location")).toBe("https://eseauto.com.ar/app");
  });
});
