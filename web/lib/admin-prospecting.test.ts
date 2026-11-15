import { describe, expect, it } from "vitest";

import {
  artDay, buildBoard, FOUNDER_LINK, hookOf, hoursSince, type MessageRow, phoneLabel, type ProspectRow, REPLIES, replyRates, waLink,
} from "@/lib/admin-prospecting";

const prospect = (over: Partial<ProspectRow> = {}): ProspectRow => ({
  id: 1, kind: "agencia", display_name: "Autos del Parque Demo", first_name: null, sources: ["rosariogarage"], region: "litoral",
  locality: "Rosario, Santa Fe", phone: "5493415123456", phone_source: "aviso", phone_evidence: null, status: "queued",
  step_sent: 0, next_due_on: null, listing_count: 5, first_sent_at: null, last_sent_at: null, replied_at: null, ...over,
});

const message = (over: Partial<MessageRow> = {}): MessageRow => ({
  id: 10, prospect_id: 1, step: "first", batch_date: "2026-11-15", status: "ready", facts: {}, variants: [],
  chosen_index: 0, final_text: "Hola", edited: false, hook_type: "oportunidad", hook_url: null, review: {}, sent_at: null, ...over,
});

describe("waLink", () => {
  it("encodes the text and only takes a wa.me number", () => {
    expect(waLink("5493415123456", "Hola, ¿te lo paso?")).toBe("https://wa.me/5493415123456?text=Hola%2C%20%C2%BFte%20lo%20paso%3F");
    expect(waLink("3415123456", "x")).toBeNull();
    expect(waLink(null, "x")).toBeNull();
  });
  it("labels a number for reading", () => {
    expect(phoneLabel("5491155551234")).toBe("+54 9 11 5555-1234");
    expect(phoneLabel("5493415123456")).toBe("+54 9 341 512-3456");
  });
});

describe("replies", () => {
  it("quote the founder price for 3 months and the link only where asked", () => {
    const ctx = { name: "", hookUrl: "https://x/1", hookCar: "Toyota Etios 2015", zone: "Rosario" };
    const byKey = Object.fromEntries(REPLIES.map((r) => [r.key, r.text(ctx)]));
    expect(byKey.precio).toContain("$50.000 por mes los primeros 3 meses");
    expect(byKey.contratar).toContain(FOUNDER_LINK);
    expect(byKey.contratar).toContain("3 meses");
    expect(byKey.pasamelo).toContain("https://x/1");
    for (const text of Object.values(byKey)) expect(text).not.toMatch(/6 meses|vendid/);
  });
  it("reads the hook the final text offers, not the first one", () => {
    const facts = { ganchos: [{ auto: "Focus 2009", precio_publicado: "$7.500.000", url: "u1" },
      { auto: "Hilux 2013", precio_publicado: "US$ 16.800", url: "u2" }] };
    expect(hookOf({ facts, final_text: "Salió una Hilux a US$ 16.800. ¿Te la paso?" })).toMatchObject({ car: "Hilux 2013", url: "u2" });
    expect(hookOf({ facts, final_text: "Hay 7 búsquedas de Gol Trend. ¿Te cuento?" })).toMatchObject({ car: null, url: null });
    expect(hookOf(null)).toMatchObject({ car: null, url: null });
  });
  it("carries when the hook was checked, and asks for a recheck past 24 h", () => {
    const facts = { ganchos: [{ auto: "Etios", precio_publicado: "$11.900.000", url: "u", verificado: { en: "2026-11-15T10:00:00Z", como: "pagina" } }] };
    const h = hookOf({ facts, final_text: "Un Etios a $11.900.000. ¿Te lo paso?" });
    expect(h).toMatchObject({ checkedAt: "2026-11-15T10:00:00Z", checkedBy: "pagina" });
    expect(hoursSince(h.checkedAt, new Date("2026-11-16T12:30:00Z"))).toBe(26);
    expect(hoursSince(null, new Date())).toBeNull();
  });
});

describe("board and rates", () => {
  const now = new Date("2026-11-15T15:00:00Z");
  it("splits ready messages and counts today's sends in Argentina", () => {
    const board = buildBoard(
      [prospect(), prospect({ id: 2, status: "contacted", last_sent_at: "2026-11-10T12:00:00Z" })],
      [message(), message({ id: 11, prospect_id: 2, step: "followup" })],
      [{ prospect_id: 2, message_id: 9, kind: "sent", created_at: "2026-11-15T11:00:00Z" },
        { prospect_id: 2, message_id: 8, kind: "sent", created_at: "2026-11-15T02:00:00Z" }],   // 14/11 23:00 in Argentina
      now,
    );
    expect(board.newToday.map((r) => r.message.id)).toEqual([10]);
    expect(board.dueToday.map((r) => r.message.id)).toEqual([11]);
    expect(board.waiting.map((p) => p.id)).toEqual([2]);
    expect(board.sentToday).toBe(1);
    expect(artDay("2026-11-15T02:00:00Z")).toBe("2026-11-14");
  });
  it("rates by hook, source, kind and region over the first messages of the week", () => {
    const P = [prospect({ replied_at: "2026-11-14T12:00:00Z" }), prospect({ id: 2, kind: "persona", sources: ["facebook"], region: "amba" })];
    const M = [
      message({ status: "sent", sent_at: "2026-11-13T12:00:00Z" }),
      message({ id: 11, prospect_id: 2, status: "sent", sent_at: "2026-11-13T12:00:00Z", hook_type: "stock_viejo" }),
      message({ id: 12, prospect_id: 2, status: "sent", sent_at: "2026-11-01T12:00:00Z" }),          // older than a week
      message({ id: 13, prospect_id: 2, step: "followup", status: "sent", sent_at: "2026-11-14T12:00:00Z" }),
    ];
    const r = replyRates(P, M, new Date(now.getTime() - 7 * 86_400_000), now);
    expect(r.sent).toBe(2);
    expect(r.replied).toBe(1);
    expect(r.hook.find((x) => x.key === "oportunidad")).toMatchObject({ sent: 1, replied: 1 });
    expect(r.kind.find((x) => x.key === "persona")).toMatchObject({ sent: 1, replied: 0 });
    expect(r.region.map((x) => x.label).sort()).toEqual(["AMBA", "Litoral"]);
  });
});
