import { describe, expect, it } from "vitest";

import { CSV_COLUMNS, csvDate, csvNumber, csvText, exportFilename, resultsCsv, type ExportRow } from "@/lib/results-csv";

const ROW: ExportRow = {
  search_name: "Ford Fiesta", detected_at: "2026-10-14T18:30:00Z", source_name: "Mercado Libre",
  title: "Ford Fiesta 1.6 Titanium", version: "Titanium", year: 2017, mileage_km: 112000, price: 10300,
  currency: "USD", comparables_pct: -12, score: 84, url: "https://example.test/fiesta",
};

/** How a spreadsheet splits the file: RFC 4180 with semicolons. */
function parse(csv: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [], cell = "", quoted = false;
  for (let i = 0; i < csv.length; i++) {
    const c = csv[i];
    if (quoted) {
      if (c === '"' && csv[i + 1] === '"') { cell += '"'; i++; }
      else if (c === '"') quoted = false;
      else cell += c;
    } else if (c === '"') quoted = true;
    else if (c === ";") { row.push(cell); cell = ""; }
    else if (c === "\r" && csv[i + 1] === "\n") { row.push(cell); rows.push(row); row = []; cell = ""; i++; }
    else cell += c;
  }
  return rows;
}

describe("resultsCsv", () => {
  it("starts with a BOM and uses semicolons and CRLF, header first", () => {
    const csv = resultsCsv([ROW]);
    expect(csv.charCodeAt(0)).toBe(0xfeff);
    expect(csv.endsWith("\r\n")).toBe(true);
    const [header, line] = parse(csv.slice(1));
    expect(header).toEqual([...CSV_COLUMNS]);
    expect(line).toEqual(["Ford Fiesta", "2026-10-14 15:30", "Mercado Libre", "Ford Fiesta 1.6 Titanium", "Titanium",
      "2017", "112000", "10300", "USD", "-12", "84", "https://example.test/fiesta"]);
  });

  it("keeps separators, quotes and line breaks inside their cell", () => {
    const tricky = { ...ROW, title: 'Fiesta; "impecable"\núnico dueño', version: null, comparables_pct: null };
    const [, line] = parse(resultsCsv([tricky]).slice(1));
    expect(line).toHaveLength(CSV_COLUMNS.length);
    expect(line[3]).toBe('Fiesta; "impecable"\núnico dueño');
    expect(line[4]).toBe("");
    expect(line[9]).toBe("");
  });

  it("only the header without results", () => {
    expect(parse(resultsCsv([]).slice(1))).toEqual([[...CSV_COLUMNS]]);
  });
});

describe("cells", () => {
  it("never lets a spreadsheet run a formula", () => {
    expect(csvText("=HYPERLINK(\"x\")")).toBe("\"'=HYPERLINK(\"\"x\"\")\"");
    expect(csvText("+54 11")).toBe("'+54 11");
    expect(csvText("-oferta-")).toBe("'-oferta-");
    expect(csvText("@vendedor")).toBe("'@vendedor");
  });

  it("numbers use the decimal comma and no thousands separator", () => {
    expect(csvNumber(10300)).toBe("10300");
    expect(csvNumber(12.5)).toBe("12,5");
    expect(csvNumber(-12)).toBe("-12");
    expect(csvNumber(null)).toBe("");
    expect(csvNumber(Number.NaN)).toBe("");
  });

  it("dates in Argentine time", () => {
    expect(csvDate("2026-10-15T02:10:00Z")).toBe("2026-10-14 23:10");
    expect(csvDate(null)).toBe("");
    expect(csvDate("no es fecha")).toBe("");
  });
});

describe("exportFilename", () => {
  it("names the file after the search and the Argentine date", () => {
    const now = new Date("2026-10-15T01:00:00Z");
    expect(exportFilename("Peugeot 208 Allure — AMBA", now)).toBe("ese-auto-peugeot-208-allure-amba-2026-10-14.csv");
    expect(exportFilename(null, now)).toBe("ese-auto-busquedas-2026-10-14.csv");
    expect(exportFilename("¿¡!?", now)).toBe("ese-auto-busqueda-2026-10-14.csv");
  });
});
