import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * PRO-01 paso 2: the ready-to-send message on the listing page, its template
 * in Ajustes (saveContactTemplate, ContactTemplateForm) and the event of
 * copying it (trackContactMessage).
 */
const state = vi.hoisted(() => ({ updated: null as Record<string, unknown> | null, track: vi.fn() }));

vi.mock("server-only", () => ({}));
vi.mock("next/cache", () => ({ refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ redirect: vi.fn() }));
vi.mock("@/lib/auth", () => ({ requireUser: vi.fn().mockResolvedValue({ id: "account" }) }));
vi.mock("@/lib/events", () => ({ track: state.track }));
vi.mock("@/lib/supabase/server", () => ({
  createClient: async () => ({
    from: () => {
      const query: Record<string, unknown> = {};
      query.update = (row: Record<string, unknown>) => { state.updated = row; return query; };
      query.eq = () => Promise.resolve({ error: null });
      return query;
    },
  }),
}));

import { trackContactMessage } from "@/app/app/listings/actions";
import { saveContactTemplate } from "@/app/app/settings/actions";
import { SellerQuestions } from "@/components/app/seller-questions";
import { ContactTemplateForm } from "@/components/app/settings-forms";
import { renderContactMessage } from "@/lib/contact-message";
import { CONTACT_MESSAGE, CONTACT_TEMPLATE_ERROR } from "@/lib/copy";

beforeEach(() => {
  state.updated = null;
  state.track.mockClear();
});

describe("saveContactTemplate", () => {
  it("saves a linted template", async () => {
    expect(await saveContactTemplate("  Buenas, ¿tu {auto} sigue?\r\n{preguntas} ")).toEqual({ value: "Buenas, ¿tu {auto} sigue?\n{preguntas}" });
    expect(state.updated).toEqual({ contact_template: "Buenas, ¿tu {auto} sigue?\n{preguntas}" });
  });
  it("an empty one is null: the default template", async () => {
    expect(await saveContactTemplate("   ")).toEqual({ value: null });
    expect(state.updated).toEqual({ contact_template: null });
    expect(await saveContactTemplate(null)).toEqual({ value: null });
  });
  it("returns each rule's message and writes nothing", async () => {
    const cases: [string, keyof typeof CONTACT_TEMPLATE_ERROR][] = [
      ["¿Cuánto vale?", "forbidden"], ["Llamame al 11 5555-5555", "phone"], ["Mirá www.autos.com", "url"],
      ["Hola {modelo}", "placeholder"], ["a\nb\nc\nd\ne\nf\ng", "too_many_lines"], ["x".repeat(501), "too_long"],
    ];
    for (const [input, code] of cases) {
      expect(await saveContactTemplate(input)).toEqual({ error: CONTACT_TEMPLATE_ERROR[code] });
      expect(state.updated).toBeNull();
    }
    expect(await saveContactTemplate(42 as never)).toEqual({ error: CONTACT_TEMPLATE_ERROR.too_long });
  });
  it("records no event of its own", async () => {
    await saveContactTemplate("Hola");
    expect(state.track).not.toHaveBeenCalled();
  });
});

describe("trackContactMessage", () => {
  it("records contact_message_copied with how and whether the template is the user's", async () => {
    await trackContactMessage(7, "mailto", true);
    expect(state.track).toHaveBeenCalledWith(expect.anything(), "account", "contact_message_copied", { listing_id: 7, via: "mailto", custom_template: true });
  });
  it("ignores anything else", async () => {
    await trackContactMessage(7, "whatsapp" as never, false);
    await trackContactMessage(-1, "clipboard", false);
    expect(state.track).not.toHaveBeenCalled();
  });
});

describe("the listing page block", () => {
  const message = renderContactMessage(null, "Fiesta", 2017, ["¿Tenés historial de services?"]);
  const html = renderToStaticMarkup(createElement(SellerQuestions, {
    listingId: 7, text: "Hola, ¿cómo estás?",
    contact: { message, subject: "Consulta por tu Fiesta 2017", custom: false, outboundHref: "/app/listings/7/out" },
  }));
  it("shows the message, copy, the mailto without a recipient and the way to send it", () => {
    expect(html).toContain(CONTACT_MESSAGE.title);
    expect(html).toContain("Hola, vi tu Fiesta 2017 publicado.\n¿Lo seguís teniendo?\n¿Tenés historial de services?\n¿Cuándo se puede ver?");
    expect(html).toMatch(/> ?Copiar<\/button>/);
    expect(html).toMatch(/href="mailto:\?subject=Consulta%20por%20tu%20Fiesta%202017&amp;body=Hola%2C%20vi%20tu%20Fiesta%202017%20publicado\.%0D%0A/);
    expect(html).not.toMatch(/mailto:[^?"]/);
    expect(html).not.toMatch(/wa\.me|tel:/);
    expect(html).toContain(CONTACT_MESSAGE.note);
    expect(html).toContain('href="/app/listings/7/out"');
    // The full list keeps its button (acceptance.spec.ts).
    expect(html).toContain("¿Qué le pregunto al vendedor?");
  });
  it("without a message, as before", () => {
    const plain = renderToStaticMarkup(createElement(SellerQuestions, { listingId: 7, text: "Hola" }));
    expect(plain).not.toContain(CONTACT_MESSAGE.title);
  });
});

describe("Ajustes", () => {
  it("previews the default message and shows a stored one", () => {
    const empty = renderToStaticMarkup(createElement(ContactTemplateForm, { value: null }));
    expect(empty).toContain(CONTACT_MESSAGE.reset);
    expect(empty).toContain("Hola, vi tu Fiesta 2017 publicado.");
    const own = renderToStaticMarkup(createElement(ContactTemplateForm, { value: "Buenas, ¿tu {auto} sigue?" }));
    expect(own).toContain("Buenas, ¿tu Fiesta 2017 sigue?");
  });
  it("a template that fails the lint shows why and previews the default", () => {
    const bad = renderToStaticMarkup(createElement(ContactTemplateForm, { value: "Llamame al 11 5555-5555" }));
    expect(bad).toContain(CONTACT_TEMPLATE_ERROR.phone);
    expect(bad).toContain("Hola, vi tu Fiesta 2017 publicado.");
  });
});
