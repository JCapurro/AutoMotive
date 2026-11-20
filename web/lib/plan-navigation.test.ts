import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ rpc: vi.fn(), config: { dealerProgram: { enabled: false } } as Record<string, unknown>, myDealer: vi.fn() }));
vi.mock("@/lib/auth", () => ({ requireUser: vi.fn().mockResolvedValue({ id: "account" }) }));
vi.mock("@/lib/admin", () => ({ isAdmin: vi.fn().mockResolvedValue(false) }));
vi.mock("@/lib/health-auth", () => ({ canViewHealth: vi.fn().mockResolvedValue(false) }));
vi.mock("@/lib/supabase/server", () => ({ createClient: vi.fn().mockResolvedValue({ rpc: mocks.rpc }) }));
vi.mock("next/navigation", () => ({ usePathname: () => "/app" }));
vi.mock("@/lib/config", () => ({ webConfig: async () => mocks.config }));
vi.mock("@/lib/dealer-server", () => ({ myDealer: mocks.myDealer }));

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
  expect(html).not.toContain(">Planes</a>");
  expect(html).not.toContain('href="/app/pro"');
  expect(html).toContain("Nueva búsqueda");
  // Ajustes moved into the account menu (04/11), which renders its items only when opened.
  expect(html).toContain('aria-label="Tu cuenta"');
  expect(mocks.rpc).toHaveBeenCalledWith("my_plan_snapshot");
});

it.each(["trial", "expired"] as const)("retains desktop and mobile purchase links for free %s access", async (state) => {
  const html = await renderNavigation({ plan: "free", enforced: true, active: state === "trial", state, limits: {} });
  expect(html.match(/>Planes<\/a>/g)).toHaveLength(2);
});

it("doesn't show a purchase offer when the plan lookup fails", async () => {
  const html = await renderNavigation(null, { message: "Could not read access" });
  expect(html).not.toContain(">Planes</a>");
  expect(html).toContain("Mis búsquedas");
});

it("shows «Mi agencia» only with the panel on and an agency of one's own (agencias)", async () => {
  mocks.config = { dealerProgram: { enabled: false } };
  let html = await renderNavigation(null);
  expect(html).not.toContain('href="/agencia"');
  expect(mocks.myDealer).not.toHaveBeenCalled();

  mocks.config = { dealerProgram: { enabled: true } };
  mocks.myDealer.mockResolvedValueOnce(null);
  html = await renderNavigation(null);
  expect(html).not.toContain('href="/agencia"');

  mocks.myDealer.mockResolvedValueOnce({ id: 1, name: "Autos Sur" });
  html = await renderNavigation(null);
  expect(html).toContain('href="/agencia"');
  mocks.config = { dealerProgram: { enabled: false } };
});
