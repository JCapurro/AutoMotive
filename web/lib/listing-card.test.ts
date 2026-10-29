import { createElement, type ComponentProps } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";

import { ListingCard } from "@/components/app/listing-card";

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
