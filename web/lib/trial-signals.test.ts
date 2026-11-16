import { beforeEach, describe, expect, it, vi } from "vitest";

const m = vi.hoisted(() => ({ rpc: vi.fn(), get: vi.fn(), set: vi.fn() }));
vi.mock("server-only", () => ({}));
vi.mock("next/headers", () => ({ cookies: async () => ({ get: m.get, set: m.set }) }));
vi.mock("@/lib/supabase/admin", () => ({ createAdminClient: () => ({ rpc: m.rpc }) }));

import { accountForCanonicalEmail, DEVICE_COOKIE, deviceKey, recordTrialSignals } from "@/lib/trial-signals";

const id = "0f8b6c1e-2a3d-4e5f-8a9b-0c1d2e3f4a5b";

beforeEach(() => {
  vi.resetAllMocks();
  m.rpc.mockResolvedValue({ data: null, error: null });
});

describe("deviceKey", () => {
  it("hashes the browser's id, the same every time, without setting it again", async () => {
    m.get.mockReturnValue({ value: id });
    const key = await deviceKey();
    expect(key).toMatch(/^[0-9a-f]{32}$/);
    expect(await deviceKey()).toBe(key);
    expect(key).not.toContain(id.slice(0, 8));
    expect(m.set).not.toHaveBeenCalled();
  });

  it("mints a long-lived httpOnly cookie the first time (or over a tampered one)", async () => {
    m.get.mockReturnValue({ value: "not-an-id" });
    expect(await deviceKey()).toMatch(/^[0-9a-f]{32}$/);
    expect(m.set).toHaveBeenCalledWith(DEVICE_COOKIE, expect.stringMatching(/^[0-9a-f-]{36}$/),
      expect.objectContaining({ httpOnly: true, secure: true, maxAge: 2 * 365 * 86400 }));
  });

  it("is null when cookies can't be written here", async () => {
    m.get.mockReturnValue(undefined);
    m.set.mockImplementation(() => { throw new Error("read-only"); });
    expect(await deviceKey()).toBeNull();
  });
});

describe("recordTrialSignals", () => {
  it("saves the account's email, IP key and device key", async () => {
    m.get.mockReturnValue({ value: id });
    await recordTrialSignals("u1", "a@example.com", "ip-key");
    expect(m.rpc).toHaveBeenCalledWith("record_trial_signals", {
      p_user: "u1", p_email: "a@example.com", p_ip_key: "ip-key", p_device_key: expect.stringMatching(/^[0-9a-f]{32}$/),
    });
  });

  it("never breaks a signup", async () => {
    m.rpc.mockRejectedValue(new Error("down"));
    await expect(recordTrialSignals("u1", "a@example.com", "ip-key")).resolves.toBeUndefined();
  });
});

describe("accountForCanonicalEmail", () => {
  it("returns the account of another spelling, or null (also when the lookup fails)", async () => {
    m.rpc.mockResolvedValueOnce({ data: [{ user_id: "u1", email: "juanperez@gmail.com", email_only: true, confirmed: true }], error: null });
    expect(await accountForCanonicalEmail("juan.perez@gmail.com")).toEqual({ user_id: "u1", email: "juanperez@gmail.com", email_only: true, confirmed: true });
    m.rpc.mockResolvedValueOnce({ data: [], error: null });
    expect(await accountForCanonicalEmail("x@example.com")).toBeNull();
    m.rpc.mockResolvedValueOnce({ data: null, error: { message: "missing function" } });
    expect(await accountForCanonicalEmail("x@example.com")).toBeNull();
  });
});
