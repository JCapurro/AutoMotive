import { beforeEach, describe, expect, it, vi } from "vitest";

const m = vi.hoisted(() => ({
  currentUser: vi.fn(), accountForEmail: vi.fn(), claimThrottle: vi.fn(), sendEntryLink: vi.fn(), afterSignIn: vi.fn(),
  createUser: vi.fn(), generateLink: vi.fn(), deleteUser: vi.fn(), rpc: vi.fn(), verifyOtp: vi.fn(), signOut: vi.fn(), signInWithPassword: vi.fn(),
  config: { enabled: true, perIpHour: 10, perDay: 100, linksPerUserHour: 3, linksPerIpHour: 20, lookupsPerIpHour: 30 },
}));
vi.mock("@/lib/auth", () => ({ currentUser: m.currentUser }));
vi.mock("@/lib/config", () => ({ webConfig: async () => ({ emailOnlySignup: m.config }) }));
vi.mock("@/lib/email-only", () => ({
  HOUR: 3600, DAY: 86400,
  accountForEmail: m.accountForEmail, claimThrottle: m.claimThrottle, clientIpKey: async () => "ip-key",
  sendEntryLink: m.sendEntryLink, linkError: () => "Ya te mandamos un link hace un momento.",
}));
vi.mock("@/lib/signup", () => ({ afterSignIn: m.afterSignIn }));
vi.mock("@/lib/supabase/admin", () => ({
  createAdminClient: () => ({ auth: { admin: { createUser: m.createUser, generateLink: m.generateLink, deleteUser: m.deleteUser } }, rpc: m.rpc }),
}));
vi.mock("@/lib/supabase/server", () => ({ createClient: async () => ({ auth: { verifyOtp: m.verifyOtp, signOut: m.signOut, signInWithPassword: m.signInWithPassword } }) }));

import { enterForFreeSearch, linkForFreeSearch, startFreeSearch } from "@/app/actions";

const prompt = "Fiesta manual & Polo en Córdoba";
const href = `/app/searches/new?${new URLSearchParams({ prompt })}`;
const input = { prompt, email: " Persona@Example.com " };

beforeEach(() => {
  vi.resetAllMocks();
  m.config.enabled = true;
  m.currentUser.mockResolvedValue(null);
  m.accountForEmail.mockResolvedValue(null);
  m.claimThrottle.mockResolvedValue(true);
  m.sendEntryLink.mockResolvedValue("sent");
  m.createUser.mockResolvedValue({ data: { user: { id: "new-user" } }, error: null });
  m.rpc.mockResolvedValue({ data: true, error: null });
  m.generateLink.mockResolvedValue({ data: { properties: { hashed_token: "hash" }, user: { id: "new-user" } }, error: null });
  m.verifyOtp.mockResolvedValue({ data: { user: { id: "new-user" } }, error: null });
});

describe("a new email", () => {
  it("becomes an email-only account signed in on this browser, without any email", async () => {
    expect(await startFreeSearch(input)).toEqual({ status: "created", href, signedUp: true });
    expect(m.createUser).toHaveBeenCalledWith({ email: "persona@example.com", email_confirm: true });
    expect(m.rpc).toHaveBeenCalledWith("mark_email_only_account", { p_user: "new-user" });
    expect(m.generateLink).toHaveBeenCalledWith({ type: "magiclink", email: "persona@example.com" });
    expect(m.verifyOtp).toHaveBeenCalledWith({ type: "magiclink", token_hash: "hash" });
    expect(m.afterSignIn).toHaveBeenCalledWith(expect.anything(), "email_only");
    expect(m.sendEntryLink).not.toHaveBeenCalled();
    // Marked before any session exists.
    expect(m.rpc.mock.invocationCallOrder[0]).toBeLessThan(m.verifyOtp.mock.invocationCallOrder[0]);
  });

  it("is deleted, with no session, when it can't be marked email-only", async () => {
    m.rpc.mockResolvedValue({ data: false, error: null });
    expect(await startFreeSearch(input)).toMatchObject({ status: "error" });
    expect(m.deleteUser).toHaveBeenCalledWith("new-user");
    expect(m.generateLink).not.toHaveBeenCalled();
    expect(m.verifyOtp).not.toHaveBeenCalled();
  });

  it("never keeps a session for another user", async () => {
    m.verifyOtp.mockResolvedValue({ data: { user: { id: "someone-else" } }, error: null });
    expect(await startFreeSearch(input)).toMatchObject({ status: "error" });
    expect(m.signOut).toHaveBeenCalledWith({ scope: "local" });
    expect(m.deleteUser).toHaveBeenCalledWith("new-user");
    expect(m.afterSignIn).not.toHaveBeenCalled();
  });

  it("refuses a link that belongs to another user before verifying it", async () => {
    m.generateLink.mockResolvedValue({ data: { properties: { hashed_token: "hash" }, user: { id: "someone-else" } }, error: null });
    expect(await startFreeSearch(input)).toMatchObject({ status: "error" });
    expect(m.verifyOtp).not.toHaveBeenCalled();
  });

  it("says so past the per-IP or daily brake, without sending to the login", async () => {
    m.claimThrottle.mockImplementation(async (kind: string) => kind !== "free_search_signup_ip");
    expect(await startFreeSearch(input)).toMatchObject({ status: "unavailable" });
    expect(m.createUser).not.toHaveBeenCalled();
  });
});

describe("an email that already exists", () => {
  it("of a free search gets the link to its inbox, never a session", async () => {
    const account = { user_id: "lite", email_only: true, confirmed: true };
    m.accountForEmail.mockResolvedValue(account);
    expect(await startFreeSearch(input)).toEqual({ status: "existing_email_only", email: "persona@example.com" });
    expect(m.sendEntryLink).toHaveBeenCalledWith("persona@example.com", href, account);
    expect(m.createUser).not.toHaveBeenCalled();
    expect(m.generateLink).not.toHaveBeenCalled();
    expect(m.verifyOtp).not.toHaveBeenCalled();
  });

  it("of a full account is sent to the login, with no email and no session", async () => {
    m.accountForEmail.mockResolvedValue({ user_id: "full", email_only: false, confirmed: true });
    expect(await startFreeSearch(input)).toEqual({ status: "existing_account", email: "persona@example.com" });
    expect(m.sendEntryLink).not.toHaveBeenCalled();
    expect(m.generateLink).not.toHaveBeenCalled();
  });

  it("of a password signup never confirmed gets the link too (it confirms it and asks for a new password)", async () => {
    const account = { user_id: "pending", email_only: false, confirmed: false };
    m.accountForEmail.mockResolvedValue(account);
    expect(await startFreeSearch(input)).toEqual({ status: "existing_email_only", email: "persona@example.com", unconfirmed: true });
    expect(m.sendEntryLink).toHaveBeenCalledWith("persona@example.com", href, account);
    expect(m.verifyOtp).not.toHaveBeenCalled();
  });

  it("created by a concurrent request is treated as existing, not signed in", async () => {
    m.createUser.mockResolvedValue({ data: { user: null }, error: { status: 422, code: "email_exists" } });
    m.accountForEmail.mockResolvedValueOnce(null).mockResolvedValueOnce({ user_id: "lite", email_only: true, confirmed: true });
    expect(await startFreeSearch(input)).toMatchObject({ status: "existing_email_only" });
    expect(m.generateLink).not.toHaveBeenCalled();
    expect(m.verifyOtp).not.toHaveBeenCalled();
  });

  it("shows why a link could not go out", async () => {
    m.accountForEmail.mockResolvedValue({ user_id: "lite", email_only: true, confirmed: true });
    m.sendEntryLink.mockResolvedValue("busy");
    expect(await startFreeSearch(input)).toMatchObject({ status: "existing_email_only", error: expect.stringContaining("Ya te mandamos") });
  });
});

describe("the form", () => {
  it("validates the prompt and the email first", async () => {
    expect(await startFreeSearch({ prompt: "  ", email: "a@b.co" })).toMatchObject({ status: "error", field: "prompt" });
    expect(await startFreeSearch({ prompt, email: "not-an-email" })).toMatchObject({ status: "error", field: "email" });
    expect(m.accountForEmail).not.toHaveBeenCalled();
  });

  it("drops bots that fill the hidden field", async () => {
    expect(await startFreeSearch({ ...input, company: "ACME" })).toMatchObject({ status: "error" });
    expect(m.claimThrottle).not.toHaveBeenCalled();
    expect(m.createUser).not.toHaveBeenCalled();
  });

  it("goes straight to the search when already signed in", async () => {
    m.currentUser.mockResolvedValue({ id: "user", email: "persona@example.com" });
    expect(await startFreeSearch(input)).toEqual({ status: "created", href, signedUp: false });
    expect(m.createUser).not.toHaveBeenCalled();
  });

  it("says so when the tab is signed in with another email, instead of dropping the one typed", async () => {
    m.currentUser.mockResolvedValue({ id: "user", email: "otra@example.com" });
    expect(await startFreeSearch(input)).toMatchObject({ status: "error", field: "email", error: expect.stringContaining("otra@example.com") });
    expect(m.createUser).not.toHaveBeenCalled();
  });

  it("pauses while the free path is switched off", async () => {
    m.config.enabled = false;
    expect(await startFreeSearch(input)).toMatchObject({ status: "unavailable" });
    expect(m.accountForEmail).not.toHaveBeenCalled();
  });

  it("never makes the health dashboard's owner address an unproven account", async () => {
    const { HEALTH_OWNER_EMAIL } = await import("@/lib/health-access");
    expect(await startFreeSearch({ prompt, email: HEALTH_OWNER_EMAIL })).toMatchObject({ status: "existing_account" });
    expect(m.createUser).not.toHaveBeenCalled();
  });

  it("brakes repeated lookups from one IP", async () => {
    m.claimThrottle.mockResolvedValue(false);
    expect(await startFreeSearch(input)).toMatchObject({ status: "unavailable" });
    expect(m.accountForEmail).not.toHaveBeenCalled();
  });
});

describe("an email with a password, from the same pop-up", () => {
  it("signs in and goes on to the search", async () => {
    m.signInWithPassword.mockResolvedValue({ error: null });
    expect(await enterForFreeSearch({ ...input, password: "su-clave" })).toEqual({ status: "created", href, signedUp: false });
    expect(m.signInWithPassword).toHaveBeenCalledWith({ email: "persona@example.com", password: "su-clave" });
    expect(m.afterSignIn).toHaveBeenCalledOnce();
  });

  it("asks again on a wrong password, without signing in", async () => {
    m.signInWithPassword.mockResolvedValue({ error: { code: "invalid_credentials" } });
    expect(await enterForFreeSearch({ ...input, password: "otra" })).toMatchObject({ status: "error", field: "password" });
    expect(m.afterSignIn).not.toHaveBeenCalled();
  });

  it("brakes repeated attempts from one IP", async () => {
    m.claimThrottle.mockResolvedValue(false);
    expect(await enterForFreeSearch({ ...input, password: "su-clave" })).toMatchObject({ status: "error", field: "password" });
    expect(m.signInWithPassword).not.toHaveBeenCalled();
  });

  it("sends the link to enter instead, with the search as the destination", async () => {
    expect(await linkForFreeSearch(input)).toEqual({ status: "existing_email_only", email: "persona@example.com" });
    expect(m.sendEntryLink).toHaveBeenCalledWith("persona@example.com", href);
  });
});
