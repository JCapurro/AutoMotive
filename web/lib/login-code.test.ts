import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  auth: { signInWithPassword: vi.fn(), signInWithOAuth: vi.fn() },
  afterSignIn: vi.fn(),
  accountForEmail: vi.fn(),
  sendEntryLink: vi.fn(),
  claimThrottle: vi.fn(),
  createEmailOnlyUser: vi.fn(),
  verifyEntryCode: vi.fn(),
  config: { emailOnlySignup: { enabled: true, perIpHour: 5, perDay: 100 } },
}));
vi.mock("@/lib/supabase/server", () => ({ createClient: async () => ({ auth: mocks.auth }) }));
vi.mock("@/lib/signup", () => ({ afterSignIn: mocks.afterSignIn }));
vi.mock("@/lib/config", () => ({ webConfig: async () => mocks.config }));
vi.mock("@/lib/health-access", () => ({ HEALTH_OWNER_EMAIL: "owner@example.com" }));
vi.mock("@/lib/entry-code", () => ({ verifyEntryCode: mocks.verifyEntryCode }));
vi.mock("@/lib/email-only", () => ({
  accountForEmail: mocks.accountForEmail, sendEntryLink: mocks.sendEntryLink, claimThrottle: mocks.claimThrottle,
  createEmailOnlyUser: mocks.createEmailOnlyUser, clientIpKey: async () => "ip", HOUR: 3600, DAY: 86400,
  linkError: (result: string) => result === "busy" ? "Esperá un minuto." : "No se pudo.",
}));
vi.mock("next/headers", () => ({ headers: async () => new Headers({ origin: "https://eseauto.com.ar" }) }));
vi.mock("next/navigation", () => ({ redirect: (path: string) => { throw new Error(`redirect:${path}`); } }));

import { login, type LoginState } from "@/app/login/actions";

const form = (values: Record<string, string>) => { const data = new FormData(); for (const [k, v] of Object.entries(values)) data.set(k, v); return data; };
const start: LoginState = { step: "email", next: "/app" };
const lite = { user_id: "lite", email_only: true, confirmed: true };
const full = { user_id: "full", email_only: false, confirmed: true };

beforeEach(() => {
  vi.resetAllMocks();
  mocks.config.emailOnlySignup.enabled = true;
  mocks.claimThrottle.mockResolvedValue(true);
  mocks.sendEntryLink.mockResolvedValue("sent");
  mocks.accountForEmail.mockResolvedValue(null);
  mocks.auth.signInWithPassword.mockResolvedValue({ error: null });
});

describe("asking for the code", () => {
  it("sends it to an existing account and moves to the code step", async () => {
    mocks.accountForEmail.mockResolvedValue(full);
    const state = await login(start, form({ intent: "send-code", email: " Person@Example.com ", next: "/app/listings/1" }));
    expect(state).toEqual({ step: "code", email: "person@example.com", next: "/app/listings/1", signedUp: false });
    expect(mocks.sendEntryLink).toHaveBeenCalledWith("person@example.com", "/app/listings/1", full);
    expect(mocks.createEmailOnlyUser).not.toHaveBeenCalled();
  });

  it("creates an email-only account for a new email, with no session, and sends the code", async () => {
    mocks.createEmailOnlyUser.mockResolvedValue({ userId: "new", discard: vi.fn() });
    const state = await login(start, form({ intent: "send-code", email: "new@example.com", next: "/app/pro?plan=pass_30" }));
    expect(state).toMatchObject({ step: "code", signedUp: true });
    expect(mocks.sendEntryLink).toHaveBeenCalledWith("new@example.com", "/app/pro?plan=pass_30", { user_id: "new", email_only: true, confirmed: true });
    expect(mocks.afterSignIn).not.toHaveBeenCalled();
  });

  it("answers the same, sending nothing, when signups are off or over their brakes", async () => {
    mocks.config.emailOnlySignup.enabled = false;
    const off = await login(start, form({ intent: "send-code", email: "new@example.com" }));
    mocks.config.emailOnlySignup.enabled = true;
    mocks.claimThrottle.mockResolvedValue(false);
    const braked = await login(start, form({ intent: "send-code", email: "new@example.com" }));
    for (const state of [off, braked]) expect(state).toEqual({ step: "code", email: "new@example.com", next: "/app", signedUp: false });
    expect(mocks.createEmailOnlyUser).not.toHaveBeenCalled();
    expect(mocks.sendEntryLink).not.toHaveBeenCalled();
  });

  it("never makes the health owner's address an unproven account", async () => {
    await login(start, form({ intent: "send-code", email: "owner@example.com" }));
    expect(mocks.createEmailOnlyUser).not.toHaveBeenCalled();
  });

  it("stays on the email with Auth's rate limit", async () => {
    mocks.accountForEmail.mockResolvedValue(full);
    mocks.sendEntryLink.mockResolvedValue("busy");
    expect(await login(start, form({ intent: "send-code", email: "person@example.com" }))).toMatchObject({ step: "email", error: "Esperá un minuto." });
  });

  it("rejects an invalid email and an unknown intent", async () => {
    expect((await login(start, form({ intent: "send-code", email: "nope" }))).error).toBeTruthy();
    expect((await login(start, form({ intent: "other", email: "person@example.com" }))).error).toBe("Acción inválida.");
    expect(mocks.sendEntryLink).not.toHaveBeenCalled();
  });
});

describe("typing the code", () => {
  it("goes where the code says, with a safe destination", async () => {
    mocks.verifyEntryCode.mockResolvedValue({ ok: true, href: "/app/listings/1", signedUp: false });
    await expect(login({ step: "code", email: "person@example.com", next: "/app" }, form({ intent: "verify", email: "person@example.com", code: "123 456", next: "https://evil.example" })))
      .rejects.toThrow("redirect:/app/listings/1");
    expect(mocks.verifyEntryCode).toHaveBeenCalledWith("person@example.com", "123 456", "/app");
  });

  it("keeps the code step with the error and the earlier notice", async () => {
    mocks.verifyEntryCode.mockResolvedValue({ ok: false, error: "El código no es correcto." });
    const state = await login({ step: "code", email: "person@example.com", next: "/app", notice: "Sin contraseña." }, form({ intent: "verify", email: "person@example.com", code: "000000" }));
    expect(state).toEqual({ step: "code", email: "person@example.com", next: "/app", error: "El código no es correcto.", notice: "Sin contraseña." });
  });

  it("goes back to the email to change it", async () => {
    expect(await login({ step: "code", email: "person@example.com", next: "/app" }, form({ intent: "change-email" }))).toEqual({ step: "email", email: "person@example.com", next: "/app" });
  });
});

describe("the password, for whoever has one", () => {
  it("signs in and records the sign-in", async () => {
    await expect(login(start, form({ intent: "password", email: "Person@Example.com", password: "good-password", next: "/app/saved" }))).rejects.toThrow("redirect:/app/saved");
    expect(mocks.auth.signInWithPassword).toHaveBeenCalledWith({ email: "person@example.com", password: "good-password" });
    expect(mocks.afterSignIn).toHaveBeenCalledOnce();
  });

  it("sends the code to an email-only account, and to an unconfirmed signup", async () => {
    mocks.auth.signInWithPassword.mockResolvedValue({ error: { code: "invalid_credentials" } });
    mocks.accountForEmail.mockResolvedValue(lite);
    expect(await login(start, form({ intent: "password", email: "person@example.com", password: "x" }))).toMatchObject({ step: "code", notice: expect.stringContaining("no tiene contraseña") });
    mocks.auth.signInWithPassword.mockResolvedValue({ error: { code: "email_not_confirmed" } });
    mocks.accountForEmail.mockResolvedValue({ user_id: "pending", email_only: false, confirmed: false });
    expect(await login(start, form({ intent: "password", email: "person@example.com", password: "x" }))).toMatchObject({ step: "code", notice: expect.stringContaining("no está confirmado") });
    expect(mocks.sendEntryLink).toHaveBeenCalledTimes(2);
    expect(mocks.afterSignIn).not.toHaveBeenCalled();
  });

  it("keeps a wrong password on a full account generic, sending nothing", async () => {
    mocks.auth.signInWithPassword.mockResolvedValue({ error: { code: "invalid_credentials", message: "secret detail" } });
    mocks.accountForEmail.mockResolvedValue(full);
    const state = await login(start, form({ intent: "password", email: "person@example.com", password: "wrong" }));
    expect(state.step).toBe("password");
    expect(state.error).not.toContain("secret detail");
    expect(state).not.toHaveProperty("password");
    expect(mocks.sendEntryLink).not.toHaveBeenCalled();
  });

  it("brakes password guesses per connection", async () => {
    mocks.claimThrottle.mockResolvedValue(false);
    expect((await login(start, form({ intent: "password", email: "person@example.com", password: "x" }))).error).toContain("varios intentos");
    expect(mocks.auth.signInWithPassword).not.toHaveBeenCalled();
  });
});
