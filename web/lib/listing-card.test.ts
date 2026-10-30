import { createElement, type ComponentProps } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";

import { ListingCard } from "@/components/app/listing-card";
import type { PriceTrack } from "@/lib/price-track";

type Card = ComponentProps<typeof ListingCard>["card"];
const card: Card = {
  listing_id: 1, make: "Toyota", model: "Corolla Cross", trim: "XEI", year: 2022, title: "Toyota Corolla Cross XEI",
  price: 25000, currency: "USD", mileage_km: 40000, location_text: "Rosario", published_at: null,
  first_seen_at: "2026-10-14T12:00:00Z", images: [], level: "good", score: 70, status: "new", saved: false,
  profile_name: "SUV hasta USD 30.000", listing_status: "active", probable_repost_of: null,
};

it("shows the user's note on one line, escaped, and nothing without one (X-01)", () => {
  const html = renderToStaticMarkup(createElement(ListingCard, { card: { ...card, note: "Llamé\n<b>martes</b>" } }));
  const note = html.match(/<p[^>]*data-testid="card-note"[^>]*>([\s\S]*?)<\/p>/);
  expect(note?.[0]).toContain("truncate");
  expect(note?.[1]).toContain("Llamé\n&lt;b&gt;martes&lt;/b&gt;");
  const plain = renderToStaticMarkup(createElement(ListingCard, { card }));
  expect(plain).not.toContain("card-note");
  expect(renderToStaticMarkup(createElement(ListingCard, { card: { ...card, note: null } }))).toBe(plain);
});

it("shows the body type in the card's meta line (docs/CARROCERIA.md)", () => {
  const html = renderToStaticMarkup(createElement(ListingCard, { card: { ...card, body_type: "suv" } }));
  expect(html).toMatch(/40\.000 km<\/span><span>SUV<\/span>/);
  // Unknown or not loaded (the saved page builds cards from listings): nothing.
  for (const bodyType of [null, undefined, "camioneta"]) {
    expect(renderToStaticMarkup(createElement(ListingCard, { card: { ...card, body_type: bodyType } }))).not.toContain(">SUV<");
  }
});

// PAR-03, opción B: 14.000 → 13.500 published and shown.
const track: PriceTrack = {
  listing_id: 1, drops: 1, rises: 0, first_at: "2026-09-20T15:00:00Z", first_price: 14000, first_currency: "USD",
  last_price: 13500, last_currency: "USD", cum_pct: 3.57, cum_usd: 500, last_drop_at: "2026-09-25T15:00:00Z",
};
const line = (html: string) => html.match(/<p[^>]*data-testid="card-price-track"[^>]*>([\s\S]*?)<\/p>/)?.[1] ?? null;

it("tells the drops when the card shows the published price (PAR-03)", () => {
  const shown = { ...card, price: 13500 };
  for (const price_source of [undefined, "published"]) {
    const html = renderToStaticMarkup(createElement(ListingCard, { card: { ...shown, price_source }, track }));
    expect(line(html)).toBe("Bajó 1 vez desde que la vimos: -USD 500 (-3,6%).");
  }
});

it("hides the drops next to a price read from the description (PAR-03)", () => {
  // A fixed cash price while the published one fell; the total behind a lower ARS down payment.
  const cash = { ...card, price: 9500, price_kind: "cash", price_source: "description" };
  const html = renderToStaticMarkup(createElement(ListingCard, { card: cash, track }));
  expect(html).toContain("de contado");
  expect(html).not.toContain("card-price-track");
  const pesos: PriceTrack = { ...track, first_price: 5_000_000, first_currency: "ARS", last_price: 4_000_000, last_currency: "ARS", cum_pct: 20, cum_usd: null };
  const down = { ...card, price: 15000, price_kind: "cash", price_source: "description" };
  expect(renderToStaticMarkup(createElement(ListingCard, { card: down, track: pesos }))).not.toContain("card-price-track");
});
