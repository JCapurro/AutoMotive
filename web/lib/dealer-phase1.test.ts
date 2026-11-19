import { describe, expect, it } from "vitest";

import { margin, type MarketRef, stockRowView, SUGGESTED_PRICE_NOTE, suggestedPrice } from "@/lib/dealer-insights";
import { dealerErrorText, parseDealerProgram } from "@/lib/dealer-program";

const market = (over: Partial<MarketRef> = {}): MarketRef => ({
  n: 12, median: 18_430, p25: 16_000, p75: 21_000, vs_market_pct: 5, enough: true, blue: 1_200, ...over,
});

describe("dealer_program, fase 1", () => {
  it("keeps alerts and photo import off and their numbers in range", () => {
    const off = parseDealerProgram(null);
    expect([off.alertsEnabled, off.alertsEveryHours, off.photoImportEnabled, off.photoImportDailyLimit]).toEqual([false, 24, false, 5]);
    const on = parseDealerProgram({ alerts_enabled: true, alerts_every_hours: 6, photo_import_enabled: true, photo_import_daily_limit: 50 });
    expect([on.alertsEnabled, on.alertsEveryHours, on.photoImportEnabled, on.photoImportDailyLimit]).toEqual([true, 6, true, 50]);
    const bad = parseDealerProgram({ alerts_enabled: "true", alerts_every_hours: 5, photo_import_enabled: 1, photo_import_daily_limit: 51 });
    expect([bad.alertsEnabled, bad.alertsEveryHours, bad.photoImportEnabled, bad.photoImportDailyLimit]).toEqual([false, 24, false, 5]);
  });

  it("says the photo errors in words", () => {
    expect(dealerErrorText("photo_import_limit")).toMatch(/máximo de fotos/);
    expect(dealerErrorText("file_too_big")).toMatch(/4 MB/);
    expect(dealerErrorText("invalid_file:type")).toMatch(/JPG/);
    expect(dealerErrorText("invalid_file:data")).toMatch(/No pudimos leer/);
    expect(dealerErrorText("photo_import_off")).toMatch(/no está disponible/);
  });
});

describe("suggested price", () => {
  it("is the median when the model sells in 30 days or we don't know", () => {
    const s = suggestedPrice(market(), { median: 25, n: 9 }, "USD")!;
    expect([s.amount, s.currency, s.label]).toEqual([18_400, "USD", "USD 18.400"]);
    expect(s.why).toMatch(/mediana de 12 comparables/);
    expect(suggestedPrice(market(), { median: 90, n: 3 }, "USD")!.amount).toBe(18_400);   // 3 cars: unknown
  });

  it("goes halfway to p25 when the model is slow", () => {
    const s = suggestedPrice(market(), { median: 45, n: 9 }, "USD")!;
    expect(s.amount).toBe(17_200);                                // (16.000 + 18.430) / 2
    expect(s.why).toMatch(/45 días/);
  });

  it("speaks pesos for an ARS car, rounded to 100.000", () => {
    const s = suggestedPrice(market(), null, "ARS")!;
    expect([s.amount, s.currency, s.usd]).toEqual([22_100_000, "ARS", 18_400]);   // 18.430 × 1.200 = 22.116.000
    expect(suggestedPrice(market({ blue: null }), null, "ARS")!.currency).toBe("USD");
  });

  it("is never shown without enough comparables", () => {
    expect(suggestedPrice(market({ enough: false }), null, "USD")).toBeNull();
    expect(suggestedPrice(market({ median: null }), null, "USD")).toBeNull();
    expect(suggestedPrice(null, null, "USD")).toBeNull();
    expect(SUGGESTED_PRICE_NOTE).toMatch(/no una valuación/);
  });
});

describe("margin", () => {
  it("is price minus cost, as a percent of the cost", () => {
    expect(margin(20_000, "USD", 16_000, "USD", null)).toEqual({ amount: 4_000, currency: "USD", pct: 25, label: "USD 4.000 (25 % sobre el costo)" });
    expect(margin(15_000, "USD", 16_000, null, null)!.label).toBe("-USD 1.000 (-6,3 % sobre el costo)");
  });

  it("converts the cost with the blue rate", () => {
    expect(margin(24_000_000, "ARS", 16_000, "USD", 1_200)!.amount).toBe(4_800_000);
    expect(margin(20_000, "USD", 19_200_000, "ARS", 1_200)!.amount).toBe(4_000);
    expect(margin(20_000, "USD", 19_200_000, "ARS", null)).toBeNull();
  });

  it("needs both numbers", () => {
    expect(margin(null, "USD", 1, "USD", 1)).toBeNull();
    expect(margin(20_000, "USD", null, null, 1)).toBeNull();
    expect(margin(20_000, null, 10, "USD", 1)).toBeNull();
  });
});

describe("stock row", () => {
  const row = {
    item_id: 1, origin: "manual", status: "available", sync_state: "ok", make: "Toyota", model: "Corolla", trim: null,
    year: 2019, mileage_km: 50_000, price: 20_000, currency: "USD", price_usd: 20_000, hidden_reason: null,
    market: market(), days_in_stock: 10, model_days_to_sell: { median: 20, n: 9 }, demand: null,
  };
  it("carries the suggested price, and the margin only when the cost is passed", () => {
    const v = stockRowView(row, 7);
    expect(v.suggested).toBe("Sugerido USD 18.400");
    expect(v.margin).toBeNull();
    const own = stockRowView(row, 7, null, { purchase_price: 21_000, purchase_currency: "USD" });
    expect(own.margin).toBe("Margen -USD 1.000 (-4,8 % sobre el costo)");
    expect(own.marginNegative).toBe(true);
  });
});
