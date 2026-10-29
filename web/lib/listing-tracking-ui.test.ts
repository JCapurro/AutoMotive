import { createElement, type ComponentProps } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it, vi } from "vitest";

vi.mock("@/app/app/listings/actions", () => ({ setStatus: vi.fn(), setSaved: vi.fn(), recordPurchase: vi.fn(), setNote: vi.fn() }));

import { ListingTracking } from "@/components/app/listing-tracking";
import { selectableStatuses } from "@/lib/listing-tracking";

type Props = ComponentProps<typeof ListingTracking>;
const base: Props = { listingId: 7, status: "contacted", note: null, noteMaxChars: 500, profileId: 3 };
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

it("asks for a private note, capped at the configured length", () => {
  const markup = html({ noteMaxChars: 300 });
  const textarea = markup.match(/<textarea[^>]*>/)?.[0] ?? "";
  const id = markup.match(/<label[^>]*for="([^"]+)"[^>]*>Tu nota<\/label>/)?.[1];
  expect(textarea).toContain(`id="${id}"`);
  expect(textarea).toContain('placeholder="Qué hablaste, cuándo es la visita, qué falta revisar"');
  expect(textarea).toContain('maxLength="300"');
  expect(markup).toMatch(/<button[^>]*>Guardar nota<\/button>/);
  expect(markup).toContain("La nota es privada: no se la mostramos al vendedor ni a otros usuarios.");
  expect(markup).not.toMatch(/solo la ves vos/i);
});

it("shows a saved note as text, line breaks kept and markup escaped", () => {
  const markup = html({ note: "Llamé el martes\n<script>alert(1)</script>" });
  const shown = markup.match(/<p[^>]*data-testid="listing-note"[^>]*>([\s\S]*?)<\/p>/);
  expect(shown?.[0]).toContain("whitespace-pre-line");
  expect(shown?.[1]).toBe("Llamé el martes\n&lt;script&gt;alert(1)&lt;/script&gt;");
  expect(markup).not.toContain("<script>");
  expect(markup).toMatch(/<button[^>]*>Editar nota<\/button>/);
});
