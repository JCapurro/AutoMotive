import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ users: vi.fn(), searches: vi.fn(), requireAdmin: vi.fn(), admin: vi.fn() }));
vi.mock("server-only", () => ({}));
vi.mock("@/lib/admin", () => ({ requireAdmin: mocks.requireAdmin }));
vi.mock("@/lib/supabase/admin", () => ({ createAdminClient: mocks.admin }));
vi.mock("@/lib/admin-load", () => ({ loadUsersInput: mocks.users, loadSearchesInput: mocks.searches }));
vi.mock("next/navigation", () => ({ notFound: () => { throw Error("not-found"); }, usePathname: () => "/admin/users" }));

import UsersPage from "@/app/admin/users/page";
import AdminUserPage from "@/app/admin/users/[id]/page";
import SearchesPage from "@/app/admin/searches/page";

const recent = new Date(Date.now() - 2 * 86_400_000).toISOString();
const props = (searchParams: Record<string, string> = {}) => ({ params: Promise.resolve({}), searchParams: Promise.resolve(searchParams) });

beforeEach(() => {
  vi.resetAllMocks();
  mocks.users.mockResolvedValue({
    users: [{ id: "u1", email: "ana@x.test", plan: "free", plan_expires_at: null, role: "user", created_at: recent, telegram_linked: false, email_only: true, searches: 1, enabled_searches: 1, waitlist_plan: null }],
    events: [{ user_id: "u1", name: "signup_completed", props: { method: "email_only", origin: { source: "facebook", medium: "paid", landing: "/", campaign: "v3" } }, created_at: recent }],
    notifications: [],
    payments: [],
  });
  mocks.searches.mockResolvedValue({
    searches: [{ id: 7, user_id: "u1", email: "ana@x.test", name: "Golf", filters: { make: "Volkswagen", model: "Golf", currency: "USD", price_max: 12000 }, enabled: true,
      notification_frequency: "immediate", notify_min_level: "good", channels: ["email"], bootstrapped_at: recent, rematch_requested_at: null, created_at: recent, matches: 0, high_matches: 0, alerts: 0, radius_km: 30 }],
    notifications: [],
  });
});

describe("Usuarios and Búsquedas dashboards", () => {
  it("renders where users come from and what they did", async () => {
    const html = renderToStaticMarkup(await UsersPage(props({ canal: "meta_ads" }) as never));
    expect(html).toContain("De dónde vienen");
    expect(html).toContain("Anuncio Meta");
    expect(html).toContain("facebook / paid / v3");
    expect(html).toContain('href="/admin/users/u1"');
  });

  it("renders what people look for and flags searches without results", async () => {
    const html = renderToStaticMarkup(await SearchesPage(props({ vista: "sin-resultados" }) as never));
    expect(html).toContain("Volkswagen Golf");
    expect(html).toContain("USD 8.000–12.000");
    expect(html).toContain("sin resultados");
  });

  it("shows a notice, not a 500, when the searches read times out", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    mocks.searches.mockRejectedValue(new Error("admin read failed: canceling statement due to statement timeout"));
    const html = renderToStaticMarkup(await SearchesPage(props() as never));
    expect(html).toContain("No se pudieron leer las búsquedas");
  });

  it("still lets the admin check's errors through on the searches page", async () => {
    mocks.searches.mockRejectedValue(new Error("admin_required"));
    await expect(SearchesPage(props() as never)).rejects.toThrow("admin_required");
  });

  it("refuses a user page with a malformed id before reading anything", async () => {
    await expect(AdminUserPage({ params: Promise.resolve({ id: "1 or 1=1" }) } as never)).rejects.toThrow("not-found");
    expect(mocks.admin).not.toHaveBeenCalled();
  });

  it("checks admin before the user page reads with the service role", async () => {
    mocks.requireAdmin.mockRejectedValue(new Error("admin_required"));
    await expect(AdminUserPage({ params: Promise.resolve({ id: "00000000-0000-0000-0000-000000000000" }) } as never)).rejects.toThrow("admin_required");
    expect(mocks.admin).not.toHaveBeenCalled();
  });
});
