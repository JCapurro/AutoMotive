import { describe, expect, it } from "vitest";

import { ADMIN_AREAS, resolveAdminNav } from "@/components/admin/admin-nav";

const at = (pathname: string, view?: string) => {
  const r = resolveAdminNav(pathname, view);
  return r ? `${r.area.id}:${r.page.href}` : null;
};

describe("admin menu structure", () => {
  it("has the six areas and no page twice", () => {
    expect(ADMIN_AREAS.map((a) => a.id)).toEqual(["hoy", "crecimiento", "calidad", "ingresos", "operacion", "herramientas"]);
    const hrefs = ADMIN_AREAS.flatMap((a) => a.pages.map((p) => p.href));
    expect(new Set(hrefs).size).toBe(hrefs.length);
    expect(hrefs).toHaveLength(16);
  });
});

describe("resolveAdminNav", () => {
  it("resolves plain pages to their area", () => {
    expect(at("/admin")).toBe("hoy:/admin");
    expect(at("/admin/users")).toBe("crecimiento:/admin/users");
    expect(at("/admin/matches")).toBe("calidad:/admin/matches");
    expect(at("/admin/billing")).toBe("ingresos:/admin/billing");
    expect(at("/admin/config")).toBe("herramientas:/admin/config");
  });

  it("keeps the parent highlighted on detail pages", () => {
    expect(at("/admin/users/abc-123")).toBe("crecimiento:/admin/users");
    expect(at("/admin/matches/42")).toBe("calidad:/admin/matches");
    expect(at("/admin/searches/7/")).toBe("calidad:/admin/searches");
  });

  it("does not treat every /admin/* page as Hoy", () => {
    expect(at("/admin/unknown")).toBeNull();
  });

  it("picks the metrics view from the view param, defaulting to activation", () => {
    expect(at("/admin/metrics", "revenue")).toBe("ingresos:/admin/metrics?view=revenue");
    expect(at("/admin/metrics", "operation")).toBe("operacion:/admin/metrics?view=operation");
    expect(at("/admin/metrics", "activation")).toBe("crecimiento:/admin/metrics?view=activation");
    expect(at("/admin/metrics")).toBe("crecimiento:/admin/metrics?view=activation");
    expect(at("/admin/metrics", "nonsense")).toBe("crecimiento:/admin/metrics?view=activation");
  });

  it("keeps the diagnostic page out of the metrics views", () => {
    expect(at("/admin/metrics/diagnostic")).toBe("herramientas:/admin/metrics/diagnostic");
    expect(at("/admin/metrics/diagnostic", "revenue")).toBe("herramientas:/admin/metrics/diagnostic");
  });
});
