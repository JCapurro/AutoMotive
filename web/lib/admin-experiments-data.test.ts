import { describe, expect, it } from "vitest";

import {
  type AuditRow, type ConfigRow, buildExperimentsBoard, daysLeft, describeChange, dueExperimentItems, type ExperimentRow, fromArtInput, historyOf,
  parseNumber, reviewState, switchState, toArtInput,
} from "./admin-experiments-data";

// 14/11/2026 at 12:00 in Argentina.
const now = new Date("2026-11-14T15:00:00Z");

const row = (slug: string, extra: Partial<ExperimentRow> = {}): ExperimentRow => ({
  slug, title: slug, config_key: slug, hypothesis: "h", metric: "m", baseline_text: null, baseline_value: null,
  started_at: "2026-11-10T12:00:00Z", review_at: null, status: "running", result_text: null, result_value: null,
  verdict_note: null, decided_at: null, created_at: "2026-11-10T12:00:00Z", updated_at: "2026-11-10T12:00:00Z", ...extra,
});
const audit = (id: number, key: string, at: string, before: unknown, after: unknown): AuditRow => ({
  id, target_type: "app_config", target_key: key, actor_id: "u1", actor_email: "juan@example.test", before_value: before, after_value: after, created_at: at,
});

describe("days left", () => {
  it("counts calendar days in Argentina, not 24-hour blocks", () => {
    expect(daysLeft("2026-11-21", now)).toBe(7);
    expect(daysLeft("2026-11-14", now)).toBe(0);
    expect(daysLeft("2026-11-11", now)).toBe(-3);
    // 01:30 UTC on the 15th is still the 14th in Argentina.
    expect(daysLeft("2026-11-15", new Date("2026-11-15T01:30:00Z"))).toBe(1);
    expect(daysLeft("2026-11-15", new Date("2026-11-15T03:00:00Z"))).toBe(0);
  });
  it("is null without a usable date", () => {
    expect(daysLeft(null, now)).toBeNull();
    expect(daysLeft("21/11", now)).toBeNull();
  });
});

describe("review state", () => {
  it("says how many days are left, in singular and plural", () => {
    expect(reviewState("2026-11-15", now)).toEqual({ kind: "upcoming", days: 1, label: "Faltan 1 día" });
    expect(reviewState("2026-11-21", now)).toEqual({ kind: "upcoming", days: 7, label: "Faltan 7 días" });
  });
  it("is ready to measure from the day itself on", () => {
    expect(reviewState("2026-11-14", now)).toMatchObject({ kind: "due", days: 0 });
    expect(reviewState("2026-11-13", now).label).toBe("Listo para medir (hace 1 día)");
    expect(reviewState("2026-11-11", now).label).toBe("Listo para medir (hace 3 días)");
  });
  it("has a state without a date", () => {
    expect(reviewState(null, now).kind).toBe("none");
  });
});

describe("the switch", () => {
  const config: ConfigRow[] = [
    { key: "a", value: { enabled: true, share: 50 } },
    { key: "b", value: { enabled: false, share: 50 } },
    { key: "c", value: { enabled: true } },
    { key: "d", value: { max: 3 } },
  ];
  it("reads on and off, with the share while it is on", () => {
    expect(switchState("a", config)).toEqual({ kind: "on", label: "Prendido", detail: "lo ve el 50 % de los visitantes" });
    expect(switchState("b", config)).toMatchObject({ kind: "off", label: "Apagado" });
    expect(switchState("c", config)).toMatchObject({ kind: "on", detail: null });
  });
  it("says so when there is no key, no row or no enabled field", () => {
    expect(switchState(null, config).kind).toBe("none");
    expect(switchState("zzz", config).kind).toBe("missing");
    expect(switchState("d", config).kind).toBe("unknown");
  });
});

describe("history of a key", () => {
  it("describes an on/off flip and any other changed field", () => {
    expect(describeChange({ enabled: false, share: 50 }, { enabled: true, share: 50 })).toBe("Se prendió");
    expect(describeChange({ enabled: true }, { enabled: false })).toBe("Se apagó");
    expect(describeChange({ enabled: true, share: 50 }, { enabled: true, share: 100 })).toBe("share: 50 → 100");
    expect(describeChange({ enabled: true, k: "x" }, { enabled: false, k: "y" })).toBe("Se apagó · k: x → y");
  });
  it("keeps only that key's config changes, newest first, and caps them", () => {
    const rows = [
      audit(1, "a", "2026-11-01T10:00:00Z", { enabled: false }, { enabled: true }),
      audit(2, "a", "2026-11-05T10:00:00Z", { enabled: true }, { enabled: false }),
      audit(3, "b", "2026-11-06T10:00:00Z", { enabled: false }, { enabled: true }),
      { ...audit(4, "a", "2026-11-07T10:00:00Z", {}, {}), target_type: "sources" },
    ];
    expect(historyOf("a", rows).map((h) => h.id)).toEqual([2, 1]);
    expect(historyOf("a", rows, 1)).toHaveLength(1);
    expect(historyOf(null, rows)).toEqual([]);
    expect(historyOf("a", rows)[0]).toMatchObject({ who: "juan@example.test", text: "Se apagó" });
  });
});

describe("the board", () => {
  const rows = [
    row("late", { review_at: "2026-11-24" }),
    row("soon", { review_at: "2026-11-16" }),
    row("nodate"),
    row("overdue", { review_at: "2026-11-11" }),
    row("due-today", { review_at: "2026-11-14" }),
    row("paused", { status: "paused", review_at: "2026-11-01" }),
    row("won-old", { status: "won", decided_at: "2026-11-02T10:00:00Z", review_at: "2026-10-30" }),
    row("lost-new", { status: "lost", decided_at: "2026-11-12T10:00:00Z" }),
  ];
  const board = buildExperimentsBoard(rows, [], [], now);
  it("puts running and due ones first, the most overdue before the rest", () => {
    expect(board.open.map((c) => c.slug)).toEqual(["overdue", "due-today", "soon", "late", "nodate", "paused"]);
  });
  it("keeps a paused experiment after the running ones even when it is overdue", () => {
    expect(board.open.at(-1)?.slug).toBe("paused");
  });
  it("lists decided ones apart, the latest decision first, with no re-measure state", () => {
    expect(board.decided.map((c) => c.slug)).toEqual(["lost-new", "won-old"]);
    expect(board.decided[0].review).toEqual({ kind: "none", label: "Decidido" });
  });
  it("counts the running ones that are due, not the paused", () => {
    expect(board.due).toBe(2);
  });
  it("is empty without experiments", () => {
    expect(buildExperimentsBoard([], [], [], now)).toEqual({ open: [], decided: [], due: 0 });
  });
});

describe("Argentina time in the forms", () => {
  it("round-trips a datetime-local value", () => {
    expect(toArtInput("2026-11-14T14:13:00Z")).toBe("2026-11-14T11:13");
    expect(fromArtInput("2026-11-14T11:13")).toBe("2026-11-14T14:13:00.000Z");
    expect(fromArtInput(toArtInput("2026-11-03T13:11:24Z"))).toBe("2026-11-03T13:11:00.000Z");
  });
  it("gives nothing for an empty or broken value", () => {
    expect(toArtInput(null)).toBe("");
    expect(fromArtInput("")).toBeNull();
    expect(fromArtInput("mañana")).toBeNull();
  });
});

describe("numbers typed by hand", () => {
  it("accepts a decimal comma and empties", () => {
    expect(parseNumber("48,5")).toBe(48.5);
    expect(parseNumber(" 12 ")).toBe(12);
    expect(parseNumber("")).toBeNull();
    expect(parseNumber("mucho")).toBeNull();
  });
});

describe("due experiments for the home page", () => {
  it("lists running experiments from their re-measure day on, the most overdue first", () => {
    const items = dueExperimentItems([
      row("today", { title: "Hoy", metric: "tasa", review_at: "2026-11-14" }),
      row("late", { title: "Atrasado", review_at: "2026-11-11" }),
      row("one", { title: "Ayer", review_at: "2026-11-13" }),
    ], now);
    expect(items.map((i) => i.title)).toEqual([
      "Experimento listo para medir: Atrasado", "Experimento listo para medir: Ayer", "Experimento listo para medir: Hoy"]);
    expect(items[0].detail).toBe("Se puede medir desde hace 3 días. Qué medir: m");
    expect(items[1].detail).toContain("desde hace 1 día.");
    expect(items[2]).toEqual({ title: "Experimento listo para medir: Hoy", detail: "Se puede medir desde hoy. Qué medir: tasa",
      href: "/admin/experiments#today", action: "Medir y decidir" });
  });
  it("leaves out the ones still to come, without a date, paused or decided", () => {
    expect(dueExperimentItems([
      row("soon", { review_at: "2026-11-21" }),
      row("none"),
      row("paused", { status: "paused", review_at: "2026-11-01" }),
      row("won", { status: "won", review_at: "2026-11-01" }),
    ], now)).toEqual([]);
  });
});
