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

it("never shows a note, even one left in the row by older versions (Juan 02/11)", () => {
  const plain = renderToStaticMarkup(createElement(ListingCard, { card }));
  expect(plain).not.toContain("card-note");
  expect(plain).not.toContain("Tu nota");
  const withOld = { ...card, note: "Llamé el martes" } as Card;
  expect(renderToStaticMarkup(createElement(ListingCard, { card: withOld }))).toBe(plain);
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

// PAR-01: the total cost header, one line under the price, only when the page passes it.
it("shows the total cost line only when given, and leaves the card as it was otherwise", () => {
  const text = "Costo total estimado: USD 16.290 – 16.560 (ARS 21.188.000 – 21.518.000)";
  const html = renderToStaticMarkup(createElement(ListingCard, { card, costLine: text }));
  expect(html).toMatch(/<p[^>]*data-testid="cost-estimate-line"[^>]*>Costo total estimado: USD 16\.290 – 16\.560 \(ARS 21\.188\.000 – 21\.518\.000\)<\/p>/);
  const plain = renderToStaticMarkup(createElement(ListingCard, { card }));
  expect(plain).not.toContain("cost-estimate-line");
  for (const costLine of [null, undefined, ""]) expect(renderToStaticMarkup(createElement(ListingCard, { card, costLine }))).toBe(plain);
});

// Juan, 02/11: without Pro, where Pro would see the margin, the line in view and unreadable.
it("shows the margin teaser only when asked, with no figure, and never over Pro's own line", () => {
  const html = renderToStaticMarkup(createElement(ListingCard, { card, marginTeaser: true }));
  const teaser = html.match(/<p[^>]*data-testid="margin-teaser-line"[^>]*>[\s\S]*?<\/p>/)?.[0] ?? "";
  expect(teaser).toMatch(/^<p[^>]*class="col-start-2\b/);
  expect(teaser).toMatch(/<span aria-hidden="true" class="[^"]*"><span class="blur-\[4px\] select-none">USD X\.XXX<\/span><span [^>]*>Pro<\/span><\/span>/);
  expect(teaser).toContain('<span class="sr-only"> disponible con Pro</span>');
  expect(teaser.replace(/<[^>]+>/g, "")).not.toMatch(/\d/);
  // The card is one link (its title's, stretched): nothing to click inside the line.
  expect(teaser).not.toContain("<a");
  const pro = renderToStaticMarkup(createElement(ListingCard, { card, marginLine: "Margen bruto estimado: USD 1.210 a 1.230", marginTeaser: true }));
  expect(pro).toContain('data-testid="margin-line"');
  expect(pro).not.toContain("margin-teaser-line");
  expect(renderToStaticMarkup(createElement(ListingCard, { card, marginTeaser: false }))).toBe(renderToStaticMarkup(createElement(ListingCard, { card })));
});

// The photo spans three rows; a cost line makes the km line the fourth, which
// auto-placement would drop into the photo's column.
it("keeps the km / body / location line in the text column, with or without a cost line", () => {
  for (const costLine of [null, "Costo total estimado: USD 16.290 (ARS 21.188.000)"]) {
    const html = renderToStaticMarkup(createElement(ListingCard, { card, costLine }));
    const meta = html.match(/<p[^>]*data-testid="card-meta"[^>]*>/)?.[0] ?? "";
    expect(meta).toMatch(/class="[^"]*\bcol-start-2\b/);
    expect(meta.length).toBeGreaterThan(0);
  }
});
