import { beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

const mocks = vi.hoisted(() => ({ getUser: vi.fn(), getClaims: vi.fn(), currentUser: vi.fn(), admin: vi.fn() }));
vi.mock("server-only", () => ({}));
vi.mock("@/lib/auth", () => ({ currentUser: mocks.currentUser }));
vi.mock("@/lib/supabase/server", () => ({ createClient: async () => ({ auth: { getUser: mocks.getUser } }) }));
vi.mock("@/lib/supabase/admin", () => ({ createAdminClient: mocks.admin }));
vi.mock("@supabase/ssr", () => ({ createServerClient: () => ({ auth: { getUser: mocks.getUser, getClaims: mocks.getClaims } }) }));
vi.mock("next/navigation", () => ({ notFound: () => { throw Error("not-found"); }, redirect: (path: string) => { throw Error(`redirect:${path}`); } }));
import { HEALTH_OWNER_EMAIL, isHealthOwner } from "./health-access";
import { canViewHealth } from "./health-auth";
import HealthPage from "@/app/app/health/page";
import { proxy } from "@/proxy";

const owner = { id: "owner", email: HEALTH_OWNER_EMAIL, email_confirmed_at: "2026-10-01T00:00:00Z" };
beforeEach(() => {
  vi.clearAllMocks();
  mocks.currentUser.mockResolvedValue(owner);
  mocks.getUser.mockResolvedValue({ data: { user: owner }, error: null });
  mocks.getClaims.mockResolvedValue({ data: { claims: { sub: "owner", email: HEALTH_OWNER_EMAIL } } });
});

describe("private health access", () => {
  it("allows only the verified exact email", () => {
    expect(isHealthOwner(owner)).toBe(true);
    expect(isHealthOwner({ ...owner, email: "JCapurro97@gmail.com" })).toBe(true);
    expect(isHealthOwner({ ...owner, email: "jcapurro97+other@gmail.com" })).toBe(false);
    expect(isHealthOwner({ ...owner, email: "other@example.test" })).toBe(false);
    expect(isHealthOwner({ ...owner, email_confirmed_at: null })).toBe(false);
    expect(isHealthOwner(null)).toBe(false);
  });
  it("authorizes the owner using the fresh server-verified user", async () => {
    expect(await canViewHealth()).toBe(true);
    expect(mocks.getUser).toHaveBeenCalledOnce();
  });
  it("never creates a privileged client for another user, including an admin", async () => {
    mocks.currentUser.mockResolvedValue({ id: "admin", email: "admin@example.test", role: "admin" });
    await expect(HealthPage()).rejects.toThrow("not-found");
    expect(mocks.admin).not.toHaveBeenCalled();
  });
  it("never reads health data for anonymous users", async () => {
    mocks.currentUser.mockResolvedValue(null);
    await expect(HealthPage()).rejects.toThrow("redirect:/login?next=/app/health");
    expect(mocks.admin).not.toHaveBeenCalled();
  });
  it("denies stale claims after the account email changes", async () => {
    mocks.getUser.mockResolvedValue({ data: { user: { ...owner, email: "other@example.test" } }, error: null });
    expect(await canViewHealth()).toBe(false);
    await expect(HealthPage()).rejects.toThrow("not-found");
    expect(mocks.admin).not.toHaveBeenCalled();
  });
  it("returns 404 for another verified user even with owner claims", async () => {
    mocks.getUser.mockResolvedValue({ data: { user: { ...owner, email: "other@example.test" } }, error: null });
    const response = await proxy(new NextRequest("https://www.eseauto.com.ar/app/health"));
    expect(response.status).toBe(404);
    expect(await response.text()).toBe("Not found");
  });
  it("denies unconfirmed email and auth validation failures", async () => {
    for (const result of [{ data: { user: { ...owner, email_confirmed_at: null } }, error: null }, { data: { user: owner }, error: { message: "invalid session" } }]) {
      mocks.getUser.mockResolvedValue(result);
      expect((await proxy(new NextRequest("https://www.eseauto.com.ar/app/health"))).status).toBe(404);
    }
  });
  it("lets the verified owner through the proxy", async () => {
    expect((await proxy(new NextRequest("https://www.eseauto.com.ar/app/health"))).status).toBe(200);
  });
  it("redirects anonymous visitors to login", async () => {
    mocks.getClaims.mockResolvedValue({ data: { claims: null } });
    const response = await proxy(new NextRequest("https://www.eseauto.com.ar/app/health"));
    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toContain("/login?next=%2Fapp%2Fhealth");
  });
});
