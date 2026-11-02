import { describe, expect, it } from "vitest";

import * as tracking from "@/lib/listing-tracking";
import {
  canChangeStatus,
  parsePurchasePrice,
  selectableStatuses,
  statusOnSave,
} from "@/lib/listing-tracking";

describe("selectableStatuses (X-01)", () => {
  it("offers every status but Nuevo, in the order of the follow-up", () => {
    expect(selectableStatuses()).toEqual([
      { value: "seen", label: "Visto" },
      { value: "interested", label: "Guardada" },
      { value: "contacted", label: "Contactado" },
      { value: "visit_scheduled", label: "Visita agendada" },
      { value: "purchased", label: "Comprado" },
      { value: "discarded", label: "Descartado" },
    ]);
  });
});

describe("statusOnSave", () => {
  it("keeps a follow-up status and only marks the listing saved", () => {
    expect(statusOnSave("contacted")).toEqual({ kind: "setSaved" });
    expect(statusOnSave("visit_scheduled")).toEqual({ kind: "setSaved" });
  });
  it("saves as Guardada from any other status", () => {
    for (const s of ["new", "seen", "interested", "discarded"] as const) {
      expect(statusOnSave(s)).toEqual({ kind: "setStatus", status: "interested" });
    }
  });
});

describe("canChangeStatus", () => {
  it("never leaves Comprado (terminal in v1)", () => {
    expect(canChangeStatus("purchased", "seen")).toBe(false);
    expect(canChangeStatus("purchased", "contacted")).toBe(false);
  });
  it("never goes to Comprado (recordPurchase) nor back to Nuevo", () => {
    expect(canChangeStatus("contacted", "purchased")).toBe(false);
    expect(canChangeStatus("seen", "new")).toBe(false);
  });
  it("allows the rest", () => {
    expect(canChangeStatus("new", "contacted")).toBe(true);
    expect(canChangeStatus("visit_scheduled", "contacted")).toBe(true);
    expect(canChangeStatus("discarded", "interested")).toBe(true);
  });
});

describe("no note (Juan 02/11)", () => {
  it("exports no note rule nor note config", () => {
    expect(Object.keys(tracking).filter((k) => /note|listingTrackingConfig/i.test(k))).toEqual([]);
  });
});

describe("parsePurchasePrice", () => {
  it("is null when left empty", () => {
    expect(parsePurchasePrice("")).toEqual({ price: null });
    expect(parsePurchasePrice("   ")).toEqual({ price: null });
  });
  it("takes whole numbers, with or without '.' thousands separators", () => {
    expect(parsePurchasePrice("9800")).toEqual({ price: 9800 });
    expect(parsePurchasePrice(" 9.800 ")).toEqual({ price: 9800 });
    expect(parsePurchasePrice("12.500.000")).toEqual({ price: 12500000 });
  });
  it("rejects anything ambiguous instead of guessing", () => {
    for (const raw of ["9800.50", "9800,50", "9,800", "1.5", "98.00", "9.8000", "9 800", "US$ 9800", "-9800", "1e4", "0", "0.000"]) {
      expect(parsePurchasePrice(raw), raw).toHaveProperty("error");
    }
  });
});
