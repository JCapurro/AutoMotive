import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));
const mocks = vi.hoisted(() => ({
  auth: { verifyOtp: vi.fn(), signOut: vi.fn() },
  accountForEmail: vi.fn(),
  claimThrottle: vi.fn(),
  afterRecoveryLink: vi.fn(),
  afterSignIn: vi.fn(),
}));
vi.mock("@/lib/supabase/server", () => ({ createClient: async () => ({ auth: mocks.auth }) }));
vi.mock("@/lib/email-only", () => ({ accountForEmail: mocks.accountForEmail, claimThrottle: mocks.claimThrottle, clientIpKey: async () => "ip", HOUR: 3600 }));
vi.mock("@/lib/account-proof", () => ({ afterRecoveryLink: mocks.afterRecoveryLink }));
vi.mock("@/lib/signup", () => ({ afterSignIn: mocks.afterSignIn }));

import { CODE_TRIES_PER_ACCOUNT_HOUR, normalizeCode, verifyEntryCode } from "@/lib/entry-code";

const lite = { user_id: "lite", email_only: true, confirmed: true };
const full = { user_id: "full", email_only: false, confirmed: true };

beforeEach(() => {
  vi.resetAllMocks();
  mocks.claimThrottle.mockResolvedValue(true);
  mocks.accountForEmail.mockResolvedValue(full);
  mocks.auth.verifyOtp.mockResolvedValue({ data: { user: { id: "full" } }, error: null });
  mocks.afterSignIn.mockResolvedValue(false);
});

describe("normalizeCode", () => {
  it("keeps 6 to 8 digits, with spaces or dashes typed in between", () => {
    expect(normalizeCode("123 456")).toBe("123456");
    expect(normalizeCode("123-456-78")).toBe("12345678");
    expect(normalizeCode("12345")).toBeNull();
    expect(normalizeCode("12345a")).toBeNull();
    expect(normalizeCode(null)).toBeNull();
  });
});

describe("verifyEntryCode", () => {
  it("checks the recovery code and sends a full account straight on", async () => {
    expect(await verifyEntryCode("person@example.com", " 123456 ", "/app/saved")).toEqual({ ok: true, href: "/app/saved", signedUp: false });
    expect(mocks.auth.verifyOtp).toHaveBeenCalledWith({ email: "person@example.com", token: "123456", type: "recovery" });
    expect(mocks.afterSignIn).toHaveBeenCalledOnce();
  });

  it("runs the link's proof for an email-only account and reports a first sign-up", async () => {
    mocks.accountForEmail.mockResolvedValue(lite);
    mocks.auth.verifyOtp.mockResolvedValue({ data: { user: { id: "lite" } }, error: null });
    mocks.afterRecoveryLink.mockResolvedValue("/app/cuenta?next=%2Fapp%2Fpro");
    mocks.afterSignIn.mockResolvedValue(true);
    expect(await verifyEntryCode("person@example.com", "123456", "/app/pro")).toEqual({ ok: true, href: "/app/cuenta?next=%2Fapp%2Fpro", signedUp: true });
    expect(mocks.afterRecoveryLink).toHaveBeenCalledWith(expect.anything(), "/auth/reset-password?next=%2Fapp%2Fpro");
    expect(mocks.afterSignIn).toHaveBeenCalledWith(expect.anything(), "email_code");
  });

  it("asks a never-confirmed signup for a new password", async () => {
    mocks.accountForEmail.mockResolvedValue({ user_id: "full", email_only: false, confirmed: false });
    expect(await verifyEntryCode("person@example.com", "123456", "/app")).toEqual({ ok: true, href: "/auth/reset-password?next=%2Fapp", signedUp: false });
  });

  it("drops an external destination", async () => {
    expect(await verifyEntryCode("person@example.com", "123456", "https://evil.example")).toMatchObject({ href: "/app" });
  });

  it("answers an unknown email exactly like a wrong code, without asking Auth", async () => {
    mocks.auth.verifyOtp.mockResolvedValue({ data: {}, error: { code: "otp_invalid" } });
    const wrong = await verifyEntryCode("person@example.com", "123456", "/app");
    mocks.accountForEmail.mockResolvedValue(null);
    mocks.auth.verifyOtp.mockClear();
    const unknown = await verifyEntryCode("nobody@example.com", "123456", "/app");
    expect(unknown).toEqual(wrong);
    expect(mocks.auth.verifyOtp).not.toHaveBeenCalled();
  });

  it("answers a mistyped code like an expired one (Auth says otp_expired for both)", async () => {
    mocks.auth.verifyOtp.mockResolvedValue({ data: {}, error: { code: "otp_expired" } });
    const expired = await verifyEntryCode("person@example.com", "123456", "/app");
    expect(expired).toMatchObject({ ok: false, error: expect.stringContaining("no es correcto o venció") });
  });

  it("caps tries per account and per IP, and fails closed when the brakes can't be read", async () => {
    mocks.claimThrottle.mockImplementation(async (kind: string, _key: string, limit: number) => kind !== "entry_code_user" || limit !== CODE_TRIES_PER_ACCOUNT_HOUR);
    expect((await verifyEntryCode("person@example.com", "123456", "/app")).ok).toBe(false);
    expect(mocks.claimThrottle).toHaveBeenCalledWith("entry_code_user", "full", CODE_TRIES_PER_ACCOUNT_HOUR, 3600);
    mocks.claimThrottle.mockResolvedValue(false);
    expect((await verifyEntryCode("person@example.com", "123456", "/app")).ok).toBe(false);
    mocks.claimThrottle.mockRejectedValue(new Error("db down"));
    expect((await verifyEntryCode("person@example.com", "123456", "/app")).ok).toBe(false);
    expect(mocks.auth.verifyOtp).not.toHaveBeenCalled();
  });

  it("refuses a malformed code before spending a try", async () => {
    expect((await verifyEntryCode("person@example.com", "abc", "/app")).ok).toBe(false);
    expect(mocks.claimThrottle).not.toHaveBeenCalled();
  });

  it("signs out a session that came back for another user", async () => {
    mocks.auth.verifyOtp.mockResolvedValue({ data: { user: { id: "someone-else" } }, error: null });
    expect((await verifyEntryCode("person@example.com", "123456", "/app")).ok).toBe(false);
    expect(mocks.auth.signOut).toHaveBeenCalledWith({ scope: "local" });
  });
});
