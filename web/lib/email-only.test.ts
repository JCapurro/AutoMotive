import { beforeEach, describe, expect, it, vi } from "vitest";

const m = vi.hoisted(() => ({ rpc: vi.fn(), resetPasswordForEmail: vi.fn(), headers: {} as Record<string, string> }));
vi.mock("server-only", () => ({}));
vi.mock("next/headers", () => ({ headers: async () => new Headers(m.headers) }));
vi.mock("@/lib/config", () => ({
  webConfig: async () => ({ emailOnlySignup: { enabled: true, perIpHour: 10, perDay: 100, linksPerUserHour: 3, linksPerIpHour: 20, lookupsPerIpHour: 30 } }),
}));
vi.mock("@/lib/supabase/admin", () => ({ createAdminClient: () => ({ rpc: m.rpc }) }));
vi.mock("@/lib/supabase/server", () => ({ createClient: async () => ({ auth: { resetPasswordForEmail: m.resetPasswordForEmail } }) }));

import { clientIpKey, ipBucket, sendEntryLink } from "@/lib/email-only";

const throttles = () => m.rpc.mock.calls.filter(([name]) => name === "claim_auth_throttle").map(([, args]) => args.p_kind);

beforeEach(() => {
  vi.resetAllMocks();
  vi.stubEnv("SITE_URL", "https://eseauto.com.ar");
  m.headers = { "x-real-ip": "203.0.113.7" };
  m.rpc.mockImplementation(async (name: string) => name === "claim_auth_throttle"
    ? { data: true, error: null }
    : { data: [{ user_id: "lite", email_only: true, confirmed: true }], error: null });
  m.resetPasswordForEmail.mockResolvedValue({ error: null });
});

describe("the IP key", () => {
  it("buckets IPv6 by /64 and unwraps IPv4-mapped addresses", () => {
    expect(ipBucket("2001:db8:1:2:3:4:5:6")).toBe("2001:db8:1:2::/64");
    expect(ipBucket("2001:db8:1:2::9")).toBe("2001:db8:1:2::/64");
    expect(ipBucket("2001:db8::1")).toBe("2001:db8:0:0::/64");
    expect(ipBucket("::ffff:198.51.100.4")).toBe("198.51.100.4");
    expect(ipBucket("198.51.100.4")).toBe("198.51.100.4");
  });

  it("is a hash, never the address", async () => {
    const key = await clientIpKey();
    expect(key).toMatch(/^[0-9a-f]{32}$/);
    expect(key).not.toContain("203.0.113.7");
    m.headers = {};
    expect(await clientIpKey()).toBe("unknown");
  });
});

describe("the link to enter", () => {
  it("is the recovery email, carrying the destination through the password step", async () => {
    expect(await sendEntryLink("persona@example.com", "/app/pro?plan=pass_30")).toBe("sent");
    const redirectTo = new URL(m.resetPasswordForEmail.mock.calls[0][1].redirectTo);
    expect(redirectTo.origin + redirectTo.pathname).toBe("https://eseauto.com.ar/auth/callback");
    expect(redirectTo.searchParams.get("next")).toBe("/auth/reset-password?next=%2Fapp%2Fpro%3Fplan%3Dpass_30");
    expect(throttles()).toEqual(["entry_link_ip", "entry_link_user"]);
    const user = m.rpc.mock.calls.find(([, args]) => args?.p_kind === "entry_link_user")?.[1];
    expect(user).toMatchObject({ p_key: "lite", p_limit: 3, p_window_seconds: 3600 });
  });

  it("sends nothing for an email without an account, and says the same", async () => {
    m.rpc.mockImplementation(async (name: string) => name === "claim_auth_throttle" ? { data: true, error: null } : { data: [], error: null });
    expect(await sendEntryLink("nadie@example.com", "/app")).toBe("sent");
    expect(m.resetPasswordForEmail).not.toHaveBeenCalled();
  });

  it("stops past the per-IP or per-account brake", async () => {
    m.rpc.mockImplementation(async (name: string, args: { p_kind?: string }) => name === "claim_auth_throttle"
      ? { data: args.p_kind !== "entry_link_user", error: null }
      : { data: [{ user_id: "lite", email_only: true, confirmed: true }], error: null });
    expect(await sendEntryLink("persona@example.com", "/app")).toBe("throttled");
    expect(m.resetPasswordForEmail).not.toHaveBeenCalled();
  });

  it("still sends when the brakes can't be read (Auth's own per-email limit remains)", async () => {
    m.rpc.mockResolvedValue({ data: null, error: { message: "connection reset" } });
    expect(await sendEntryLink("persona@example.com", "/app")).toBe("sent");
    expect(m.resetPasswordForEmail).toHaveBeenCalledOnce();
  });

  it("reports Auth's per-email cooldown as busy", async () => {
    m.resetPasswordForEmail.mockResolvedValue({ error: { status: 429 } });
    expect(await sendEntryLink("persona@example.com", "/app", { user_id: "lite", email_only: true, confirmed: true })).toBe("busy");
  });

  it("never carries an external destination", async () => {
    await sendEntryLink("persona@example.com", "//evil.example", { user_id: "lite", email_only: true, confirmed: true });
    const redirectTo = new URL(m.resetPasswordForEmail.mock.calls[0][1].redirectTo);
    expect(redirectTo.searchParams.get("next")).toBe("/auth/reset-password?next=%2Fapp");
  });
});
