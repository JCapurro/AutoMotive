import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/admin", () => ({ requireAdmin: vi.fn() }));
vi.mock("@/lib/admin-dashboard-data", () => ({ loadAdminDashboard: vi.fn() }));
vi.mock("@/lib/supabase/admin", () => ({ createAdminClient: vi.fn() }));

import AdminHome from "@/app/admin/page";
import DiagnosticPage from "@/app/admin/metrics/diagnostic/page";
import MetricsPage from "@/app/admin/metrics/page";
import { requireAdmin } from "@/lib/admin";
import { loadAdminDashboard } from "@/lib/admin-dashboard-data";
import { createAdminClient } from "@/lib/supabase/admin";

describe("admin decision pages authorization", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(requireAdmin).mockRejectedValue(new Error("admin_required"));
  });

  const pages = [
    { name: "Resumen", render: () => AdminHome({ params: Promise.resolve({}), searchParams: Promise.resolve({}) }) },
    { name: "Métricas", render: () => MetricsPage({ params: Promise.resolve({}), searchParams: Promise.resolve({ view: "operation" }) }) },
    { name: "Diagnóstico", render: () => DiagnosticPage() },
  ];
  it.each(pages)("$name refuses to read service-role data before authorization", async ({ render }) => {
    await expect(render()).rejects.toThrow("admin_required");
    expect(loadAdminDashboard).not.toHaveBeenCalled();
    expect(createAdminClient).not.toHaveBeenCalled();
  });
});
