import { describe, expect, it } from "vitest";

import { missingData, missingDataText } from "@/lib/dealer-data-quality";
import { sheetKindOf, stockReadState, tableToText } from "@/lib/dealer-stock-photo";

const car = (km: number | null, trim: string | null) => ({ km, trim });

describe("missing data of the agency's cars", () => {
  it("counts cars without km (null or 0) and without trim (null or blank)", () => {
    expect(missingData([car(90000, "S"), car(null, "S"), car(0, " "), car(50000, null)])).toEqual({ total: 4, km: 2, trim: 2 });
  });

  it("says it loudly, and nothing when every car has both", () => {
    expect(missingDataText([car(90000, "S"), car(1, "X")])).toBeNull();
    expect(missingDataText([])).toBeNull();
    expect(missingDataText([car(null, "S"), car(null, null), car(9, "S")])).toBe("2 de 3 autos no tienen kilómetros y 1 no tiene versión.");
    expect(missingDataText([car(null, "S"), car(9, "S")])).toBe("1 de 2 autos no tiene kilómetros.");
    expect(missingDataText([car(9, null)])).toBe("1 de 1 auto no tiene versión.");
  });
});

describe("a spreadsheet for the reader", () => {
  it("is the table as text, one row per line, with cells that cannot break a line or a column", () => {
    expect(tableToText({ headers: ["Auto", "Precio"], rows: [["Focus 1.6 S 2016\nnafta; 85 mil", "USD 9.800"], ["", ""], ["Gol", "$ 9.000.000"]] }))
      .toBe("Auto ; Precio\nFocus 1.6 S 2016 nafta 85 mil ; USD 9.800\nGol ; $ 9.000.000");
    expect(tableToText({ headers: ["", ""], rows: [["Gol", "1"]] })).toBe("Gol ; 1");
  });

  it("is not sent when it is empty or longer than one read", () => {
    expect(tableToText({ headers: ["Auto"], rows: [] })).toBeNull();
    expect(tableToText({ headers: ["Auto"], rows: Array.from({ length: 201 }, () => ["Gol"]) })).toBeNull();
    expect(tableToText({ headers: ["Auto"], rows: Array.from({ length: 200 }, () => ["Gol"]) })).not.toBeNull();
  });

  it("comes back as a spreadsheet, not as a photo", () => {
    expect(sheetKindOf("text/csv")).toBe("csv");
    expect(sheetKindOf("application/pdf")).toBe("pdf");
    expect(sheetKindOf("image/jpeg")).toBe("photo");
    const done = stockReadState({ status: "done", output: { readable: true, media_type: "text/csv", headers: ["Marca"], rows: [["Ford"]] } });
    expect(done).toEqual({ state: "ok", table: { headers: ["Marca"], rows: [["Ford"]] }, kind: "csv", truncated: false });
  });
});
