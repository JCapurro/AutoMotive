import { describe, expect, it } from "vitest";

import { destination, isPreview, parseClick } from "./tracking";

describe("/r/<id> (sección 7.3)", () => {
  it("parses the target and the digest item", () => {
    expect(parseClick("12", new URLSearchParams("to=detail&l=7"))).toEqual({
      notificationId: 12,
      to: "detail",
      listingId: 7,
    });
    expect(parseClick("12", new URLSearchParams("to=nope&l=x"))).toEqual({
      notificationId: 12,
      to: "listing",
      listingId: null,
    });
    expect(parseClick("12abc", new URLSearchParams())).toBeNull();
  });

  it("sends detail clicks to the listing page with the alert, listing clicks to the source", () => {
    const row = { listing_id: 5, url: "https://auto.mercadolibre.com.ar/MLA-1_JM" };
    expect(destination("detail", row, 9)).toBe("/app/listings/5?n=9");
    expect(destination("listing", row, 9)).toBe(row.url);
  });

  it("does not count link previews", () => {
    expect(isPreview("TelegramBot (like TwitterBot)")).toBe(true);
    expect(isPreview("WhatsApp/2.23")).toBe(true);
    expect(isPreview("Mozilla/5.0 (iPhone)")).toBe(false);
    expect(isPreview(null)).toBe(false);
  });
});
