import { describe, expect, it } from "vitest";

import { dealerPageFor, dealerPages } from "@/components/agencia/dealer-nav";

import {
  budgetText, buyMarketHref, demandLine, isOpportunity, parseBuyMarketQuery, parseBuyOpportunities, parseDealerSellers,
  parseSellers, requestStatusText, sellerCarText, sellerErrorText, supplyText, yearsText,
} from "@/lib/dealer-buying";

const row = {
  make: "Toyota", model: "Etios", searches: 4, active_searches: 4, year_from: 2018, year_to: 2020,
  budget: 14500000, budget_currency: "ARS", supply_total: 2, supply_near: 1,
};

describe("dealer_program sellers keys", () => {
  it("is off unless enabled and sellers_enabled are both true", () => {
    expect(parseDealerSellers(null)).toEqual({ sellersEnabled: false, requestsPerDay: 5 });
    expect(parseDealerSellers({ sellers_enabled: true })).toEqual({ sellersEnabled: false, requestsPerDay: 5 });
    expect(parseDealerSellers({ enabled: true, sellers_enabled: "true" }).sellersEnabled).toBe(false);
    expect(parseDealerSellers({ enabled: true, sellers_enabled: true, seller_requests_per_day: 12 })).toEqual({ sellersEnabled: true, requestsPerDay: 12 });
    expect(parseDealerSellers({ enabled: true, sellers_enabled: true, seller_requests_per_day: 0 }).requestsPerDay).toBe(5);
    expect(parseDealerSellers({ enabled: true, sellers_enabled: true, seller_requests_per_day: 51 }).requestsPerDay).toBe(5);
  });
});

describe("Qué comprar", () => {
  it("reads the rows and drops anything under 3 searches or malformed", () => {
    const [o, ...rest] = parseBuyOpportunities([row, { ...row, searches: 2 }, { ...row, model: "" }, null, "x"]);
    expect(rest).toEqual([]);
    expect(o).toEqual({
      make: "Toyota", model: "Etios", searches: 4, activeSearches: 4, yearFrom: 2018, yearTo: 2020,
      budget: 14500000, budgetCurrency: "ARS", supplyTotal: 2, supplyNear: 1,
    });
    expect(parseBuyOpportunities({})).toEqual([]);
  });

  it("never shows 1 or 2 active searches, even if a number comes", () => {
    for (const v of [1, 2, "few"]) {
      const [o] = parseBuyOpportunities([{ ...row, active_searches: v }]);
      expect(o.activeSearches).toBe("few");
      expect(demandLine(o)).toBe("4 búsquedas · pocas activas");
    }
    const [none] = parseBuyOpportunities([{ ...row, active_searches: 0 }]);
    expect(demandLine(none)).toBe("4 búsquedas · ninguna activa");
    const [o] = parseBuyOpportunities([row]);
    expect(demandLine(o)).toBe("4 búsquedas · 4 activas");
  });

  it("puts years, budget and supply in words", () => {
    expect(yearsText(2018, 2020)).toBe("2018 a 2020");
    expect(yearsText(2019, 2019)).toBe("2019");
    expect(yearsText(2015, null)).toBe("desde 2015");
    expect(yearsText(null, 2012)).toBe("hasta 2012");
    expect(yearsText(null, null)).toBe("cualquier año");
    expect(budgetText(14500000, "ARS")).toBe("hasta $ 14.500.000");
    expect(budgetText(9500, "USD")).toBe("hasta USD 9.500");
    expect(budgetText(null, null)).toBe("sin presupuesto claro");
    expect(parseBuyOpportunities([{ ...row, budget: 0 }])[0].budgetCurrency).toBeNull();
    expect(supplyText(0, 0)).toBe("Ningún aviso publicado");
    expect(supplyText(1, 0)).toBe("1 aviso publicado · ninguno a menos de 50 km");
    expect(supplyText(1200, 30)).toBe("1.200 avisos publicados · 30 a menos de 50 km");
  });

  it("calls it an opportunity when there are fewer listings than searches", () => {
    const [o] = parseBuyOpportunities([row]);
    expect(isOpportunity(o)).toBe(true);
    expect(isOpportunity({ ...o, supplyTotal: 4 })).toBe(false);
  });

  it("links to the market and reads the link back", () => {
    const href = buyMarketHref({ make: "Toyota", model: "Etios", yearFrom: 2018, yearTo: 2020 });
    expect(href).toBe("/agencia/comprar/mercado?modelo=Etios&marca=Toyota&desde=2018&hasta=2020");
    const q = Object.fromEntries(new URL(href, "https://x.test").searchParams);
    expect(parseBuyMarketQuery(q)).toEqual({ make: "Toyota", model: "Etios", yearFrom: 2018, yearTo: 2020 });
    expect(parseBuyMarketQuery({ modelo: "Ka", desde: "20x8", hasta: "1900" })).toEqual({ make: null, model: "Ka", yearFrom: null, yearTo: null });
    expect(parseBuyMarketQuery({ marca: "Ford" })).toBeNull();
    expect(parseBuyMarketQuery({ modelo: "x".repeat(61) })).toBeNull();
  });
});

describe("vendedores", () => {
  const seller = {
    ref: "a74155a8c4f54ac7af616fa1b2548046", make: "Fiat", model: "Palio", year: 2012, mileage_km_rounded: 85000,
    distance_band: "lt10", recent: true, request_id: null, request_status: null, requested_on: null,
    shared_name: null, shared_phone: null, shared_email: null, can_request: true,
  };

  it("reads the rows; a bad ref is dropped", () => {
    const rows = parseSellers([seller, { ...seller, ref: "d3000000-0000-0000-0000-000000000011" }, null]);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({ distance: "lt10", canRequest: true, requestStatus: null });
    expect(parseSellers([{ ...seller, distance_band: "2km" }])[0].distance).toBe("unknown");
  });

  it("keeps the contact only for an accepted request", () => {
    const shared = { shared_name: "Sergio", shared_phone: "1155556666", shared_email: "s@x.test", request_id: 7 };
    expect(parseSellers([{ ...seller, ...shared, request_status: "pending" }])[0]).toMatchObject({ sharedName: null, sharedPhone: null, sharedEmail: null, canRequest: false });
    expect(parseSellers([{ ...seller, ...shared, request_status: "accepted" }])[0]).toMatchObject({ sharedName: "Sergio", sharedPhone: "1155556666", sharedEmail: "s@x.test" });
  });

  it("says what car and what happened, in words", () => {
    expect(sellerCarText({ make: "Fiat", model: "Palio", year: 2012, mileageKm: 85000 })).toBe("Fiat Palio 2012 · unos 85.000 km");
    expect(sellerCarText({ make: null, model: null, year: null, mileageKm: null })).toBe("Todavía no nos dijo qué auto vende");
    expect(requestStatusText("pending")).toBe("Le avisamos que querés contactarlo. Decide el vendedor.");
    expect(requestStatusText(null)).toBeNull();
    expect(sellerErrorText("rate_limited")).toBe("Llegaste al tope de pedidos de hoy. Probá mañana.");
    expect(sellerErrorText("duplicate key <secret>")).toBe("No pudimos guardar. Probá de nuevo.");
  });
});

describe("the panel's menu", () => {
  it("shows «Qué comprar» always and «Vendedores» only with its switch", () => {
    expect(dealerPages(false).map((p) => p.label)).toEqual(["Stock", "Cargar", "Consultas", "Qué comprar", "Datos"]);
    expect(dealerPages(true).map((p) => p.label)).toContain("Vendedores");
    expect(dealerPageFor("/agencia/comprar/mercado")).toBe("/agencia/comprar");
    expect(dealerPageFor("/agencia/vendedores")).toBe("/agencia/vendedores");
  });
});
