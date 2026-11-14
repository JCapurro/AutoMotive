import { describe, expect, it } from "vitest";

import { channelOf, encodeOrigin, landingKind, originFromRequest, parseOrigin, skipsOrigin } from "./acquisition";

const at = new Date("2026-11-14T12:00:00Z");
const visit = (path: string, referer: string | null = null) => originFromRequest(new URL(`https://eseauto.com.ar${path}`), referer, at);

describe("originFromRequest", () => {
  it("keeps UTM, the ad click and the landing path without the query", () => {
    expect(visit("/?utm_source=Facebook&utm_medium=paid&utm_campaign=v3&fbclid=abc")).toEqual({
      source: "facebook", medium: "paid", campaign: "v3", landing: "/", click: "meta", at: at.toISOString(),
    });
  });

  it("keeps an outside referrer host and drops our own", () => {
    expect(visit("/guias/ford/focus", "https://www.google.com.ar/").referrer).toBe("google.com.ar");
    expect(visit("/planes", "https://eseauto.com.ar/guias").referrer).toBeUndefined();
    expect(visit("/", "not a url").referrer).toBeUndefined();
  });
});

describe("parseOrigin", () => {
  it("round-trips the cookie and drops unknown fields and bad click ids", () => {
    const o = visit("/?twclid=1");
    expect(parseOrigin(encodeOrigin(o))).toEqual(o);
    expect(parseOrigin({ source: "x", click: "tiktok", extra: 1 })).toEqual({ source: "x" });
    expect(parseOrigin("%%%")).toBeNull();
    expect(parseOrigin(null)).toBeNull();
  });
});

describe("channelOf", () => {
  it.each([
    [{ click: "meta" as const }, "meta_ads"],
    [{ source: "instagram", medium: "cpc" }, "meta_ads"],
    [{ click: "x" as const }, "x_ads"],
    [{ source: "twitter", medium: "paid" }, "x_ads"],
    [{ click: "google" as const }, "google_ads"],
    [{ landing: "/fundador/abc" }, "founder"],
    [{ medium: "email", source: "resend" }, "email"],
    [{ referrer: "chatgpt.com" }, "ai"],
    [{ referrer: "gemini.google.com" }, "ai"],
    [{ source: "whatsapp" }, "social"],
    [{ source: "volante" }, "campaign"],
    [{ referrer: "google.com.ar" }, "search"],
    [{ referrer: "l.facebook.com" }, "social"],
    [{ referrer: "t.co" }, "social"],
    [{ referrer: "foro.autos.com" }, "referral"],
    [{ landing: "/" }, "direct"],
  ])("%j → %s", (origin, channel) => {
    expect(channelOf(origin)).toBe(channel);
  });

  it("is unknown without a first visit", () => {
    expect(channelOf(null)).toBe("unknown");
  });
});

it("skips secret, alert and backoffice pages", () => {
  for (const p of ["/auth/confirm", "/baja", "/r/1", "/m/2", "/api/x", "/admin", "/admin/users"]) expect(skipsOrigin(p)).toBe(true);
  for (const p of ["/", "/guias/ford", "/planes", "/administrar"]) expect(skipsOrigin(p)).toBe(false);
});

it("names the kind of first page", () => {
  expect(landingKind("/")).toBe("Inicio");
  expect(landingKind("/guias/ford/focus")).toBe("Guía");
  expect(landingKind(undefined)).toBe("—");
});
