import { describe, expect, it } from "vitest";

import {
  canChangeStatus,
  listingTrackingConfig,
  NOTE_MAX_DEFAULT,
  normalizeNote,
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

describe("normalizeNote", () => {
  it("trims and stores an empty note as null", () => {
    expect(normalizeNote("  hola  ", 500)).toEqual({ note: "hola" });
    expect(normalizeNote("", 500)).toEqual({ note: null });
    expect(normalizeNote(" \n\t ", 500)).toEqual({ note: null });
  });
  it("rejects a note over the limit instead of cutting it", () => {
    expect(normalizeNote("a".repeat(500), 500)).toEqual({ note: "a".repeat(500) });
    expect(normalizeNote("a".repeat(501), 500)).toHaveProperty("error");
  });
  it("counts characters like Postgres' char_length, not UTF-16 units", () => {
    expect(normalizeNote("🚗".repeat(500), 500)).toEqual({ note: "🚗".repeat(500) });
  });
  it("keeps line breaks and control characters but drops NUL", () => {
    expect(normalizeNote("visita\nmartes\t10 hs\u0007", 500)).toEqual({ note: "visita\nmartes\t10 hs\u0007" });
    expect(normalizeNote("a\u0000b", 500)).toEqual({ note: "ab" });
  });
});

describe("listingTrackingConfig", () => {
  it("defaults to 500 characters", () => {
    expect(NOTE_MAX_DEFAULT).toBe(500);
    expect(listingTrackingConfig(undefined)).toEqual({ noteMaxChars: 500 });
    expect(listingTrackingConfig({})).toEqual({ noteMaxChars: 500 });
  });
  it("reads app_config.listing_tracking.note_max_chars", () => {
    expect(listingTrackingConfig({ note_max_chars: 300 })).toEqual({ noteMaxChars: 300 });
  });
  it("falls back on non-numeric or non-positive values", () => {
    for (const v of ["x", 0, -5, null, Number.NaN]) {
      expect(listingTrackingConfig({ note_max_chars: v })).toEqual({ noteMaxChars: 500 });
    }
  });
});
