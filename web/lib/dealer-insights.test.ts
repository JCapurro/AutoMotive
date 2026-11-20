import { describe, expect, it } from "vitest";

import { dealerErrorText, parseDealerProgram, channelOn, DEFAULT_DEALER_PROGRAM } from "@/lib/dealer-program";
import {
  demandCount, demandText, hiddenReasonText, itemSending, parseDemand, parseMarket, priceCheck, priceVsMarketText,
  stockRowView, SYNC_ERROR_TEXT,
} from "@/lib/dealer-insights";

describe("dealer_program", () => {
  it("is off unless both switches say true, with safe numbers", () => {
    expect(parseDealerProgram(null)).toEqual(DEFAULT_DEALER_PROGRAM);
    expect(parseDealerProgram({ enabled: "true", channel_enabled: 1 })).toEqual(DEFAULT_DEALER_PROGRAM);
    expect(parseDealerProgram({ enabled: true, manual_confirm_days: 0, demand_min_count: 2 })).toEqual({ ...DEFAULT_DEALER_PROGRAM, enabled: true });
    expect(parseDealerProgram({ enabled: true, channel_enabled: true, manual_confirm_days: 14, demand_min_count: 5 }))
      .toEqual({ ...DEFAULT_DEALER_PROGRAM, enabled: true, channelEnabled: true, manualConfirmDays: 14, demandMinCount: 5 });
    expect(channelOn({ ...DEFAULT_DEALER_PROGRAM, channelEnabled: true })).toBe(false);
  });

  it("puts RPC codes in words without echoing input", () => {
    expect(dealerErrorText("invalid_item:3:price")).toBe("Revisá el precio en la fila 3.");
    expect(dealerErrorText("invalid_dealer:whatsapp")).toBe("Revisá el WhatsApp.");
    expect(dealerErrorText("already_member")).toBe("Ya tenés una agencia.");
    expect(dealerErrorText("duplicate key value violates <secret>")).toBe("No pudimos guardar. Probá de nuevo.");
  });
});

describe("market", () => {
  const market = (vs: number | null, n = 23, enough = true) => parseMarket({ n, median: 15000, p25: 13000, p75: 17000, vs_market_pct: vs, enough });

  it("says where the price stands", () => {
    expect(priceVsMarketText(null)).toBe("Sin comparables");
    expect(priceVsMarketText(market(5, 3, false))).toBe("Pocos comparables (3)");
    expect(priceVsMarketText(market(8))).toBe("En precio · 23 comparables");
    expect(priceVsMarketText(market(12.4))).toBe("12 % arriba de autos parecidos · 23 comparables");
    expect(priceVsMarketText(market(-15))).toBe("15 % abajo de autos parecidos · 23 comparables");
  });

  it("flags a price far from the market only with enough comparables", () => {
    expect(priceCheck(market(-25))).toBe("far_below");
    expect(priceCheck(market(60))).toBe("far_above");
    expect(priceCheck(market(-25, 3, false))).toBeNull();
  });
});

describe("demand", () => {
  it("never prints a 1 or a 2", () => {
    expect(demandCount(1)).toBe("pocas");
    expect(demandCount(2)).toBe("pocas");
    expect(demandCount(4, 5)).toBe("pocas");
    expect(demandCount("few")).toBe("pocas");
    expect(demandCount(0)).toBe("ninguna");
    expect(demandCount(null)).toBe("sin dato");
    expect(demandCount(42)).toBe("42");
  });

  it("reads the levels and says them in a line", () => {
    const d = parseDemand({ approved: true, window_days: 90, min_count: 3, levels: { model: 42, fits: 17, zone: 2, active_zone: "few" } });
    expect(demandText(d)).toBe("42 búsquedas del modelo · 17 entran en año y precio · pocas en tu zona · pocas activas en tu zona");
    expect(demandText(d)).not.toMatch(/(^|\D)[12] /);
    expect(demandText(parseDemand({ approved: false }))).toBe("La demanda se ve con el plan Pro activo");
    expect(parseDemand({ approved: true, min_count: 1, levels: {} })).toMatchObject({ min_count: 3 });
  });

  it("explains why a car isn't reaching buyers", () => {
    expect(hiddenReasonText("pending_sync", 7)).toBe("Lo estamos cargando");
    expect(hiddenReasonText("unconfirmed", 7)).toContain("7");
  });

  it("says a car is being sent when the gate lets it through (a null reason is not «pending»)", () => {
    expect(itemSending({ status: "available", sync_state: "synced", hidden_reason: null }, 7))
      .toEqual({ text: "Se envía a quien lo busca", sends: true });
    expect(itemSending({ status: "available", sync_state: "linked", hidden_reason: null }, 7).sends).toBe(true);
  });

  it("without an insight row, a car on sale is loading and an archived or sold one says so", () => {
    expect(itemSending({ status: "available", sync_state: "pending" }, 7)).toEqual({ text: "Lo estamos cargando", sends: false });
    expect(itemSending({ status: "archived", sync_state: "synced" }, 7)).toEqual({ text: "Sacado del stock", sends: false });
    expect(itemSending({ status: "sold", sync_state: "gone", hidden_reason: "pending_sync" }, 7).text).toBe("Vendido: no se envía");
  });

  it("tells the agency when the worker could not load a car, instead of «loading» forever", () => {
    for (const hidden of ["pending_sync", null]) {
      expect(itemSending({ status: "available", sync_state: "error", hidden_reason: hidden }, 7))
        .toEqual({ text: SYNC_ERROR_TEXT, sends: false });
    }
    const row = stockRowView({
      item_id: 1, origin: "manual", status: "available", sync_state: "error", make: "Ford", model: "Focus", trim: null,
      year: 2017, mileage_km: null, price: 1, currency: "USD", price_usd: 1, hidden_reason: "pending_sync",
      market: null, days_in_stock: 0, model_days_to_sell: null, demand: null,
    }, 7);
    expect(row).toMatchObject({ sending: SYNC_ERROR_TEXT, sends: false, review: false });
  });
});
