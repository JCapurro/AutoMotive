import { beforeEach, describe, expect, it, vi } from "vitest";

const m = vi.hoisted(() => ({
  claims: { sub: "user", session_id: "session" } as Record<string, string> | null,
  profile: { email_only: true } as { email_only: boolean } | null,
  signOut: vi.fn(), recordProof: vi.fn(), rpc: vi.fn(),
}));
vi.mock("server-only", () => ({}));
vi.mock("@/lib/email-only", () => ({ recordProof: m.recordProof }));
vi.mock("@/lib/supabase/admin", () => ({ createAdminClient: () => ({ rpc: m.rpc }) }));

import { afterRecoveryLink, completeWithGoogle } from "@/lib/account-proof";

const client = () => ({
  auth: { getClaims: async () => ({ data: m.claims ? { claims: m.claims } : null }), signOut: m.signOut },
  from: () => ({ select: () => ({ eq: () => ({ maybeSingle: async () => ({ data: m.profile }) }) }) }),
}) as never;
const next = `/auth/reset-password?${new URLSearchParams({ next: "/app/pro?plan=pass_30" })}`;

beforeEach(() => {
  vi.resetAllMocks();
  m.claims = { sub: "user", session_id: "session" };
  m.profile = { email_only: true };
  m.rpc.mockResolvedValue({ data: true, error: null });
});

describe("a used recovery link", () => {
  it("lets an email-only session choose its password and closes every other session", async () => {
    expect(await afterRecoveryLink(client(), next)).toBe("/app/cuenta?next=%2Fapp%2Fpro%3Fplan%3Dpass_30");
    expect(m.recordProof).toHaveBeenCalledWith("user", "session", "email_link");
    expect(m.signOut).toHaveBeenCalledWith({ scope: "others" });
    expect(m.rpc).toHaveBeenCalledWith("secure_email_only_account", { p_user: "user" });
  });

  it("takes an email-only session that isn't paying straight to where it was going", async () => {
    const search = `/auth/reset-password?${new URLSearchParams({ next: "/app/searches/new?prompt=fiesta" })}`;
    expect(await afterRecoveryLink(client(), search)).toBe("/app/searches/new?prompt=fiesta");
    expect(m.recordProof).toHaveBeenCalledWith("user", "session", "email_link");
  });

  it("takes a full account to the new password form", async () => {
    m.profile = { email_only: false };
    expect(await afterRecoveryLink(client(), next)).toBe("/auth/reset-password?next=%2Fapp%2Fpro%3Fplan%3Dpass_30");
    expect(m.recordProof).not.toHaveBeenCalled();
    expect(m.signOut).not.toHaveBeenCalled();
  });
});

describe("Google over an email-only account", () => {
  const google = (email: string, verified: unknown) => ({
    id: "user", email: "persona@gmail.com",
    identities: [{ provider: "google", identity_data: { email, email_verified: verified } }],
  }) as never;

  it("closes every other session, then completes it, when Google vouches for the same email", async () => {
    m.signOut.mockResolvedValue({ error: null });
    await completeWithGoogle(client(), google("Persona@gmail.com", true));
    expect(m.recordProof).toHaveBeenCalledWith("user", "session", "google");
    expect(m.rpc).toHaveBeenCalledWith("complete_email_only_account", { p_user: "user", p_session: "session", p_method: "google" });
    expect(m.signOut).toHaveBeenCalledWith({ scope: "others" });
    const complete = m.rpc.mock.calls.findIndex(([name]) => name === "complete_email_only_account");
    expect(m.signOut.mock.invocationCallOrder[0]).toBeLessThan(m.rpc.mock.invocationCallOrder[complete]);
  });

  it("doesn't complete it while the other sessions couldn't be closed", async () => {
    m.signOut.mockResolvedValue({ error: { message: "network" } });
    await completeWithGoogle(client(), google("persona@gmail.com", true));
    expect(m.rpc).not.toHaveBeenCalledWith("complete_email_only_account", expect.anything());
  });

  it.each([["otra@gmail.com", true], ["persona@gmail.com", false]])("does nothing for %s (verified %s)", async (email, verified) => {
    await completeWithGoogle(client(), google(email, verified));
    expect(m.rpc).not.toHaveBeenCalled();
    expect(m.signOut).not.toHaveBeenCalled();
  });

  it("leaves full accounts alone", async () => {
    m.profile = { email_only: false };
    await completeWithGoogle(client(), google("persona@gmail.com", true));
    expect(m.rpc).not.toHaveBeenCalled();
  });

  it("survives a refusal from the database (the account stays email-only)", async () => {
    m.signOut.mockResolvedValue({ error: null });
    m.rpc.mockResolvedValue({ data: null, error: { message: "proof_required" } });
    await expect(completeWithGoogle(client(), google("persona@gmail.com", true))).resolves.toBeUndefined();
  });
});
