import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { MARGIN } from "@/lib/copy";
import { asMarginRef, marginDetail, marginHeadline, marginLine, marginPayload, type MarginRef, pctText, round10, signed } from "@/lib/margin-view";

// PRO-02: the vectors shared with worker/tests/test_margin.py (GoldenTests).
const GOLDEN = JSON.parse(
  readFileSync(path.resolve(__dirname, "../../worker/tests/fixtures/margin/golden.json"), "utf-8"),
) as { cases: { name: string; margin_ref: MarginRef; payload: Record<string, unknown>; line: string }[] };
const byName = (name: string) => GOLDEN.cases.find((c) => c.name === name)!.margin_ref;

describe("margin line (the worker's, byte for byte)", () => {
  it.each(GOLDEN.cases.map((c) => [c.name, c] as const))("%s", (_, c) => {
    expect(marginPayload(c.margin_ref)).toEqual(c.payload);
    expect(marginLine(c.margin_ref)).toBe(c.line);
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

describe("margin copy lint over every rendered variant", () => {
  it("never promises a result", () => {
    const fold = (t: string) => t.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase().replace("no con precios de venta", "");
    const texts = GOLDEN.cases.flatMap((c) => [c.line, ...marginDetail(c.margin_ref)]);
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
    expect(detail).toContain("Margen sobre la mediana: 6 % a 7 %.");
    expect(detail).toContain(MARGIN.excludes);
    expect(detail).toContain(MARGIN.published);
    expect(detail).toContain("Parámetros al 30/10.");
  });

  it("without the place: no transfer and why, never another zone", () => {
    const detail = marginDetail(byName("sin localidad"));
    expect(detail).toContain("Transferencia: no se descuenta porque tu búsqueda no tiene localidad.");
    expect(detail.join(" ")).not.toMatch(/CABA|Buenos Aires|resto del país/);
  });

  it("names AMBA's two jurisdictions and the rest of the country's range", () => {
    expect(marginDetail(byName("AMBA")).join(" ")).toContain("de CABA y Buenos Aires");
    expect(marginDetail(byName("resto del país"))).toContain(MARGIN.rest);
  });

  it("a cash price and missing reconditioning", () => {
    expect(marginDetail(byName("de contado"))).toContain("Precio de compra (de contado): USD 15.380.");
    expect(marginDetail(byName("sin acondicionamiento"))).toContain(MARGIN.reconditioningMissing);
  });
});
