import { beforeEach, describe, expect, it, vi } from "vitest";

const m = vi.hoisted(() => ({
  liveAccount: vi.fn(), sendEntryLink: vi.fn(), hasFreshProof: vi.fn(), rpc: vi.fn(), updateUser: vi.fn(), signOut: vi.fn(),
  verifyEntryCode: vi.fn(), startPayment: vi.fn(), automaticPayments: true,
}));
vi.mock("@/lib/auth", () => ({ liveAccount: m.liveAccount }));
vi.mock("@/lib/entry-code", () => ({ verifyEntryCode: m.verifyEntryCode }));
vi.mock("@/app/app/pro/billing-actions", () => ({ startPayment: m.startPayment }));
vi.mock("@/lib/config", () => ({ webConfig: async () => ({ automaticPayments: m.automaticPayments }) }));
vi.mock("@/lib/email-only", () => ({ sendEntryLink: m.sendEntryLink, hasFreshProof: m.hasFreshProof, linkError: () => "Ya te mandamos un link hace un momento." }));
vi.mock("@/lib/supabase/admin", () => ({ createAdminClient: () => ({ rpc: m.rpc }) }));
vi.mock("@/lib/supabase/server", () => ({ createClient: async () => ({ auth: { updateUser: m.updateUser, signOut: m.signOut } }) }));
vi.mock("next/navigation", () => ({ redirect: (path: string) => { throw new Error(`redirect:${path}`); } }));

import { completeAccount, confirmAccountCode, continueToPayment, sendAccountLink } from "@/app/app/cuenta/actions";
import { payPlan } from "@/lib/pro";

const form = (password: string, confirmPassword = password) => {
  const data = new FormData();
  data.set("password", password);
  data.set("confirmPassword", confirmPassword);
  return data;
};
const lite = { id: "user", email: "persona@example.com", sessionId: "session", emailOnly: true };

beforeEach(() => {
  vi.resetAllMocks();
  m.liveAccount.mockResolvedValue(lite);
  m.rpc.mockResolvedValue({ data: true, error: null });
  m.updateUser.mockResolvedValue({ error: null });
  m.signOut.mockResolvedValue({ error: null });
  m.sendEntryLink.mockResolvedValue("sent");
  m.hasFreshProof.mockResolvedValue(true);
  m.startPayment.mockResolvedValue({ url: "https://mercadopago.example/checkout" });
  m.automaticPayments = true;
});

describe("choosing the password", () => {
  it("closes the other sessions, completes the account, then sets the password", async () => {
    await expect(completeAccount("/app/pro?plan=pass_30", {}, form("good-password"))).rejects.toThrow("redirect:/app/pro?plan=pass_30");
    expect(m.signOut).toHaveBeenCalledWith({ scope: "others" });
    expect(m.rpc).toHaveBeenCalledWith("complete_email_only_account", { p_user: "user", p_session: "session", p_method: "password" });
    expect(m.updateUser).toHaveBeenCalledWith({ password: "good-password" });
    expect(m.signOut.mock.invocationCallOrder[0]).toBeLessThan(m.rpc.mock.invocationCallOrder[0]);
    expect(m.rpc.mock.invocationCallOrder[0]).toBeLessThan(m.updateUser.mock.invocationCallOrder[0]);
  });

  it("stops if the other sessions can't be closed", async () => {
    m.signOut.mockResolvedValue({ error: { message: "network" } });
    expect((await completeAccount("/app", {}, form("good-password"))).error).toBeTruthy();
    expect(m.rpc).not.toHaveBeenCalled();
    expect(m.updateUser).not.toHaveBeenCalled();
  });

  it("asks for a new link when this session has no fresh proof", async () => {
    m.hasFreshProof.mockResolvedValue(false);
    expect(await completeAccount("/app", {}, form("good-password"))).toMatchObject({ expired: true });
    expect(m.signOut).not.toHaveBeenCalled();
    expect(m.rpc).not.toHaveBeenCalled();
    expect(m.updateUser).not.toHaveBeenCalled();
  });

  it("rechecks proof transactionally after closing other sessions", async () => {
    m.rpc.mockResolvedValue({ data: null, error: { message: "proof_required" } });
    expect(await completeAccount("/app", {}, form("good-password"))).toMatchObject({ expired: true });
    expect(m.updateUser).not.toHaveBeenCalled();
  });

  it("tells a database failure apart from an expired link", async () => {
    m.rpc.mockResolvedValue({ data: null, error: { message: "connection reset" } });
    const result = await completeAccount("/app", {}, form("good-password"));
    expect(result.expired).toBeUndefined();
    expect(m.updateUser).not.toHaveBeenCalled();
  });

  it("validates the password before touching anything", async () => {
    expect((await completeAccount("/app", {}, form("short"))).error).toContain("8 caracteres");
    expect((await completeAccount("/app", {}, form("good-password", "other-password"))).error).toContain("no coinciden");
    expect(m.rpc).not.toHaveBeenCalled();
  });

  it("does nothing for a full account or a revoked session", async () => {
    m.liveAccount.mockResolvedValue({ ...lite, emailOnly: false });
    await expect(completeAccount("/app/settings", {}, form("good-password"))).rejects.toThrow("redirect:/app/settings");
    m.liveAccount.mockResolvedValue(null);
    expect((await completeAccount("/app", {}, form("good-password"))).error).toContain("venció");
    expect(m.rpc).not.toHaveBeenCalled();
    expect(m.updateUser).not.toHaveBeenCalled();
  });

  it("never follows an external destination", async () => {
    await expect(completeAccount("https://evil.example", {}, form("good-password"))).rejects.toThrow("redirect:/app");
  });
});

describe("asking for the link", () => {
  it("sends it to the account's own email, carrying where it was headed", async () => {
    expect(await sendAccountLink("/app/pro?plan=pass_30")).toEqual({ sent: true });
    expect(m.sendEntryLink).toHaveBeenCalledWith("persona@example.com", "/app/pro?plan=pass_30", { user_id: "user", email_only: true, confirmed: true });
  });

  it("explains a link that could not go out", async () => {
    m.sendEntryLink.mockResolvedValue("busy");
    expect((await sendAccountLink("/app")).error).toContain("Ya te mandamos");
  });
});

const codeForm = (code: string) => { const data = new FormData(); data.set("code", code); return data; };

describe("typing the code", () => {
  it("goes on to Mercado Pago by itself when it was typed on the way to paying", async () => {
    m.verifyEntryCode.mockResolvedValue({ ok: true, signedUp: false, href: "/app/cuenta?next=%2Fapp%2Fpro%3Fplan%3Dpass_7" });
    await expect(confirmAccountCode("/app/pro?plan=pass_7", {}, codeForm("123456")))
      .rejects.toThrow("redirect:/app/cuenta?next=%2Fapp%2Fpro%3Fplan%3Dpass_7&pagar=1");
    expect(m.verifyEntryCode).toHaveBeenCalledWith("persona@example.com", "123456", "/app/pro?plan=pass_7");
  });

  it("leaves the password step as it was when it isn't paying, and a failed cleanup with its error", async () => {
    m.verifyEntryCode.mockResolvedValue({ ok: true, signedUp: false, href: "/app/cuenta?next=%2Fapp%2Fsettings" });
    await expect(confirmAccountCode("/app/settings", {}, codeForm("123456"))).rejects.toThrow(/redirect:\/app\/cuenta\?next=%2Fapp%2Fsettings$/);
    m.verifyEntryCode.mockResolvedValue({ ok: true, signedUp: false, href: "/app/cuenta?next=%2Fapp%2Fpro%3Fplan%3Dpass_7&error=security" });
    await expect(confirmAccountCode("/app/pro?plan=pass_7", {}, codeForm("123456"))).rejects.toThrow(/error=security$/);
  });

  it("keeps the code box with its error", async () => {
    m.verifyEntryCode.mockResolvedValue({ ok: false, error: "El código no es correcto o venció." });
    expect(await confirmAccountCode("/app/pro?plan=pass_7", {}, codeForm("000000"))).toEqual({ sent: true, error: "El código no es correcto o venció." });
  });
});

describe("continuing to the payment with the code alone", () => {
  it("proves, closes the other sessions, completes with 'code', then opens the checkout", async () => {
    expect(await continueToPayment("/app/pro?plan=pass_7", "v1", 5000)).toEqual({ url: "https://mercadopago.example/checkout", error: undefined });
    expect(m.hasFreshProof).toHaveBeenCalledWith("user", "session");
    expect(m.signOut).toHaveBeenCalledWith({ scope: "others" });
    expect(m.rpc).toHaveBeenCalledWith("complete_email_only_account", { p_user: "user", p_session: "session", p_method: "code" });
    expect(m.startPayment).toHaveBeenCalledWith("pass_7", true, "v1", 5000);
    const order = [m.hasFreshProof, m.signOut, m.rpc, m.startPayment].map((fn) => fn.mock.invocationCallOrder[0]);
    expect(order).toEqual([...order].sort((a, b) => a - b));
    expect(m.updateUser).not.toHaveBeenCalled();
  });

  it("asks for a new code when this session has no fresh proof, before touching anyone", async () => {
    m.hasFreshProof.mockResolvedValue(false);
    expect(await continueToPayment("/app/pro?plan=pass_7", "v1", 5000)).toMatchObject({ expired: true });
    expect(m.signOut).not.toHaveBeenCalled();
    expect(m.rpc).not.toHaveBeenCalled();
    expect(m.startPayment).not.toHaveBeenCalled();
  });

  it("asks for a new code when the database finds the proof gone", async () => {
    m.rpc.mockResolvedValue({ data: null, error: { message: "proof_required" } });
    expect(await continueToPayment("/app/pro?plan=pass_7", "v1", 5000)).toMatchObject({ expired: true });
    expect(m.startPayment).not.toHaveBeenCalled();
  });

  it("falls back to the password on a database without the 'code' method", async () => {
    m.rpc.mockResolvedValue({ data: null, error: { message: "invalid_method" } });
    expect(await continueToPayment("/app/pro?plan=pass_7", "v1", 5000)).toEqual({ password: true });
    expect(m.startPayment).not.toHaveBeenCalled();
  });

  it("stops if the other sessions can't be closed, or the database fails", async () => {
    m.signOut.mockResolvedValue({ error: { message: "network" } });
    expect((await continueToPayment("/app/pro?plan=pass_7", "v1", 5000)).error).toBeTruthy();
    expect(m.rpc).not.toHaveBeenCalled();
    m.signOut.mockResolvedValue({ error: null });
    m.rpc.mockResolvedValue({ data: null, error: { message: "connection reset" } });
    const result = await continueToPayment("/app/pro?plan=pass_7", "v1", 5000);
    expect(result.error).toBeTruthy();
    expect(result.expired).toBeUndefined();
    expect(m.startPayment).not.toHaveBeenCalled();
  });

  it("only starts the payment for a full account", async () => {
    m.liveAccount.mockResolvedValue({ ...lite, emailOnly: false });
    expect((await continueToPayment("/app/pro?plan=pass_30", "v1", 15000)).url).toBe("https://mercadopago.example/checkout");
    expect(m.hasFreshProof).not.toHaveBeenCalled();
    expect(m.signOut).not.toHaveBeenCalled();
    expect(m.rpc).not.toHaveBeenCalled();
    expect(m.startPayment).toHaveBeenCalledWith("pass_30", true, "v1", 15000);
  });

  it("goes on to the founder link's own page, and to /app/pro with payments off", async () => {
    expect(await continueToPayment("/app/pro?plan=pro_monthly&fundador=abcdef12", "v1", 100000)).toEqual({ href: "/app/pro?plan=pro_monthly&fundador=abcdef12" });
    expect(m.rpc).toHaveBeenCalledWith("complete_email_only_account", expect.objectContaining({ p_method: "code" }));
    m.automaticPayments = false;
    expect(await continueToPayment("/app/pro?plan=pass_7", "v1", 5000)).toEqual({ href: "/app/pro?plan=pass_7" });
    expect(m.startPayment).not.toHaveBeenCalled();
  });

  it("never follows an external destination", async () => {
    expect(await continueToPayment("https://evil.example/app/pro?plan=pass_7", "v1", 5000)).toEqual({ href: "/app" });
    expect(await continueToPayment("//evil.example/app/pro?plan=pass_7", "v1", 5000)).toEqual({ href: "/app" });
    expect(m.startPayment).not.toHaveBeenCalled();
  });

  it("passes on a checkout error, and doesn't loop on a lagging profile read", async () => {
    m.startPayment.mockResolvedValue({ error: "La oferta cambió." });
    expect(await continueToPayment("/app/pro?plan=pass_7", "v1", 5000)).toEqual({ url: undefined, error: "La oferta cambió." });
    m.startPayment.mockResolvedValue({ needsAccount: true });
    const lagging = await continueToPayment("/app/pro?plan=pass_7", "v1", 5000);
    expect(lagging.error).toBeTruthy();
    expect(lagging.url).toBeUndefined();
  });

  it("refuses a revoked session", async () => {
    m.liveAccount.mockResolvedValue(null);
    expect((await continueToPayment("/app/pro?plan=pass_7", "v1", 5000)).error).toContain("venció");
    expect(m.rpc).not.toHaveBeenCalled();
  });
});

describe("the plan a destination pays", () => {
  it("is the offer of /app/pro?plan=<offer> and nothing else", () => {
    expect(payPlan("/app/pro?plan=pass_7")).toBe("pass_7");
    expect(payPlan("/app/pro?plan=pro_monthly&from=dashboard")).toBe("pro_monthly");
    expect(payPlan("/app/pro?plan=pro_monthly&fundador=abcdef12")).toBeNull();
    expect(payPlan("/app/pro?plan=custom")).toBeNull();
    expect(payPlan("/app/pro")).toBeNull();
    expect(payPlan("/app/settings?plan=pass_7")).toBeNull();
    expect(payPlan("/app/pro/x?plan=pass_7")).toBeNull();
  });
});
