import { describe, expect, it } from "vitest";

import { type FunnelCounts, funnelSteps, parseAdminFunnel, parseReach, rateText, reachSentence, saleErrorText, salesSentence, stepRate } from "@/lib/dealer-funnel";

const counts: FunnelCounts = {
  stock: 10, visible: 8, loaded: 4, matched_cars: 6, matched_searches: 9, alerts: 14, alerted_cars: 3, people: 12,
  leads: 3, contacted: 2, reserved: 1, sold: 1, lost: 1, still_new: 1, sales_via_ese_auto: 1, sales_elsewhere: 1,
};

describe("funnelSteps", () => {
  it("chains the rates in the same unit", () => {
    const steps = Object.fromEntries(funnelSteps(counts).map((s) => [s.key, s]));
    expect(steps.stock.rate).toBeNull();
    expect(steps.visible.rate).toBe(80);
    expect(steps.matched.rate).toBe(75);
    expect(steps.alerted.rate).toBe(50);
    expect(steps.people.rate).toBeNull();
    expect(steps.leads.rate).toBe(25);
    expect(steps.contacted.rate).toBeCloseTo(66.67, 1);
    expect(steps.reserved.rate).toBe(50);
    expect(steps.sold.rate).toBe(100);
    expect(steps.sales.rate).toBe(50);
    expect(steps.alerted.hint).toContain("14 alertas enviadas");
  });

  it("has no rate without a denominator", () => {
    const zero = Object.fromEntries(Object.keys(counts).map((k) => [k, 0])) as FunnelCounts;
    expect(funnelSteps(zero).every((s) => s.rate === null)).toBe(true);
    expect(rateText(null)).toBe("—");
    expect(rateText(stepRate(1, 300))).toBe("<1 %");
    expect(rateText(stepRate(2, 3))).toBe("67 %");
  });
});

describe("parseAdminFunnel", () => {
  it("accepts the RPC's shape and rejects anything else", () => {
    const raw = { start: "2026-10-20T03:00:00Z", end: "2026-11-19T03:00:00Z", total: counts,
      dealers: [{ ...counts, dealer_id: 1, name: "TT", approved: true, status: "active" }] };
    expect(parseAdminFunnel(raw)?.dealers[0].name).toBe("TT");
    expect(parseAdminFunnel({ ...raw, total: { ...counts, people: -1 } })).toBeNull();
    expect(parseAdminFunnel(null)).toBeNull();
  });
});

describe("the agency's month", () => {
  const base = { since: "2026-11-01T03:00:00Z", min_count: 3, leads: 3, sales_via_ese_auto: 0, pending_sales: [] };

  it("says the reach and the leads", () => {
    expect(reachSentence({ people: 12, leads: 3 })).toBe("Este mes tus autos llegaron a 12 personas y recibiste 3 consultas.");
    expect(reachSentence({ people: 12, leads: 1 })).toBe("Este mes tus autos llegaron a 12 personas y recibiste 1 consulta.");
    expect(reachSentence({ people: "few", leads: 0 })).toBe("Este mes tus autos llegaron a pocas personas. Todavía no recibiste consultas.");
    expect(reachSentence({ people: 0, leads: 0 })).toBe("Este mes tus autos todavía no llegaron a ningún comprador.");
    expect(reachSentence({ people: 0, leads: 2 })).toBe("Este mes recibiste 2 consultas.");
  });

  it("never prints 1 or 2 people", () => {
    expect(parseReach({ ...base, people: 2 })?.people).toBe("few");
    expect(parseReach({ ...base, people: 1 })?.people).toBe("few");
    expect(parseReach({ ...base, people: 4, min_count: 5 })?.people).toBe("few");
    expect(parseReach({ ...base, people: 3 })?.people).toBe(3);
    expect(parseReach({ ...base, people: 0 })?.people).toBe(0);
    expect(parseReach({ ...base, people: "few" })?.people).toBe("few");
    expect(parseReach({ ...base, people: "2" })).toBeNull();
    for (const n of [1, 2]) expect(reachSentence(parseReach({ ...base, people: n })!)).not.toMatch(/\b[12] personas/);
  });

  it("reads the pending sales", () => {
    const r = parseReach({ ...base, people: 3, pending_sales: [{ item_id: 5, lead_id: null, vehicle: "Ford Focus 2017", sold_at: "2026-11-18T12:00:00Z" }] });
    expect(r?.pending_sales[0].vehicle).toBe("Ford Focus 2017");
  });

  it("says the declared sales and the errors", () => {
    expect(salesSentence(0)).toBeNull();
    expect(salesSentence(1)).toBe("1 venta vino por Ese Auto.");
    expect(salesSentence(3)).toBe("3 ventas vinieron por Ese Auto.");
    expect(saleErrorText("not_sold")).toBe("Primero marcalo como vendido.");
    expect(saleErrorText("lead_not_found")).toBe("No encontramos esa consulta.");
    expect(saleErrorText("boom")).toBe("No pudimos guardar. Probá de nuevo.");
  });
});
