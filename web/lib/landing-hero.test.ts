import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  blurred, builderPicking, builderPrompt, builderText, EMPTY_BUILDER, feedAgo, feedPlace, HERE, HERO_MODELS, heroBucket, heroModels,
  heroVariant, landingHeroConfig, modelLabel, NATIONWIDE, parseLandingFeed, pickBudget, pickModel, pickOther, pickZone, typed,
} from "./landing-hero";
import { clearHere, storeHere, takeHere } from "./landing-here";

describe("the hero test's switch and split", () => {
  it("is off without the row or without enabled: true, and shares half by default", () => {
    expect(landingHeroConfig(undefined)).toEqual({ enabled: false, share: 50 });
    expect(landingHeroConfig({ enabled: "true", share: 30 })).toEqual({ enabled: false, share: 30 });
    expect(landingHeroConfig({ enabled: true, share: 100 })).toEqual({ enabled: true, share: 100 });
    expect(landingHeroConfig({ enabled: true, share: 140 })).toEqual({ enabled: true, share: 50 });
    expect(landingHeroConfig([true])).toEqual({ enabled: false, share: 50 });
  });

  it("reads a bucket only from 0 to 99", () => {
    expect(heroBucket("0")).toBe(0);
    expect(heroBucket("99")).toBe(99);
    expect(heroBucket("100")).toBeNull();
    expect(heroBucket("-1")).toBeNull();
    expect(heroBucket("b")).toBeNull();
    expect(heroBucket(undefined)).toBeNull();
  });

  it("shows the new hero only with the switch on, to anonymous visitors under the share", () => {
    const on = { enabled: true, share: 50 };
    expect(heroVariant(on, "49", false)).toBe("b");
    expect(heroVariant(on, "50", false)).toBe("a");
    expect(heroVariant(on, "10", true)).toBe("a");
    expect(heroVariant(on, undefined, false)).toBe("a");
    expect(heroVariant({ enabled: false, share: 100 }, "10", false)).toBe("a");
    expect(heroVariant(null, "10", false)).toBe("a");
    expect(heroVariant({ enabled: true, share: 100 }, "99", false)).toBe("b");
    expect(heroVariant({ enabled: true, share: 0 }, "0", false)).toBe("a");
  });
});

describe("what the hero shows", () => {
  const row = { make: "Volkswagen", model: "Polo", trim: "Comfortline", year: 2018, km: 86000, usd: 11457, median: 12881, n: 18, where: "Buenos Aires", source: "kavak", seen_at: "2026-11-14T13:20:07Z" };

  it("turns landing_feed into rows, dropping whatever can't be printed whole", () => {
    const feed = parseLandingFeed({
      flagged_24h: 56,
      rows: [row, { ...row, km: null }, { ...row, median: 11000 }, { ...row, seen_at: "ayer" }, null, { ...row, trim: null, source: "usadossantafe", where: "Malvinas Argentinas - Bs.As. G.B.A. Norte" }],
      models: [{ make: "Volkswagen", model: "Golf" }, { make: "Volkswagen", model: "Golf" }, { make: "", model: "Focus" }],
    });
    expect(feed.flagged24h).toBe(56);
    expect(feed.rows).toEqual([
      { model: "Volkswagen Polo", name: "Volkswagen Polo Comfortline 2018", km: 86000, usd: 11457, median: 12881, n: 18, where: "Buenos Aires", source: "Kavak", seenAt: "2026-11-14T13:20:07Z" },
      { model: "Volkswagen Polo", name: "Volkswagen Polo 2018", km: 86000, usd: 11457, median: 12881, n: 18, where: "Malvinas Argentinas", source: "Usadossantafe", seenAt: "2026-11-14T13:20:07Z" },
    ]);
    expect(feed.models).toEqual(["Volkswagen Golf"]);
  });

  it("survives anything that is not the function's answer", () => {
    expect(parseLandingFeed(null)).toEqual({ flagged24h: 0, rows: [], models: [] });
    expect(parseLandingFeed({ flagged_24h: "x", rows: "no", models: 3 })).toEqual({ flagged24h: 0, rows: [], models: [] });
  });

  it("uses its own models once there are six, the fixed list until then", () => {
    expect(heroModels(null)).toBe(HERO_MODELS);
    expect(heroModels({ flagged24h: 0, rows: [], models: ["A B", "C D"] })).toBe(HERO_MODELS);
    const six = ["A 1", "A 2", "A 3", "A 4", "A 5", "A 6"];
    expect(heroModels({ flagged24h: 0, rows: [], models: six })).toBe(six);
  });

  it("labels places, models and times", () => {
    expect(feedPlace("Rosario, Santa Fe")).toBe("Rosario");
    expect(modelLabel("Volkswagen Gol Trend")).toBe("Gol Trend");
    expect(modelLabel("Hilux")).toBe("Hilux");
    const now = new Date("2026-11-14T14:00:00Z");
    expect(feedAgo("2026-11-14T13:25:00Z", now)).toBe("hace 35 min");
    expect(feedAgo("2026-11-14T11:00:00Z", now)).toBe("hace 3 h");
    expect(feedAgo("2026-11-14T14:00:00Z", now)).toBe("hace 1 min");
  });
});

describe("the search built by tapping", () => {
  it("writes model, budget and zone into the text", () => {
    let s = pickModel(EMPTY_BUILDER, "Toyota Corolla");
    expect(builderText(s)).toBe("Busco Toyota Corolla");
    s = pickZone(pickBudget(s, 16000), NATIONWIDE);
    expect(builderText(s)).toBe("Busco Toyota Corolla hasta USD 16.000 en todo el país");
    expect(builderPrompt(s)).toBe(builderText(s));
    s = pickZone(s, "Córdoba");
    expect(builderText(s)).toBe("Busco Toyota Corolla hasta USD 16.000 en Córdoba");
    // A second tap takes the option back.
    expect(builderText(pickZone(pickBudget(s, 16000), "Córdoba"))).toBe("Busco Toyota Corolla");
  });

  it("keeps budget and zone when the model changes, and lets go of everything on a second tap", () => {
    const s = pickZone(pickBudget(pickModel(EMPTY_BUILDER, "Ford Focus"), 12000), "AMBA");
    expect(builderText(pickModel(s, "Volkswagen Gol"))).toBe("Busco Volkswagen Gol hasta USD 12.000 en AMBA");
    expect(pickModel(s, "Ford Focus")).toEqual(EMPTY_BUILDER);
  });

  it("«Otro»: the model is typed, budget and zone are still tapped", () => {
    let s = pickOther(pickModel(EMPTY_BUILDER, "Ford Focus"));
    expect(s).toMatchObject({ other: true, model: "" });
    expect(builderPicking(s)).toBe(true);
    expect(builderText(s)).toBe("");
    // Tapped before typing: they wait, and join the text when the box is left.
    s = pickBudget(s, 14000);
    expect(builderText(s)).toBe("");
    s = typed(s, "Peugeot 208 2019 en adelante");
    expect(s.budget).toBe(14000);
    expect(builderText(s)).toBe("Peugeot 208 2019 en adelante");
    expect(builderPrompt(s)).toBe("Peugeot 208 2019 en adelante");
    s = blurred(s);
    expect(builderText(s)).toBe("Peugeot 208 2019 en adelante hasta USD 14.000");
    s = pickZone(s, "Córdoba");
    expect(builderText(s)).toBe("Peugeot 208 2019 en adelante hasta USD 14.000 en Córdoba");
    expect(pickOther(s)).toEqual(EMPTY_BUILDER);
  });

  it("typing before the tail keeps the chips; editing the tail by hand lets them go", () => {
    let s = pickZone(pickBudget(pickModel(EMPTY_BUILDER, "Ford Focus"), 12000), "AMBA");
    s = typed(s, "Busco Ford Focus 2015 en adelante hasta USD 12.000 en AMBA");
    expect(s).toMatchObject({ budget: 12000, zone: "AMBA", base: "Busco Ford Focus 2015 en adelante" });
    expect(builderText(pickBudget(s, 16000))).toBe("Busco Ford Focus 2015 en adelante hasta USD 16.000 en AMBA");
    s = typed(s, "Busco Ford Focus 2015 en adelante hasta USD 12.500 en AMBA");
    expect(s).toMatchObject({ budget: 0, zone: "", shown: "" });
    expect(builderText(s)).toBe("Busco Ford Focus 2015 en adelante hasta USD 12.500 en AMBA");
    expect(blurred(s)).toBe(s);
  });

  it("shows «cerca de mi ubicación» but never sends it to be read", () => {
    const s = pickZone(pickBudget(pickModel(EMPTY_BUILDER, "Toyota Corolla"), 12000), HERE);
    expect(builderText(s)).toBe("Busco Toyota Corolla hasta USD 12.000 cerca de mi ubicación");
    expect(builderPrompt(s)).toBe("Busco Toyota Corolla hasta USD 12.000");
    expect(builderPrompt(pickZone(pickModel(EMPTY_BUILDER, "Toyota Corolla"), HERE))).toBe("Busco Toyota Corolla");
  });

  it("is nothing until there is a car", () => {
    expect(builderPicking(EMPTY_BUILDER)).toBe(false);
    expect(builderPrompt(EMPTY_BUILDER)).toBe("");
    expect(builderPrompt(typed(EMPTY_BUILDER, "  un Gol blanco  "))).toBe("un Gol blanco");
  });
});

describe("«Mi ubicación» waiting for the search", () => {
  beforeEach(() => {
    const data = new Map<string, string>();
    vi.stubGlobal("localStorage", {
      getItem: (k: string) => data.get(k) ?? null,
      setItem: (k: string, v: string) => void data.set(k, v),
      removeItem: (k: string) => void data.delete(k),
    });
  });

  it("is read once, as a device location", () => {
    storeHere({ lat: -34.6, lon: -58.38 }, 1_000);
    expect(takeHere(2_000)).toEqual({ label: "Mi ubicación actual", lat: -34.6, lon: -58.38, approximate: false });
    expect(takeHere(2_000)).toBeNull();
  });

  it("is not used once stale, cleared or malformed", () => {
    storeHere({ lat: -34.6, lon: -58.38 }, 0);
    expect(takeHere(31 * 60_000)).toBeNull();
    storeHere({ lat: -34.6, lon: -58.38 }, 0);
    clearHere();
    expect(takeHere(1)).toBeNull();
    localStorage.setItem("ea_here", JSON.stringify({ lat: 200, lon: 0, at: 0 }));
    expect(takeHere(1)).toBeNull();
    localStorage.setItem("ea_here", "{");
    expect(takeHere(1)).toBeNull();
  });

  it("does nothing without storage", () => {
    vi.stubGlobal("localStorage", undefined);
    expect(() => storeHere({ lat: 1, lon: 1 })).not.toThrow();
    expect(() => clearHere()).not.toThrow();
    expect(takeHere()).toBeNull();
  });
});
