import { beforeEach, describe, expect, it, vi } from "vitest";

const m = vi.hoisted(() => ({
  liveAccount: vi.fn(), sendEntryLink: vi.fn(), rpc: vi.fn(), updateUser: vi.fn(), signOut: vi.fn(),
}));
vi.mock("@/lib/auth", () => ({ liveAccount: m.liveAccount }));
vi.mock("@/lib/email-only", () => ({ sendEntryLink: m.sendEntryLink, linkError: () => "Ya te mandamos un link hace un momento." }));
vi.mock("@/lib/supabase/admin", () => ({ createAdminClient: () => ({ rpc: m.rpc }) }));
vi.mock("@/lib/supabase/server", () => ({ createClient: async () => ({ auth: { updateUser: m.updateUser, signOut: m.signOut } }) }));
vi.mock("next/navigation", () => ({ redirect: (path: string) => { throw new Error(`redirect:${path}`); } }));

import { completeAccount, sendAccountLink } from "@/app/app/cuenta/actions";

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
