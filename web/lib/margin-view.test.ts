import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { MARGIN } from "@/lib/copy";
import {
  asFewDealers,
  asMarginRef,
  asStoredMargin,
  marginDetail,
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
) as { cases: { name: string; margin_ref: MarginRef; payload: Record<string, unknown>; line: string }[] };
const byName = (name: string) => GOLDEN.cases.find((c) => c.name === name)!.margin_ref;
const MARGINS = GOLDEN.cases.filter((c) => c.payload.status === "ok");

describe("margin line (the worker's, byte for byte)", () => {
  it.each(GOLDEN.cases.map((c) => [c.name, c] as const))("%s", (_, c) => {
    if (c.payload.status === "ok") expect(marginPayload(c.margin_ref)).toEqual(c.payload);
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

describe("margin copy lint over every rendered variant", () => {
  it("never promises a result", () => {
    const fold = (t: string) => t.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase().replace("no con precios de venta", "");
    const texts = [...GOLDEN.cases.map((c) => c.line), ...MARGINS.flatMap((c) => marginDetail(c.margin_ref))];
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
    expect(marginDetail(byName("AMBA")).join(" ")).toContain("de CABA y Buenos Aires");
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
