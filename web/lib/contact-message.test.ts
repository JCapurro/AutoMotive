import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { autoText, contactSubject, mailtoHref, renderContactMessage } from "@/lib/contact-message";
import {
  ALLOWED_PHRASES,
  CONTACT_MESSAGE,
  CONTACT_TEMPLATE_ERROR,
  CONTACT_TEMPLATE_MAX_CHARS,
  CONTACT_TEMPLATE_MAX_LINES,
  FORBIDDEN_TERMS,
  foldText,
  lintContactTemplate,
} from "@/lib/copy";

/** PRO-01 paso 2: the twin of worker/intelligence/contact_message.py, against the same JSON. */
const FIXTURES = path.resolve(__dirname, "../../worker/tests/fixtures/contact_message");
type LintCase = { name: string; input: string | null; error: string | null; value: string | null };
type GoldenCase = { name: string; template: string | null; catalog_model: string | null; year: number | null; questions: string[]; text: string; subject: string };
const LINT = JSON.parse(readFileSync(path.join(FIXTURES, "lint.json"), "utf-8")) as {
  terms: string[]; allowed: string[]; max_chars: number; max_lines: number; cases: LintCase[];
};
const GOLDEN = JSON.parse(readFileSync(path.join(FIXTURES, "golden.json"), "utf-8")) as { default_template: string; cases: GoldenCase[] };

describe("lintContactTemplate (lint.json)", () => {
  it("reads the shared terms and limits", () => {
    expect([...new Set(FORBIDDEN_TERMS.map(foldText))].sort()).toEqual(LINT.terms);
    expect(ALLOWED_PHRASES).toEqual(LINT.allowed);
    expect([CONTACT_TEMPLATE_MAX_CHARS, CONTACT_TEMPLATE_MAX_LINES]).toEqual([LINT.max_chars, LINT.max_lines]);
  });
  for (const c of LINT.cases) {
    it(c.name, () => expect(lintContactTemplate(c.input)).toEqual({ value: c.value, error: c.error }));
  }
  it("has a message for every error", () => {
    for (const c of LINT.cases) if (c.error) expect(CONTACT_TEMPLATE_ERROR[c.error as keyof typeof CONTACT_TEMPLATE_ERROR]).toBeTruthy();
  });
  it("the default template passes", () => {
    expect(CONTACT_MESSAGE.default).toBe(GOLDEN.default_template);
    expect(lintContactTemplate(CONTACT_MESSAGE.default)).toEqual({ value: CONTACT_MESSAGE.default, error: null });
  });
});

describe("renderContactMessage (golden.json)", () => {
  for (const c of GOLDEN.cases) {
    it(c.name, () => {
      expect(renderContactMessage(c.template, c.catalog_model, c.year, c.questions)).toBe(c.text);
      expect(contactSubject(c.catalog_model, c.year)).toBe(c.subject);
    });
  }
  it("«auto» without a catalog model", () => {
    expect([autoText(null, 2017), autoText("  ", 2017), autoText("Fiesta", 2017)]).toEqual(["auto", "auto", "Fiesta 2017"]);
  });
});

describe("mailtoHref", () => {
  it("has no recipient, encodes each field and breaks lines with CRLF", () => {
    const body = "Hola & chau\n¿Sigue? #1 al 100%\nSaludos";
    expect(mailtoHref("Consulta por tu Fiesta 2017", body)).toBe(
      "mailto:?subject=Consulta%20por%20tu%20Fiesta%202017"
      + "&body=Hola%20%26%20chau%0D%0A%C2%BFSigue%3F%20%231%20al%20100%25%0D%0ASaludos",
    );
    expect(mailtoHref("a b", "c\r\nd")).toBe("mailto:?subject=a%20b&body=c%0D%0Ad");
    expect(mailtoHref("a b", "c d")).not.toContain("+");
  });
});
