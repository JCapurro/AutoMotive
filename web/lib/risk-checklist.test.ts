import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { FORBIDDEN_TERMS } from "./copy";
import {
  CHECKLIST_ITEMS,
  RISK_HEADER,
  RiskConfigInput,
  checklistItems,
  checklistText,
  emphasize,
  riskConfig,
} from "./risk-checklist";

const link = (url: string, label = "Sitio") => ({ label, url });
const EMPTY = { checklistEnabled: true, links: { dnrpa: null, patentes: [], infracciones: [], vtv: null, form_08: null } };
const BAD_URLS = [
  "http://example.test/a",
  "javascript:alert(1)",
  "data:text/html,hola",
  "//example.test/a",
  "https://user:pass@example.test/a",
  `https://example.test/${"a".repeat(300)}`,
  " https://example.test/a",
  "https:///nohost",
];

describe("riskConfig (PAR-02)", () => {
  it.each([undefined, null, [], "x", 3, { checklist_enabled: "yes" }, { links: [] }, { links: "x" }])(
    "falls back to a visible checklist without links for %j",
    (raw) => {
      expect(riskConfig(raw)).toEqual(EMPTY);
    },
  );

  it("only turns the checklist off with an explicit false", () => {
    expect(riskConfig({ checklist_enabled: false }).checklistEnabled).toBe(false);
    expect(riskConfig({ checklist_enabled: true }).checklistEnabled).toBe(true);
  });

  it.each(BAD_URLS)("drops the unsafe link %s and keeps the others", (url) => {
    const config = riskConfig({
      links: { dnrpa: link(url), vtv: link("https://vtv.example.test/"), patentes: [link(url), link("https://p.example.test/", "CABA")] },
    });
    expect(config.links.dnrpa).toBeNull();
    expect(config.links.vtv).toEqual(link("https://vtv.example.test/"));
    expect(config.links.patentes).toEqual([link("https://p.example.test/", "CABA")]);
  });

  it("drops a link with an empty label", () => {
    expect(riskConfig({ links: { form_08: link("https://f.example.test/", "  ") } }).links.form_08).toBeNull();
  });

  it("keeps a valid link with its label trimmed", () => {
    expect(riskConfig({ links: { dnrpa: link("https://d.example.test/x?y=1", " DNRPA ") } }).links.dnrpa).toEqual(
      link("https://d.example.test/x?y=1", "DNRPA"),
    );
  });
});

describe("RiskConfigInput (PAR-02)", () => {
  it("accepts the migration's row and unknown keys", () => {
    const value = { checklist_enabled: true, extra: 1, links: { dnrpa: null, patentes: [], infracciones: [], vtv: null, form_08: null, other: 2 } };
    const parsed = RiskConfigInput.safeParse(value);
    expect(parsed.success).toBe(true);
    expect(parsed.data).toEqual(value);
  });

  it("accepts valid links", () => {
    expect(
      RiskConfigInput.safeParse({ links: { dnrpa: link("https://d.example.test/"), infracciones: [link("https://i.example.test/", "PBA")] } }).success,
    ).toBe(true);
  });

  it.each(BAD_URLS)("rejects %s with a message", (url) => {
    const parsed = RiskConfigInput.safeParse({ links: { vtv: link(url) } });
    expect(parsed.success).toBe(false);
    expect(parsed.error?.issues[0]?.message).toMatch(/https/);
  });

  it("rejects an empty label and a non-boolean switch", () => {
    expect(RiskConfigInput.safeParse({ links: { patentes: [link("https://p.example.test/", "")] } }).success).toBe(false);
    expect(RiskConfigInput.safeParse({ checklist_enabled: "true" }).success).toBe(false);
  });
});

describe("checklistItems (PAR-02)", () => {
  it("has the seven approved items, none with links when nothing is loaded", () => {
    const items = checklistItems(EMPTY);
    expect(items.map((item) => item.text)).toEqual(CHECKLIST_ITEMS.map((item) => item.text));
    expect(items).toHaveLength(7);
    for (const item of items) {
      expect(item.official).toBeUndefined();
      expect(item.groups).toBeUndefined();
    }
  });

  it("puts each loaded link in its item and the jurisdictions as sublists", () => {
    const config = riskConfig({
      links: {
        dnrpa: link("https://d.example.test/"),
        vtv: link("https://v.example.test/"),
        form_08: link("https://f.example.test/"),
        patentes: [link("https://p.example.test/", "CABA")],
        infracciones: [link("https://i.example.test/", "PBA")],
      },
    });
    const byId = Object.fromEntries(checklistItems(config).map((item) => [item.id, item]));
    expect(byId.dominio.official?.url).toBe("https://d.example.test/");
    expect(byId.vtv.official?.url).toBe("https://v.example.test/");
    expect(byId.transferencia.official?.url).toBe("https://f.example.test/");
    expect(byId.deudas.groups).toEqual([
      { title: "Patentes", links: [link("https://p.example.test/", "CABA")] },
      { title: "Infracciones", links: [link("https://i.example.test/", "PBA")] },
    ]);
    expect(byId.prenda.official).toBeUndefined();
  });
});

describe("checklistText (PAR-02)", () => {
  it("is plain text with the title and every item, without links", () => {
    const text = checklistText("Ford Fiesta Titanium 2017");
    expect(text.split("\n")[0]).toBe("Antes de señar: Ford Fiesta Titanium 2017");
    expect(text).toContain(RISK_HEADER);
    for (const item of CHECKLIST_ITEMS) expect(text).toContain(`- ${item.text}`);
    expect(text.toLowerCase()).toContain("conviene verificar");
    expect(text).not.toMatch(/https?:|www\.|@/);
  });

  it("survives an empty or very long title", () => {
    expect(checklistText("").split("\n")[0]).toBe("Antes de señar");
    expect(checklistText("   ").split("\n")[0]).toBe("Antes de señar");
    const first = checklistText("Ford ".repeat(200)).split("\n")[0];
    expect(first.length).toBeLessThanOrEqual(140);
    expect(first.endsWith("…")).toBe(true);
  });
});

describe("emphasize (PAR-02)", () => {
  it("is on for much_cheaper or partial_price_suspect only", () => {
    expect(emphasize([{ id: "much_cheaper" }])).toBe(true);
    expect(emphasize([{ id: "no_owners" }, { id: "partial_price_suspect" }])).toBe(true);
    expect(emphasize([{ id: "no_owners" }])).toBe(false);
    expect(emphasize([])).toBe(false);
  });
});

describe("risk-checklist copy lint", () => {
  const source = readFileSync(path.join(__dirname, "risk-checklist.ts"), "utf-8").toLowerCase();

  it("never uses the §19 forbidden terms", () => {
    for (const term of FORBIDDEN_TERMS) {
      expect(new RegExp(`(^|[^\\p{L}\\p{N}_])${term}([^\\p{L}\\p{N}_]|$)`, "u").test(source), term).toBe(false);
    }
  });

  it("never promises that Ese Auto verified or guarantees anything", () => {
    for (const term of ["verificado por ese auto", "garantizado", "garantía", "seguro", "sin riesgo", "certificado"]) {
      expect(new RegExp(`(^|[^\\p{L}\\p{N}_])${term}([^\\p{L}\\p{N}_]|$)`, "u").test(source), term).toBe(false);
    }
  });
});
