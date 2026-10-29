import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it, vi } from "vitest";

vi.mock("@/app/app/listings/actions", () => ({ setStatus: vi.fn(), setSaved: vi.fn(), recordPurchase: vi.fn(), setNote: vi.fn() }));

import { ListingActions } from "@/components/app/listing-actions";
import type { InteractionStatus } from "@/lib/copy";

const html = (status: InteractionStatus, saved: boolean) =>
  renderToStaticMarkup(createElement(ListingActions, { listingId: 7, status, saved, outboundHref: "/out" }));
const saveButton = (markup: string) => markup.match(/<button[^>]*aria-pressed="(true|false)"[^>]*>.*?<\/button>/)?.[0] ?? "";

it("shows Guardada for a contacted listing that is saved (X-01: saving never lowers a follow-up)", () => {
  const button = saveButton(html("contacted", true));
  expect(button).toContain('aria-pressed="true"');
  expect(button).toContain("Guardada");
});

it("offers Guardar on a contacted listing that is not saved", () => {
  const button = saveButton(html("contacted", false));
  expect(button).toContain('aria-pressed="false"');
  expect(button).toContain("Guardar");
  expect(button).not.toContain("Guardada");
});

it("keeps Guardada for an interested, saved listing", () => {
  const button = saveButton(html("interested", true));
  expect(button).toContain('aria-pressed="true"');
  expect(button).toContain("Guardada");
});
