import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ rpc: vi.fn() }));
vi.mock("@/lib/auth", () => ({ requireUser: vi.fn().mockResolvedValue({ id: "account" }) }));
vi.mock("@/lib/admin", () => ({ isAdmin: vi.fn().mockResolvedValue(false) }));
vi.mock("@/lib/health-auth", () => ({ canViewHealth: vi.fn().mockResolvedValue(false) }));
vi.mock("@/lib/supabase/server", () => ({ createClient: vi.fn().mockResolvedValue({ rpc: mocks.rpc }) }));
vi.mock("next/navigation", () => ({ usePathname: () => "/app" }));

import AppLayout from "@/app/app/layout";
import type { PlanLimits } from "@/lib/pro";

beforeEach(() => vi.clearAllMocks());

async function renderNavigation(access: PlanLimits | null, error: unknown = null) {
  mocks.rpc.mockResolvedValue({ data: access, error });
  const layout = await AppLayout({ children: createElement("p", null, "Mis búsquedas"), params: Promise.resolve({}) });
  return renderToStaticMarkup(layout);
}

it.each(["pass", "pro"] as const)("hides desktop and mobile purchase links for active %s access", async (plan) => {
  const html = await renderNavigation({ plan, enforced: true, active: true, state: "paid", limits: {} });
  expect(html).not.toContain("Adquirir plan");
  expect(html).not.toContain('href="/app/pro"');
  expect(html).toContain("Nueva búsqueda");
  expect(html).toContain('href="/app/settings"');
  expect(mocks.rpc).toHaveBeenCalledWith("my_plan_snapshot");
});

it.each(["trial", "expired"] as const)("retains desktop and mobile purchase links for free %s access", async (state) => {
  const html = await renderNavigation({ plan: "free", enforced: true, active: state === "trial", state, limits: {} });
  expect(html.match(/Adquirir plan/g)).toHaveLength(2);
});

it("doesn't show a purchase offer when the plan lookup fails", async () => {
  const html = await renderNavigation(null, { message: "Could not read access" });
  expect(html).not.toContain("Adquirir plan");
  expect(html).toContain("Mis búsquedas");
});
