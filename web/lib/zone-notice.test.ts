import { describe, expect, it } from "vitest";

import { SearchInput } from "@/lib/search-form";
import { APPROXIMATE_LABEL, DEVICE_LABEL } from "@/lib/search-location";
import {
  type NoticeProfile,
  ZONE_NOTICE_MAX_RESULTS,
  type ZoneNoticeData,
  cardLead,
  isWidenTo,
  noticeGate,
  noticeHeadline,
  optionLabel,
  parseZone,
  sameZone,
  searchFormKey,
  widenedDraft,
  widenedText,
  withoutPlace,
  zoneKind,
  zoneLine,
  zoneNoticeConfig,
  zoneOf,
  zoneOptions,
  zonePlace,
} from "@/lib/zone-notice";

// Aviso de zona (docs/AVISO_ZONA.md): when it shows, what it offers and what it says.
const READY: NoticeProfile = {
  enabled: true,
  filters: { make: "Toyota", model: "Corolla", location_label: "Laferrere" },
  origin_lat: -34.75, origin_lon: -58.58, radius_km: 30,
  bootstrapped_at: "2026-10-30T12:00:00Z", rematch_requested_at: null,
};
const gate = (patch: Partial<Parameters<typeof noticeGate>[0]> = {}) =>
  noticeGate({ profile: READY, count: 1, quotaReached: false, dismissed: [], reading: false, ...patch });

describe("noticeGate", () => {
  it("counts a ready search with a model and one zone, at three results or fewer", () => {
    expect(gate()).toBe("count");
    expect(gate({ count: 0 })).toBe("count");
    expect(gate({ count: ZONE_NOTICE_MAX_RESULTS })).toBe("count");
    expect(gate({ count: ZONE_NOTICE_MAX_RESULTS + 1 })).toBe("none");
  });
  it("waits while the search is being prepared, a source is on its first read or the count is missing", () => {
    expect(gate({ profile: { ...READY, bootstrapped_at: null } })).toBe("pending");
    expect(gate({ profile: { ...READY, rematch_requested_at: "2026-10-30T13:00:00Z" } })).toBe("pending");
    expect(gate({ reading: true })).toBe("pending");
    expect(gate({ count: null })).toBe("pending");
  });
  it("never applies to a paused search, one without a model, the whole country or several places", () => {
    expect(gate({ profile: { ...READY, enabled: false } })).toBe("none");
    expect(gate({ profile: { ...READY, filters: { body_types: ["suv"], price_max: 20000 } } })).toBe("none");
    expect(gate({ profile: { ...READY, filters: { make: "Toyota", model: " " } } })).toBe("none");
    expect(gate({ profile: { ...READY, origin_lat: null, origin_lon: null, radius_km: null } })).toBe("none");
    expect(gate({ profile: { ...READY, radius_km: 0 } })).toBe("none");
    const extra = { label: "Morón", lat: -34.65, lon: -58.62, radius_km: 30 };
    expect(gate({ profile: { ...READY, filters: { ...(READY.filters as object), extra_locations: [extra] } } })).toBe("none");
    // Before waiting: a search that will never show it doesn't keep the card asking.
    expect(gate({ profile: { ...READY, enabled: false, bootstrapped_at: null } })).toBe("none");
  });
  it("hides behind the free trial's reached quota and after «Dejar así» for that same zone", () => {
    expect(gate({ quotaReached: true })).toBe("none");
    expect(gate({ dismissed: [[-34.75, -58.58, 30]] })).toBe("none");
    // Another zone (a radius changed since) asks again.
    expect(gate({ dismissed: [[-34.75, -58.58, 20]] })).toBe("count");
  });
});

describe("the switch (app_config.zone_notice)", () => {
  it("is on only with enabled true: without the row, or with anything else, off", () => {
    expect(zoneNoticeConfig({ enabled: true })).toEqual({ enabled: true });
    for (const raw of [undefined, null, {}, { enabled: false }, { enabled: "true" }, { enabled: 1 }, [true], true]) {
      expect(zoneNoticeConfig(raw)).toEqual({ enabled: false });
    }
  });
});

describe("zoneOptions", () => {
  const radii = (r100: number, r200: number) => [{ radius: 100 as const, count: r100 }, { radius: 200 as const, count: r200 }];

  it("offers the smallest radius that reaches four results, then the whole country if it adds more", () => {
    expect(zoneOptions({ count: 1, current: 1, radii: radii(6, 14), country: 50, cap: null })).toEqual([
      { to: 100, count: 6, capped: false },
      { to: "pais", count: 50, capped: false },
    ]);
    expect(zoneOptions({ count: 1, current: 1, radii: radii(2, 14), country: 50, cap: null })).toEqual([
      { to: 200, count: 14, capped: false },
      { to: "pais", count: 50, capped: false },
    ]);
  });
  it("leaves the country out when it adds nothing over the radius, and offers it alone without one", () => {
    expect(zoneOptions({ count: 0, current: 0, radii: radii(5, 5), country: 5, cap: null })).toEqual([{ to: 100, count: 5, capped: false }]);
    expect(zoneOptions({ count: 0, current: 0, radii: radii(1, 2), country: 9, cap: null })).toEqual([{ to: "pais", count: 9, capped: false }]);
    // A search already at 150 km: only 200 km is wider.
    expect(zoneOptions({ count: 0, current: 0, radii: [{ radius: 200, count: 7 }], country: 7, cap: null })).toEqual([{ to: 200, count: 7, capped: false }]);
  });
  it("offers nothing when no option gets to four", () => {
    expect(zoneOptions({ count: 1, current: 1, radii: radii(2, 3), country: 3, cap: null })).toEqual([]);
  });
  it("estimates from the visible results plus what each option adds over the current zone", () => {
    // Two visible (one more than preview_search finds now: an older match), the wider zone adds four.
    expect(zoneOptions({ count: 2, current: 1, radii: radii(5, 5), country: 5, cap: null })).toEqual([{ to: 100, count: 6, capped: false }]);
    // A preview below the current one never subtracts.
    expect(zoneOptions({ count: 3, current: 4, radii: radii(2, 9), country: 9, cap: null })).toEqual([{ to: 200, count: 8, capped: false }]);
  });
  it("shows what an enforced free trial can still show as «N+»", () => {
    expect(zoneOptions({ count: 1, current: 1, radii: radii(6, 30), country: 80, cap: 10 })).toEqual([
      { to: 100, count: 6, capped: false },
      { to: "pais", count: 10, capped: true },
    ]);
    // A cap below four keeps every option out.
    expect(zoneOptions({ count: 1, current: 1, radii: radii(6, 30), country: 80, cap: 3 })).toEqual([]);
    // Both at the same «5+»: the country shows nothing more, and would spend the last slots far away.
    expect(zoneOptions({ count: 1, current: 1, radii: radii(11, 20), country: 60, cap: 5 })).toEqual([{ to: 100, count: 5, capped: true }]);
  });
});

describe("zones and places", () => {
  it("tells where the zone came from", () => {
    expect(zoneKind(APPROXIMATE_LABEL)).toBe("ip");
    expect(zoneKind("Laferrere (zona aproximada)")).toBe("ip");
    expect(zoneKind(DEVICE_LABEL)).toBe("device");
    expect(zoneKind("Laferrere")).toBe("named");
    expect(zoneKind(undefined)).toBe("named");
  });
  it("names the place in a sentence", () => {
    expect(zonePlace(APPROXIMATE_LABEL)).toBe("tu zona aproximada");
    expect(zonePlace("Laferrere (zona aproximada)")).toBe("Laferrere");
    expect(zonePlace(DEVICE_LABEL)).toBe("tu ubicación");
    expect(zonePlace(" Rosario ")).toBe("Rosario");
    expect(zonePlace(null)).toBe("la zona elegida");
  });
  it("reads the search's zone and the stored ones", () => {
    expect(zoneOf(READY)).toEqual([-34.75, -58.58, 30]);
    expect(zoneOf({ origin_lat: -34.75, origin_lon: null, radius_km: 30 })).toBeNull();
    expect(parseZone([-34.75, "-58.58", 30])).toEqual([-34.75, -58.58, 30]);
    expect(parseZone([-34.75, -58.58])).toBeNull();
    expect(parseZone([-34.75, "x", 30])).toBeNull();
    expect(parseZone("-34.75,-58.58,30")).toBeNull();
    expect(sameZone([-34.75, -58.58, 30], [-34.75, -58.58, 30])).toBe(true);
    expect(sameZone([-34.75, -58.58, 30], [-34.75, -58.58, 100])).toBe(false);
    expect(sameZone(null, [-34.75, -58.58, 30])).toBe(false);
  });
  it("drops the place, and only the place, for the whole country", () => {
    const filters = { make: "Toyota", model: "Corolla", location_label: "Laferrere", extra_locations: [], year_min: 2015 };
    expect(withoutPlace(filters)).toEqual({ make: "Toyota", model: "Corolla", year_min: 2015 });
    expect(filters.location_label).toBe("Laferrere");
  });
  it("accepts only the offered destinations", () => {
    expect([100, 200, "pais"].every(isWidenTo)).toBe(true);
    expect([50, 150, "país", "100", null].some(isWidenTo)).toBe(false);
  });
});

describe("the modo asistido's card after a widening", () => {
  const LAFERRERE = { label: "Laferrere", lat: -34.75, lon: -58.58, radius_km: 30 };
  const draft = {
    title: "Toyota Corolla",
    values: SearchInput.parse({ make: "Toyota", model: "Corolla", location: LAFERRERE }),
    notes: ["Buscamos en Laferrere. Si querés otra zona, cambiala abajo.", "Elegí la versión abajo."],
  };

  it("keeps the place with the new radius, so the form below doesn't undo it", () => {
    const widened = widenedDraft(draft, 100);
    expect(widened.values.location).toEqual({ ...LAFERRERE, radius_km: 100 });
    expect(widened.notes).toEqual(draft.notes);
    expect(widened.title).toBe("Toyota Corolla");
    expect(draft.values.location?.radius_km).toBe(30);
    // The form mounts again with the new zone.
    expect(searchFormKey(widened.values.location)).toBe("-34.75,-58.58,100");
    expect(searchFormKey(widened.values.location)).not.toBe(searchFormKey(draft.values.location));
  });
  it("drops the place, the extra ones and the note on where it searched for the whole country", () => {
    const morón = { label: "Morón", lat: -34.65, lon: -58.62, radius_km: 30 };
    const widened = widenedDraft({ ...draft, values: { ...draft.values, extra_locations: [morón] } }, "pais");
    expect([widened.values.location, widened.values.extra_locations]).toEqual([null, []]);
    expect(widened.notes).toEqual(["Elegí la versión abajo."]);
    expect(searchFormKey(widened.values.location)).toBe("pais");
  });
});

describe("the words", () => {
  const notice = (count: number): ZoneNoticeData => ({
    profileId: 7, count, place: "Laferrere", kind: "named", zone: [-34.75, -58.58, 30], options: [], cold: false,
  });

  it("says how many there are, with numbers", () => {
    expect(noticeHeadline(0)).toBe("En tu zona no hay publicaciones ahora.");
    expect(noticeHeadline(1)).toBe("En tu zona hay solo 1 publicación ahora.");
    expect(noticeHeadline(3)).toBe("En tu zona hay solo 3 publicaciones ahora.");
    expect(zoneLine(notice(1))).toBe("Buscamos a 30 km de Laferrere.");
    expect(cardLead(notice(0))).toBe("A 30 km de Laferrere no hay publicaciones ahora.");
    expect(cardLead(notice(2))).toBe("A 30 km de Laferrere hay solo 2 publicaciones ahora.");
  });
  it("labels each option with what it would show, and the change once made", () => {
    expect(optionLabel({ to: 200, count: 14, capped: false })).toBe("Hasta 200 km · 14");
    expect(optionLabel({ to: "pais", count: 1500, capped: true })).toBe("Todo el país · 1.500+");
    expect(widenedText(100, "Laferrere")).toBe("Listo: ahora buscamos a 100 km de Laferrere.");
    expect(widenedText("pais", "Laferrere")).toBe("Listo: ahora buscamos en todo el país.");
  });
});
