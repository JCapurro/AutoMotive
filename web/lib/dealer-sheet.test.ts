import { deflateRawSync } from "node:zlib";

import { describe, expect, it } from "vitest";

import type { Catalog } from "@/lib/catalog";
import {
  cleanTable, currencyFor, guessColumns, importValues, matchVehicle, parseCsv, parseDay, parseMoney, parseXlsx,
  priceColumnGuessed, readSheet, rowAccepted, SHEET_MAX_BYTES, SheetError, sheetKind, toRows,
} from "@/lib/dealer-sheet";

const model = (name: string, trims: string[] = []) => ({ model: name, trims, yearFrom: null, yearTo: null, transmissions: [], fuels: [], bodyTypes: [] });
const CATALOG: Catalog = [
  { make: "Ford", models: [model("Focus", ["SE 2.0"]), model("Ka")] },
  { make: "Volkswagen", models: [model("Gol Trend"), model("Gol")] },
  { make: "Renault", models: [model("Kangoo")] },
];
const NOW = new Date("2026-11-18T12:00:00Z");

/** A minimal XLSX (ZIP with deflate): workbook, rels, shared strings and one sheet. */
function xlsx(parts: Record<string, string>): Uint8Array {
  const enc = new TextEncoder();
  const locals: Buffer[] = [];
  const centrals: Buffer[] = [];
  let offset = 0;
  for (const [name, text] of Object.entries(parts)) {
    const nameBytes = Buffer.from(enc.encode(name));
    const raw = Buffer.from(enc.encode(text));
    const data = deflateRawSync(raw);
    const local = Buffer.alloc(30);
    local.writeUInt32LE(0x04034b50, 0);
    local.writeUInt16LE(20, 4);
    local.writeUInt16LE(8, 8);
    local.writeUInt32LE(data.length, 18);
    local.writeUInt32LE(raw.length, 22);
    local.writeUInt16LE(nameBytes.length, 26);
    locals.push(local, nameBytes, data);
    const central = Buffer.alloc(46);
    central.writeUInt32LE(0x02014b50, 0);
    central.writeUInt16LE(20, 4);
    central.writeUInt16LE(20, 6);
    central.writeUInt16LE(8, 10);
    central.writeUInt32LE(data.length, 20);
    central.writeUInt32LE(raw.length, 24);
    central.writeUInt16LE(nameBytes.length, 28);
    central.writeUInt32LE(offset, 42);
    centrals.push(central, nameBytes);
    offset += 30 + nameBytes.length + data.length;
  }
  const cd = Buffer.concat(centrals);
  const eocd = Buffer.alloc(22);
  eocd.writeUInt32LE(0x06054b50, 0);
  eocd.writeUInt16LE(Object.keys(parts).length, 8);
  eocd.writeUInt16LE(Object.keys(parts).length, 10);
  eocd.writeUInt32LE(cd.length, 12);
  eocd.writeUInt32LE(offset, 16);
  return new Uint8Array(Buffer.concat([...locals, cd, eocd]));
}

describe("CSV", () => {
  it("reads ; with quotes, a BOM and CRLF", () => {
    const t = parseCsv('﻿Marca;Modelo;Precio\r\nFord;"Focus; SE";"$ 12.500.000"\r\nVW;"Gol ""Trend""";9000000\r\n');
    expect(t.headers).toEqual(["Marca", "Modelo", "Precio"]);
    expect(t.rows).toEqual([["Ford", "Focus; SE", "$ 12.500.000"], ["VW", 'Gol "Trend"', "9000000"]]);
  });

  it("reads , and skips a title row above the header", () => {
    const t = parseCsv("Stock noviembre\nmarca,modelo,año,km\nFord,Ka,2015,80000\n");
    expect(t.headers).toEqual(["marca", "modelo", "año", "km"]);
    expect(t.rows).toEqual([["Ford", "Ka", "2015", "80000"]]);
  });

  it("drops plate columns by header and by content", () => {
    expect(parseCsv("Marca;Dominio;Modelo\nFord;AB123CD;Ka\n").headers).toEqual(["Marca", "Modelo"]);
    const t = cleanTable({ headers: ["Marca", "", "Modelo"], rows: [["Ford", "AB123CD", "Ka"], ["VW", "ABC123", "Gol"], ["Ford", "AC456DE", "Focus"]] });
    expect(t.headers).toEqual(["Marca", "Modelo"]);
    expect(JSON.stringify(t.rows)).not.toContain("AB123CD");
  });

  it("refuses more than 500 cars and an empty sheet", () => {
    const rows = Array.from({ length: 501 }, (_, i) => `Ford;Ka;${2010 + (i % 10)}`).join("\n");
    expect(() => parseCsv(`Marca;Modelo;Año\n${rows}`)).toThrow(SheetError);
    try {
      parseCsv(`Marca;Modelo;Año\n${rows}`);
    } catch (e) {
      expect((e as SheetError).code).toBe("too_many_rows");
    }
    expect(() => parseCsv("")).toThrow(SheetError);
  });

  it("refuses a file over 1 MB and reads Latin-1", () => {
    expect(() => readSheet(new Uint8Array(SHEET_MAX_BYTES + 1), "csv")).toThrow(SheetError);
    const latin1 = new Uint8Array([...new TextEncoder().encode("Marca;Modelo;A"), 0xf1, ...new TextEncoder().encode("o\nFord;Ka;2015\n")]);
    expect(readSheet(latin1, "csv").headers).toEqual(["Marca", "Modelo", "Año"]);
  });
});

describe("XLSX", () => {
  const parts = {
    "xl/workbook.xml": '<workbook><sheets><sheet name="Stock" sheetId="1" r:id="rId1"/></sheets></workbook>',
    "xl/_rels/workbook.xml.rels": '<Relationships><Relationship Id="rId1" Type="worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
    "xl/sharedStrings.xml": "<sst><si><t>Marca</t></si><si><t>Modelo</t></si><si><t>Patente</t></si><si><t>Precio</t></si><si><t>Ford</t></si><si><t>Focus SE 2.0</t></si></sst>",
    "xl/worksheets/sheet1.xml":
      '<worksheet><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c><c r="C1" t="s"><v>2</v></c><c r="D1" t="s"><v>3</v></c></row>' +
      '<row r="2"><c r="A2" t="s"><v>4</v></c><c r="B2" t="s"><v>5</v></c><c r="C2" t="inlineStr"><is><t>AB123CD</t></is></c><c r="D2"><v>15000000</v></c></row></sheetData></worksheet>',
  };

  it("reads the first sheet with shared and inline strings, without the plate", () => {
    const t = parseXlsx(xlsx(parts));
    expect(t.headers).toEqual(["Marca", "Modelo", "Precio"]);
    expect(t.rows).toEqual([["Ford", "Focus SE 2.0", "15000000"]]);
    expect(sheetKind("stock.XLSX", null)).toBe("xlsx");
    expect(sheetKind("stock.csv", null)).toBe("csv");
    expect(sheetKind("stock.pdf", "application/pdf")).toBeNull();
  });

  it("says unreadable for a file that isn't a ZIP", () => {
    expect(() => parseXlsx(new TextEncoder().encode("not a zip at all, sorry"))).toThrow(SheetError);
  });
});

describe("values", () => {
  it("reads prices as agencies write them", () => {
    expect(parseMoney("$ 12.500.000")).toEqual({ amount: 12_500_000, currency: "ARS" });
    expect(parseMoney("12,5 M")).toEqual({ amount: 12_500_000, currency: null });
    expect(parseMoney("USD 14.000")).toEqual({ amount: 14_000, currency: "USD" });
    expect(parseMoney("u$s 14000")).toEqual({ amount: 14_000, currency: "USD" });
    expect(parseMoney("consultar")).toBeNull();
    expect(currencyFor(14_000, null)).toBe("USD");
    expect(currencyFor(9_000_000, null)).toBe("ARS");
    expect(currencyFor(14_000, "Pesos")).toBe("ARS");
  });

  it("reads days and refuses future ones", () => {
    expect(parseDay("18/11/2026", NOW)).toBe("2026-11-18");
    expect(parseDay("2026-10-01", NOW)).toBe("2026-10-01");
    expect(parseDay("31/02/2026", NOW)).toBeNull();
    expect(parseDay("01/01/2030", NOW)).toBeNull();
  });

  it("matches the catalog's spelling and keeps the trim", () => {
    expect(matchVehicle("vw", "gol trend 1.6", CATALOG)).toEqual({ make: "Volkswagen", model: "Gol Trend", trim: "1.6", inCatalog: true });
    expect(matchVehicle("Ford", "Focus se 2.0", CATALOG)).toEqual({ make: "Ford", model: "Focus", trim: "SE 2.0", inCatalog: true });
    expect(matchVehicle("Ford Ka", null, CATALOG)?.model).toBe("Ka");
    expect(matchVehicle("Lada", "Niva", CATALOG)?.inCatalog).toBe(false);
  });
});

describe("columns and rows", () => {
  it("takes an untitled amounts column when the price header is empty, and asks to confirm it", () => {
    const headers = ["Marca", "Modelo", "Año", "Venta", "", "Costo"];
    const rows = [["Ford", "Ka", "2015", "", "9.500.000", "7.000.000"], ["VW", "Gol", "2014", "", "8.000.000", "6.000.000"]];
    const map = guessColumns(headers, rows);
    expect(map.price).toBe(4);
    expect(priceColumnGuessed(headers, map)).toBe(true);
    expect(priceColumnGuessed(["Precio"], { price: 0 })).toBe(false);
  });

  it("never takes a cost column as the price", () => {
    const map = guessColumns(["Marca", "Modelo", "Precio compra"], [["Ford", "Ka", "7.000.000"]]);
    expect(map.price).toBeUndefined();
  });

  it("turns rows into items with their issues and sheet line", () => {
    const table = parseCsv("Marca;Modelo;Precio;Km\nRenault;Kangoo Confort 1.5 D 2011;9.000.000;120.000\nLada;Niva;5000000;\nFord;Ka;;\nRenault;Kangoo Confort 1.5 D 2011;9.000.000;120.000\n");
    const rows = toRows(table, guessColumns(table.headers, table.rows), CATALOG, NOW);
    expect(rows[0]).toMatchObject({ line: 2, issues: [], values: { make: "Renault", model: "Kangoo", trim: "Confort 1.5 D", year: 2011, price: 9_000_000, currency: "ARS", mileage_km: 120_000 } });
    expect(rows[1].issues).toEqual(expect.arrayContaining(["not_in_catalog", "no_year"]));
    expect(rows[2].issues).toEqual(expect.arrayContaining(["no_year", "no_price"]));
    expect(rows[3].issues).toEqual(["duplicate_in_sheet"]);
    expect(rows.map(rowAccepted)).toEqual([true, false, false, true]);
    expect(importValues(rows[0].values)).not.toHaveProperty("color");
  });
});
