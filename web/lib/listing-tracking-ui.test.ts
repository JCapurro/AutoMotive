import { createElement, type ComponentProps } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it, vi } from "vitest";

vi.mock("@/app/app/listings/actions", () => ({ setStatus: vi.fn(), setSaved: vi.fn(), recordPurchase: vi.fn() }));

import { ListingTracking } from "@/components/app/listing-tracking";
import { selectableStatuses } from "@/lib/listing-tracking";

type Props = ComponentProps<typeof ListingTracking>;
const base: Props = { listingId: 7, status: "contacted", profileId: 3 };
const html = (props: Partial<Props> = {}) => renderToStaticMarkup(createElement(ListingTracking, { ...base, ...props }));
const select = (markup: string) => markup.match(/<select[^>]*>[\s\S]*?<\/select>/)?.[0] ?? "";

it("is the «Seguimiento» block with an «Estado» select of the six statuses (X-01)", () => {
  const markup = html();
  expect(markup).toContain("Seguimiento");
  const id = markup.match(/<label[^>]*for="([^"]+)"[^>]*>Estado<\/label>/)?.[1];
  expect(id).toBeTruthy();
  expect(select(markup)).toContain(`id="${id}"`);
  const options = [...select(markup).matchAll(/<option[^>]*value="([^"]+)"[^>]*>([^<]*)<\/option>/g)].map((m) => ({ value: m[1], label: m[2] }));
  expect(options).toEqual(selectableStatuses());
});

it("locks a purchased listing and says why", () => {
  const markup = html({ status: "purchased" });
  expect(select(markup)).toMatch(/<select[^>]*disabled=""/);
  expect(markup).toContain("la compra no se puede deshacer desde acá");
  expect(select(html())).not.toMatch(/<select[^>]*disabled=""/);
});

it("has no private note: no textarea, no «Tu nota», nothing to save (Juan 02/11)", () => {
  const markup = html();
  expect(markup).not.toMatch(/<textarea/i);
  expect(markup).not.toMatch(/nota/i);
  expect(markup).not.toContain("listing-note");
  expect(markup).not.toMatch(/<button[^>]*>Guardar/);
  // A note left in the row by older versions is never passed in nor drawn.
  expect(html({ note: "vieja" } as Partial<Props>)).not.toContain("vieja");
});
