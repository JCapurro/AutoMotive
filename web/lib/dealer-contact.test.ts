import { describe, expect, it } from "vitest";

import { dealerPageFor } from "@/components/agencia/dealer-nav";
import {
  confirmedAgoText, consentText, DEALER_CONTACT_PRIVACY_LINE, defaultMessage, leadErrorText, normalizePhone, parseDealerCard, whatsappText, whatsappUrl,
} from "@/lib/dealer-contact";

describe("«Quiero que me contacten»", () => {
  it("names the agency in the consent the buyer ticks", () => {
    const text = consentText("Autos Sur");
    expect(text).toBe("Acepto que Ese Auto le pase mi nombre, mi teléfono y mi mensaje a Autos Sur para que me contacte por este auto.");
    expect(text.length).toBeGreaterThanOrEqual(20);
    expect(consentText("  ")).toContain("la agencia");
    expect(consentText("x".repeat(400)).length).toBeLessThanOrEqual(300);
    expect(DEALER_CONTACT_PRIVACY_LINE).toContain("a nadie más");
  });

  it("keeps only phone digits, 8 to 15 of them", () => {
    expect(normalizePhone("+54 9 11 5555-1234")).toBe("5491155551234");
    expect(normalizePhone("1234")).toBeNull();
    expect(normalizePhone(null)).toBeNull();
  });

  it("builds an encoded WhatsApp link only for a real number", () => {
    const text = whatsappText("Ford Focus 2017", "Ana & Co");
    expect(text).toBe("Hola, vi tu Ford Focus 2017 en Ese Auto y te pedí que me contactes. Soy Ana & Co.");
    const url = whatsappUrl("5491155551234", text);
    expect(url).toBe(`https://wa.me/5491155551234?text=${encodeURIComponent(text)}`);
    expect(url).not.toContain(" ");
    expect(url).not.toContain("&Co");
    expect(whatsappUrl("123", text)).toBeNull();
    expect(whatsappUrl(null, text)).toBeNull();
    expect(defaultMessage("Ford Focus 2017")).toBe("Hola, me interesa el Ford Focus 2017. ¿Sigue disponible?");
  });

  it("puts the RPC's codes in words", () => {
    expect(leadErrorText("consent_required")).toBe("Marcá la casilla para que le pasemos tus datos.");
    expect(leadErrorText("whatever")).toBe("No pudimos guardar. Probá de nuevo.");
  });

  it("reads the card tolerantly and says how fresh the stock is", () => {
    expect(parseDealerCard(null)).toBeNull();
    expect(parseDealerCard("x")).toBeNull();
    const now = new Date("2026-11-18T12:00:00Z");
    expect(confirmedAgoText(null, now)).toBeNull();
    expect(confirmedAgoText("2026-11-15T12:00:00Z", now)).toMatch(/3 días/);
  });
});

describe("panel menu", () => {
  it("marks the page the agency is on", () => {
    expect(dealerPageFor("/agencia/stock")).toBe("/agencia/stock");
    expect(dealerPageFor("/agencia/stock/nuevo")).toBe("/agencia/stock/planilla");
    expect(dealerPageFor("/agencia/consultas")).toBe("/agencia/consultas");
  });
});
