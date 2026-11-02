import { readFileSync } from "node:fs";
import path from "node:path";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { MarginEstimate, MarginTeaser } from "@/components/app/margin-estimate";

import { MARGIN, MARGIN_TEASER } from "@/lib/copy";
import {
  asFewDealers,
  asMarginRef,
  asStoredMargin,
  marginDetail,
  marginCardLine,
  marginHeadline,
  marginLine,
  marginPayload,
  type MarginRef,
  pctText,
  round10,
  signed,
} from "@/lib/margin-view";

// PRO-02: the vectors shared with worker/tests/test_margin.py (GoldenTests).
const GOLDEN = JSON.parse(
  readFileSync(path.resolve(__dirname, "../../worker/tests/fixtures/margin/golden.json"), "utf-8"),
) as {
  cases: { name: string; implausible?: boolean; margin_ref: MarginRef; payload: Record<string, unknown> | null; line: string | null }[];
};
const byName = (name: string) => GOLDEN.cases.find((c) => c.name === name)!.margin_ref;
const MARGINS = GOLDEN.cases.filter((c) => c.payload?.status === "ok");
// Shown: a margin or «not enough dealers»; the implausible ones are stored refs from before the guard.
const SHOWN = GOLDEN.cases.filter((c) => !c.implausible);
const IMPLAUSIBLE = GOLDEN.cases.filter((c) => c.implausible);

describe("margin line (the worker's, byte for byte)", () => {
  it.each(GOLDEN.cases.map((c) => [c.name, c] as const))("%s", (_, c) => {
    if (c.payload?.status === "ok") expect(marginPayload(c.margin_ref)).toEqual(c.payload);
    expect(marginLine(c.margin_ref)).toBe(c.line);
  });

  it("without enough dealers, says so (Juan, 02/11)", () => {
    const few = byName("pocas agencias");
    expect(asFewDealers(few)).toEqual(few);
    expect(asMarginRef(few)).toBeNull();
    expect(asStoredMargin(few)).toEqual(few);
    expect(marginLine(few)).toBe("Margen estimado: no hay suficientes agencias publicando este modelo para estimarlo (n = 2, mínimo 5)");
    expect(marginLine({ status: "few_dealers", dealer_n: 2 })).toBeNull();
    expect(marginLine({ ...byName("pool CABA"), status: "other" })).toBeNull();
  });

  it("pool of 6 dealers and 4 private sellers: the dealers' median", () => {
    const ref = byName("pool CABA");
    expect([ref.dealer_median, ref.dealer_n, ref.n]).toEqual([18000, 6, 10]);
    expect(marginLine(ref)).toBe(
      "Margen bruto estimado: USD 1.210 a 1.230 (contra la mediana de USD 18.000 a la que publican las agencias este modelo, n = 6; descuenta acondicionamiento del 5 % y transferencia; sin impuestos)",
    );
  });

  it("nothing for a missing or unknown margin", () => {
    for (const value of [null, undefined, {}, { gross_margin_usd: { min: 1 } }, "x"]) expect(marginLine(value)).toBeNull();
    expect(asMarginRef({ ...byName("pool CABA"), dealer_n: "6" })).toBeNull();
  });

  it("formats signs, the median and the percentage like the worker", () => {
    expect([signed(-300), signed(-1300), signed(1400), signed(0)]).toEqual(["-300", "-1.300", "1.400", "0"]);
    expect([round10(14495), round10(14505), round10(18000)]).toEqual([14500, 14510, 18000]);
    expect([pctText(5), pctText(5.5), pctText(5.25)]).toEqual(["5", "5,5", "5,25"]);
  });

  it("a single number when the margin has no range", () => {
    const line = marginHeadline({ ...marginPayload(byName("sin localidad")) });
    expect(line).toContain("Margen bruto estimado: USD 1.850 (");
  });
});

describe("margin card line (Juan, 02/11: short in the result cards)", () => {
  it("a range: the same USD range as the full line and the dealers' n", () => {
    expect(marginCardLine(byName("pool CABA"))).toBe("Margen bruto estimado: USD 1.210 a 1.230 (n\u00a0=\u00a06\u00a0agencias)");
  });

  it("a single value", () => {
    expect(marginCardLine(byName("sin localidad"))).toBe("Margen bruto estimado: USD 1.850 (n\u00a0=\u00a06\u00a0agencias)");
  });

  it("a negative margin keeps its sign", () => {
    expect(marginCardLine(byName("negativo"))).toBe("Margen bruto estimado: USD -1.790 a -1.770 (n\u00a0=\u00a06\u00a0agencias)");
  });

  it("few dealers: short and honest", () => {
    expect(marginCardLine(byName("pocas agencias"))).toBe("Margen estimado: pocas agencias para estimarlo (n\u00a0=\u00a02)");
    expect(marginCardLine({ status: "few_dealers", dealer_n: 2 })).toBeNull();
  });

  it("starts like the full line, which keeps the median, the costs and «sin impuestos»", () => {
    for (const c of SHOWN) {
      const card = marginCardLine(c.margin_ref)!;
      if (c.payload?.status === "ok") expect(c.line!.startsWith(card.replace(/ \(n\u00a0=\u00a0\d+\u00a0agencias\)$/, " ("))).toBe(true);
      expect(card.length).toBeLessThan(c.line!.length);
    }
    expect(marginLine(byName("pool CABA"))).toContain("contra la mediana de USD 18.000");
    expect(marginCardLine(byName("pool CABA"))).not.toContain("mediana");
  });

  it("the listing page keeps the full line, with or without enough dealers", () => {
    const html = renderToStaticMarkup(createElement(MarginEstimate, { margin: byName("pool CABA") }));
    // The decision panel sets the amount apart; the headline's text is still the whole line.
    const headline = html.match(/<p[^>]*data-testid="margin-estimate-headline"[^>]*>[\s\S]*?<\/p>/)![0].replace(/<[^>]+>/g, "");
    expect(headline).toBe(marginLine(byName("pool CABA"))!);
    expect(html).toMatch(/<span class="type-figure[^"]*">USD [^<]+<\/span>/);
    expect(html).not.toContain("agencias)");
    const few = renderToStaticMarkup(createElement(MarginEstimate, { margin: asFewDealers(byName("pocas agencias")) }));
    expect(few).toContain("Margen estimado: no hay suficientes agencias publicando este modelo para estimarlo (n = 2, mínimo 5)");
    expect(few).not.toContain("pocas agencias para estimarlo");
  });

  it("nothing for a missing or unknown margin", () => {
    for (const value of [null, undefined, {}, { gross_margin_usd: { min: 1 } }, "x", { ...byName("pool CABA"), status: "other" }]) {
      expect(marginCardLine(value)).toBeNull();
    }
  });
});

describe("the other plans' preview (Juan, 02/11: in view, unreadable in any way)", () => {
  const html = renderToStaticMarkup(createElement(MarginTeaser));
  const text = (markup: string) => markup.replace(/<[^>]+>/g, "");

  it("has no figure to read: every digit is an X, blur or not", () => {
    expect(html).toContain('data-testid="margin-teaser"');
    expect(text(html)).not.toMatch(/\d/);
    expect(Object.values(MARGIN_TEASER).join(" ")).not.toMatch(/\d/);
  });

  it("the placeholder is blurred, not selectable and hidden from screen readers, which hear why", () => {
    const blurred = html.match(/<span aria-hidden="true" class="([^"]*)">([\s\S]*?)<\/span><\/p>/)!;
    expect(blurred[1].split(" ")).toEqual(expect.arrayContaining(["blur-[5px]", "select-none", "pointer-events-none"]));
    expect(text(blurred[2])).toBe(`${MARGIN_TEASER.figure}${MARGIN_TEASER.note}`);
    expect(html).toContain(`<span class="sr-only">: ${MARGIN_TEASER.hidden}</span>`);
  });

  it("says what Pro shows and links to the plans", () => {
    expect(html).toContain(MARGIN_TEASER.line);
    expect(html).toMatch(new RegExp(`<a [^>]*href="/app/pro"[^>]*>${MARGIN_TEASER.cta}</a>`));
  });
});

describe("an implausible price has no margin (asking above 3x or below 0,4x the dealers' median)", () => {
  it("the golden has the cases above, below and on the bounds", () => {
    expect(IMPLAUSIBLE.map((c) => c.name)).toEqual([
      "implausible: ARS cargado como USD",
      "implausible: apenas arriba de 3x",
      "implausible: abajo de 0,4x",
    ]);
    expect(byName("en el borde de arriba (3x)").asking_usd).toBe(3 * byName("en el borde de arriba (3x)").dealer_median);
    expect(byName("en el borde de abajo (0,4x)").asking_usd).toBe(0.4 * byName("en el borde de abajo (0,4x)").dealer_median);
  });

  it.each(IMPLAUSIBLE.map((c) => [c.name, c] as const))("%s: no line, no card line, no detail, nothing rendered", (_, c) => {
    expect(c.payload).toBeNull();
    expect(c.line).toBeNull();
    expect(asMarginRef(c.margin_ref)).toBeNull();
    expect(asStoredMargin(c.margin_ref)).toBeNull();
    expect(marginLine(c.margin_ref)).toBeNull();
    expect(marginCardLine(c.margin_ref)).toBeNull();
    expect(marginDetail(c.margin_ref)).toEqual([]);
    expect(renderToStaticMarkup(createElement(MarginEstimate, { margin: c.margin_ref }))).toBe("");
  });

  it("the bounds are plausible: their margin is shown", () => {
    expect(marginCardLine(byName("en el borde de arriba (3x)"))).toBe("Margen bruto estimado: USD -38.700 (n\u00a0=\u00a06\u00a0agencias)");
    expect(marginCardLine(byName("en el borde de abajo (0,4x)"))).toBe("Margen bruto estimado: USD 10.440 (n\u00a0=\u00a06\u00a0agencias)");
    expect(marginDetail(byName("en el borde de abajo (0,4x)")).length).toBeGreaterThan(0);
  });

  it("the production case: a VW Bora «USD 600.000» against a median of USD 8.038", () => {
    const bora = byName("implausible: ARS cargado como USD");
    expect([bora.asking_usd, bora.dealer_median]).toEqual([600000, 8038]);
    expect(bora.gross_margin_usd.min).toBeLessThan(-600000);
    expect(marginLine(bora)).toBeNull();
  });

  it("a ref with its own bounds is checked against them; without, against 0,4 and 3", () => {
    const top = byName("en el borde de arriba (3x)");
    expect(top.plausible_ratio).toEqual({ min: 0.4, max: 3 });
    expect(marginLine({ ...top, plausible_ratio: { min: 0.4, max: 2.5 } })).toBeNull();
    expect(marginLine({ ...top, plausible_ratio: undefined })).not.toBeNull();
    expect(marginLine({ ...top, plausible_ratio: { min: 0, max: 99 } })).not.toBeNull(); // invalid bounds: the default
    expect(marginLine({ ...top, asking_usd: 54000.02 })).toBeNull();
    expect(marginLine({ ...top, asking_usd: 54000.01 })).not.toBeNull(); // the worker's cent of slack
    expect(marginLine({ ...top, asking_usd: undefined })).toBeNull();
  });
});

describe("margin copy lint over every rendered variant", () => {
  it("never promises a result", () => {
    const fold = (t: string) => t.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase().replace("no con precios de venta", "");
    const texts = [
      ...SHOWN.map((c) => c.line!),
      ...SHOWN.map((c) => marginCardLine(c.margin_ref)!),
      ...MARGINS.flatMap((c) => marginDetail(c.margin_ref)),
      ...Object.values(MARGIN_TEASER),
    ];
    for (const text of texts) {
      for (const term of ["vale", "ganancia", "garantiz", "rentab", "asegur", "seguro que", "vas a ganar", "precio de venta", "precios de venta"]) {
        expect(fold(text).includes(term), `${text}: ${term}`).toBe(false);
      }
    }
  });
});

describe("margin detail (listing page)", () => {
  it("says what it subtracts, in numbers, and what it is not", () => {
    const detail = marginDetail(byName("pool CABA"));
    expect(detail).toContain("Mediana de agencias: USD 18.000 (n = 6 de 10 comparables, misma caja).");
    expect(detail).toContain("Precio de compra: USD 15.380.");
    expect(detail).toContain("Acondicionamiento: USD 770 (5 % del precio, mínimo USD 300).");
    expect(detail).toContain("Transferencia: USD 620 a 630 (arancel, sellos y formularios de CABA, según tu búsqueda).");
    expect(detail).toContain("Lo que cuesta comprar el auto: USD 16.770 a 16.790 (precio de compra más los costos descontados).");
    expect(detail).toContain("Margen sobre lo que cuesta comprar el auto: 7 % a 8 %.");
    expect(detail).toContain(MARGIN.excludes);
    expect(detail).toContain(MARGIN.published);
    expect(detail).toContain("Parámetros al 30/10.");
  });

  it("without the place: no transfer and why, never another zone", () => {
    const detail = marginDetail(byName("sin localidad"));
    expect(detail).toContain("Transferencia: no se descuenta porque tu búsqueda no tiene localidad.");
    expect(detail.join(" ")).not.toMatch(/CABA|Buenos Aires|resto del país/);
  });

  it("names AMBA's two jurisdictions; outside CABA and Buenos Aires, no transfer and why", () => {
    expect(marginDetail(byName("AMBA")).join(" ")).toContain("de CABA o Provincia de Buenos Aires");
    const rest = marginDetail(byName("resto del país"));
    expect(rest).toContain("Transferencia: no se descuenta porque no tenemos los valores oficiales de tu provincia.");
    expect(rest.join(" ")).not.toMatch(/Córdoba|Santa Fe|Mendoza|resto del país/);
    expect(marginDetail(byName("CABA y Córdoba"))).toContain(
      "Transferencia: no se descuenta porque no tenemos los valores oficiales de todas las provincias de tu búsqueda.",
    );
  });

  it("a single percentage when the cost has no range", () => {
    expect(marginDetail(byName("sin localidad"))).toContain("Margen sobre lo que cuesta comprar el auto: 11 %.");
    expect(marginDetail(byName("sin localidad"))).toContain("Lo que cuesta comprar el auto: USD 16.150 (precio de compra más los costos descontados).");
  });

  it("a cash price and missing reconditioning", () => {
    expect(marginDetail(byName("de contado"))).toContain("Precio de compra (de contado): USD 15.380.");
    expect(marginDetail(byName("sin acondicionamiento"))).toContain(MARGIN.reconditioningMissing);
  });
});
