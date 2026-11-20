import type { Catalog } from "@/lib/catalog";

/**
 * node:zlib, fetched when an XLSX is read (only on the server): no static
 * import, so the client components that use this module's labels don't pull
 * a Node built-in into the browser bundle.
 */
function inflateRaw(data: Uint8Array, maxOutputLength: number): Uint8Array {
  const zlib = process.getBuiltinModule?.("node:zlib") as typeof import("node:zlib") | undefined;
  if (!zlib) throw new SheetError("unreadable");
  return zlib.inflateRawSync(data, { maxOutputLength });
}

/**
 * The agency's stock spreadsheet (spec §5), read in the web with no new
 * dependency: CSV by hand, XLSX as a ZIP with node:zlib (server only). Pure (no I/O); the
 * server action reads the file and calls these. Plate columns (dominio,
 * patente, placa) are dropped while reading and never leave this module.
 */

export type SheetKind = "csv" | "xlsx";
export type SheetTable = { headers: string[]; rows: string[][] };
export type SheetField =
  | "make" | "model" | "trim" | "year" | "mileage_km" | "price" | "currency"
  | "transmission" | "fuel" | "color" | "in_stock_since" | "title" | "description";
export type ColumnMap = Partial<Record<SheetField, number>>;
export type ItemValues = {
  make: string | null;
  model: string | null;
  trim: string | null;
  year: number | null;
  mileage_km: number | null;
  price: number | null;
  currency: "ARS" | "USD" | null;
  transmission: "manual" | "automatic" | null;
  fuel: string | null;
  color: string | null;
  in_stock_since: string | null;
  title: string | null;
  description: string | null;
};
export type SheetIssue =
  | "no_make" | "no_model" | "not_in_catalog" | "no_year" | "no_price"
  | "price_far_from_market" | "price_looks_like_cost" | "duplicate_in_sheet";
export type SheetRow = { line: number; values: ItemValues; issues: SheetIssue[] };

export const SHEET_MAX_BYTES = 1024 * 1024;
export const SHEET_MAX_ROWS = 500;
export const SHEET_FIELDS: SheetField[] = [
  "make", "model", "trim", "year", "mileage_km", "price", "currency", "transmission", "fuel", "color", "in_stock_since", "title", "description",
];

/** Columns with these headers are dropped on read: the plate never gets stored. */
export const PLATE_HEADERS = /dominio|patente|placa/i;
/** AA123BB (2016+) or ABC123 (1995–2016): a column mostly of these is a plate column even without its header. */
const PLATE_VALUE = /^(?:[a-z]{2}\s?-?\d{3}\s?-?[a-z]{2}|[a-z]{3}\s?-?\d{3})$/i;

export class SheetError extends Error {
  constructor(public code: "too_big" | "too_many_rows" | "empty" | "unreadable") {
    super(code);
  }
}

export const SHEET_ERROR_TEXT: Record<SheetError["code"], string> = {
  too_big: "La planilla pesa más de 1 MB.",
  too_many_rows: "La planilla tiene más de 500 autos.",
  empty: "La planilla está vacía.",
  unreadable: "No pudimos leer la planilla. Guardala como CSV o XLSX y probá de nuevo.",
};

export function fold(text: string): string {
  return text.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}

// ---------------------------------------------------------------------------
// Reading
// ---------------------------------------------------------------------------

/** Drops plate columns (by header or by content) and fully empty rows; trims every cell. */
export function cleanTable(table: SheetTable): SheetTable {
  const width = Math.max(table.headers.length, ...table.rows.map((r) => r.length), 0);
  const headers = Array.from({ length: width }, (_, i) => (table.headers[i] ?? "").trim());
  const rows = table.rows
    .map((r) => Array.from({ length: width }, (_, i) => (r[i] ?? "").trim()))
    .filter((r) => r.some((c) => c !== ""));
  const keep = headers.map((h, i) => {
    if (PLATE_HEADERS.test(h)) return false;
    const values = rows.map((r) => r[i]).filter((v) => v !== "");
    const plates = values.filter((v) => PLATE_VALUE.test(v)).length;
    return !(values.length >= 2 && plates / values.length >= 0.6);
  });
  return {
    headers: headers.filter((_, i) => keep[i]),
    rows: rows.map((r) => r.filter((_, i) => keep[i])),
  };
}

/** The header row: the first of the first 10 with two or more known column names (a title row above it is skipped), else the first. */
function splitHeader(records: string[][]): SheetTable {
  const known = (r: string[]) => r.filter((c) => {
    const h = fold(c);
    return h !== "" && HEADER_WORDS.some(([, re]) => re.test(h));
  }).length;
  const at = records.slice(0, 10).findIndex((r) => known(r) >= 2);
  const i = at < 0 ? 0 : at;
  return { headers: records[i] ?? [], rows: records.slice(i + 1) };
}

function checkRows(table: SheetTable): SheetTable {
  if (!table.headers.length && !table.rows.length) throw new SheetError("empty");
  if (table.rows.length > SHEET_MAX_ROWS) throw new SheetError("too_many_rows");
  return table;
}

function detectSeparator(text: string): string {
  // The first 10 lines, not only the first: a title row above the header («Stock noviembre») has no separators.
  const lines = text.split(/\r?\n/).filter((l) => l.trim() !== "").slice(0, 10);
  let best = ",";
  let bestCount = 0;
  for (const sep of [";", ",", "\t"]) {
    let count = 0;
    for (const line of lines) {
      let inLine = 0;
      let quoted = false;
      for (const ch of line) {
        if (ch === '"') quoted = !quoted;
        else if (!quoted && ch === sep) inLine++;
      }
      count = Math.max(count, inLine);
    }
    if (count > bestCount) {
      best = sep;
      bestCount = count;
    }
  }
  return best;
}

/** CSV with ; , or tab (whichever the first line uses most), quotes, "" escapes, BOM and CRLF. */
export function parseCsv(text: string): SheetTable {
  const src = text.replace(/^﻿/, "");
  const sep = detectSeparator(src);
  const records: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let quoted = false;
  for (let i = 0; i < src.length; i++) {
    const ch = src[i];
    if (quoted) {
      if (ch === '"') {
        if (src[i + 1] === '"') {
          cell += '"';
          i++;
        } else quoted = false;
      } else cell += ch;
      continue;
    }
    if (ch === '"' && cell.trim() === "") {
      quoted = true;
      cell = "";
    } else if (ch === sep) {
      row.push(cell);
      cell = "";
    } else if (ch === "\n" || ch === "\r") {
      if (ch === "\r" && src[i + 1] === "\n") i++;
      row.push(cell);
      records.push(row);
      row = [];
      cell = "";
    } else cell += ch;
  }
  if (cell !== "" || row.length) {
    row.push(cell);
    records.push(row);
  }
  const nonEmpty = records.filter((r) => r.some((c) => c.trim() !== ""));
  return checkRows(cleanTable(splitHeader(nonEmpty)));
}

// --- XLSX: a ZIP of XML parts ---

type ZipEntry = { name: string; method: number; compressedSize: number; localOffset: number };

function zipEntries(bytes: Uint8Array): ZipEntry[] {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  let eocd = -1;
  for (let i = bytes.length - 22; i >= Math.max(0, bytes.length - 22 - 65_535); i--) {
    if (view.getUint32(i, true) === 0x06054b50) {
      eocd = i;
      break;
    }
  }
  if (eocd < 0) throw new SheetError("unreadable");
  const count = view.getUint16(eocd + 10, true);
  let at = view.getUint32(eocd + 16, true);
  const entries: ZipEntry[] = [];
  const decoder = new TextDecoder();
  for (let k = 0; k < count; k++) {
    if (at + 46 > bytes.length || view.getUint32(at, true) !== 0x02014b50) throw new SheetError("unreadable");
    const method = view.getUint16(at + 10, true);
    const compressedSize = view.getUint32(at + 20, true);
    const nameLen = view.getUint16(at + 28, true);
    const extraLen = view.getUint16(at + 30, true);
    const commentLen = view.getUint16(at + 32, true);
    const localOffset = view.getUint32(at + 42, true);
    const name = decoder.decode(bytes.subarray(at + 46, at + 46 + nameLen));
    entries.push({ name, method, compressedSize, localOffset });
    at += 46 + nameLen + extraLen + commentLen;
  }
  return entries;
}

function zipRead(bytes: Uint8Array, entry: ZipEntry): string {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const at = entry.localOffset;
  if (view.getUint32(at, true) !== 0x04034b50) throw new SheetError("unreadable");
  const start = at + 30 + view.getUint16(at + 26, true) + view.getUint16(at + 28, true);
  const data = bytes.subarray(start, start + entry.compressedSize);
  let raw: Uint8Array;
  if (entry.method === 0) raw = data;
  else if (entry.method === 8) raw = inflateRaw(data, 32 * SHEET_MAX_BYTES);
  else throw new SheetError("unreadable");
  return new TextDecoder().decode(raw);
}

function xmlText(s: string): string {
  return s
    .replace(/<[^>]+>/g, "")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'")
    .replace(/&#(\d+);/g, (_, d) => String.fromCodePoint(Number(d)))
    .replace(/&#x([0-9a-f]+);/gi, (_, h) => String.fromCodePoint(parseInt(h, 16)))
    .replace(/&amp;/g, "&");
}

function attr(tag: string, name: string): string | null {
  const m = new RegExp(`\\s${name}="([^"]*)"`).exec(tag);
  return m ? m[1] : null;
}

function columnIndex(ref: string): number {
  const letters = /^[A-Z]+/.exec(ref)?.[0] ?? "A";
  let n = 0;
  for (const ch of letters) n = n * 26 + (ch.charCodeAt(0) - 64);
  return n - 1;
}

/** «4,5» → strings of the shared table: each <si> joined from its <t> runs (phonetic runs skipped). */
function sharedStrings(xml: string): string[] {
  const out: string[] = [];
  for (const si of xml.matchAll(/<si>([\s\S]*?)<\/si>/g)) {
    const body = si[1].replace(/<rPh[\s\S]*?<\/rPh>/g, "");
    out.push([...body.matchAll(/<t(?:\s[^>]*)?>([\s\S]*?)<\/t>/g)].map((t) => xmlText(t[1])).join(""));
  }
  return out;
}

function firstSheetPath(files: Map<string, ZipEntry>, bytes: Uint8Array): string {
  const wb = files.get("xl/workbook.xml");
  const rels = files.get("xl/_rels/workbook.xml.rels");
  if (wb && rels) {
    const sheet = /<sheet\s[^>]*>/.exec(zipRead(bytes, wb))?.[0];
    const rid = sheet ? attr(sheet, "r:id") : null;
    if (rid) {
      for (const rel of zipRead(bytes, rels).matchAll(/<Relationship\s[^>]*>/g)) {
        if (attr(rel[0], "Id") === rid) {
          const target = attr(rel[0], "Target") ?? "";
          const path = target.startsWith("/") ? target.slice(1) : `xl/${target.replace(/^\.\//, "")}`;
          if (files.has(path)) return path;
        }
      }
    }
  }
  const fallback = [...files.keys()].filter((k) => /^xl\/worksheets\/sheet\d+\.xml$/.test(k)).sort()[0];
  if (!fallback) throw new SheetError("unreadable");
  return fallback;
}

/**
 * The first sheet of an XLSX: shared strings, inline strings and numbers as
 * text. Dates stay as Excel serial numbers; toRows turns them into a year or
 * a day for the fields that take one.
 */
export function parseXlsx(bytes: Uint8Array): SheetTable {
  let entries: ZipEntry[];
  try {
    entries = zipEntries(bytes);
  } catch {
    throw new SheetError("unreadable");
  }
  const files = new Map(entries.map((e) => [e.name, e]));
  let grid: string[][] = [];
  try {
    const strings = files.has("xl/sharedStrings.xml") ? sharedStrings(zipRead(bytes, files.get("xl/sharedStrings.xml")!)) : [];
    const sheet = zipRead(bytes, files.get(firstSheetPath(files, bytes))!);
    for (const rowMatch of sheet.matchAll(/<row\b([^>]*)>([\s\S]*?)<\/row>/g)) {
      const rowNumber = Number(attr(rowMatch[0].slice(0, rowMatch[0].indexOf(">") + 1), "r")) || grid.length + 1;
      const cells: string[] = [];
      let next = 0;
      for (const c of rowMatch[2].matchAll(/<c\b([^>]*?)(?:\/>|>([\s\S]*?)<\/c>)/g)) {
        const tag = `<c${c[1]}>`;
        const ref = attr(tag, "r");
        const col = ref ? columnIndex(ref) : next;
        next = col + 1;
        const type = attr(tag, "t");
        const body = c[2] ?? "";
        const v = /<v>([\s\S]*?)<\/v>/.exec(body)?.[1];
        let value = "";
        if (type === "s") value = strings[Number(v)] ?? "";
        else if (type === "inlineStr") value = [...body.matchAll(/<t(?:\s[^>]*)?>([\s\S]*?)<\/t>/g)].map((t) => xmlText(t[1])).join("");
        else if (type === "b") value = v === "1" ? "VERDADERO" : "FALSO";
        else if (v != null) value = xmlText(v);
        cells[col] = value;
      }
      grid[rowNumber - 1] = Array.from(cells, (x) => x ?? "");
    }
  } catch (error) {
    if (error instanceof SheetError) throw error;
    throw new SheetError("unreadable");
  }
  grid = Array.from(grid, (r) => r ?? []).filter((r) => r.some((c) => c.trim() !== ""));
  return checkRows(cleanTable(splitHeader(grid)));
}

// ---------------------------------------------------------------------------
// Columns
// ---------------------------------------------------------------------------

const HEADER_WORDS: [SheetField, RegExp][] = [
  ["make", /^(marca|fabricante)$/],
  ["model", /^(modelo|vehiculo|auto|unidad)$/],
  ["trim", /^(version|ver|variante|modelo version)$/],
  ["year", /^(ano|anio|year|modelo ano|ano modelo|ano fabricacion)$/],
  ["mileage_km", /^(km|kms|kilometraje|kilometros|recorrido)$/],
  ["price", /^(precio|venta|precio venta|precio de venta|pvp|valor|valor venta|precio publicado|precio contado)$/],
  ["currency", /^(moneda|divisa)$/],
  ["transmission", /^(caja|transmision|caja de cambios)$/],
  ["fuel", /^(combustible|motor combustible)$/],
  ["color", /^(color|colores)$/],
  ["in_stock_since", /^(ingreso|fecha ingreso|fecha de ingreso|alta|fecha alta|fecha)$/],
  ["title", /^(titulo|nombre)$/],
  ["description", /^(descripcion|observaciones|obs|detalle|comentarios|notas)$/],
];
/** Never the sale price: what the agency paid. */
const COST_HEADER = /\b(costo|compra|pagado|toma|precio toma|precio compra)\b/;

function isAmount(value: string): boolean {
  const m = parseMoney(value);
  return m !== null && m.amount >= 1000;
}

/**
 * The column for each field from its header (Spanish, with or without
 * accents). A price header with no values (the informe's «VENTA») doesn't
 * count: then the first column of amounts with no title of its own is the
 * price, and the preview asks to confirm it (priceColumnGuessed).
 */
export function guessColumns(headers: string[], rows: string[][]): ColumnMap {
  const map: ColumnMap = {};
  const folded = headers.map(fold);
  const filled = (i: number) => rows.filter((r) => (r[i] ?? "").trim() !== "").length;
  for (const [field, re] of HEADER_WORDS) {
    const i = folded.findIndex((h, k) => re.test(h) && !Object.values(map).includes(k));
    if (i >= 0) map[field] = i;
  }
  if (map.price !== undefined && filled(map.price) === 0) delete map.price;
  if (map.price === undefined) {
    const used = new Set(Object.values(map));
    const candidates = headers.map((_, i) => i).filter((i) => !used.has(i) && !COST_HEADER.test(folded[i]));
    const amounts = (i: number) => {
      const values = rows.map((r) => r[i] ?? "").filter((v) => v.trim() !== "");
      return values.length > 0 && values.filter(isAmount).length / values.length >= 0.6;
    };
    const untitled = candidates.find((i) => folded[i] === "" && amounts(i));
    const any = untitled ?? candidates.find((i) => amounts(i) && !(map.year === i) && !(map.mileage_km === i));
    if (any !== undefined && map.mileage_km !== any) map.price = any;
  }
  return map;
}

/** Whether the price column was guessed (its header doesn't say price): the preview asks «¿Esta columna es el precio de venta?». */
export function priceColumnGuessed(headers: string[], map: ColumnMap): boolean {
  if (map.price === undefined) return false;
  const re = HEADER_WORDS.find(([f]) => f === "price")![1];
  return !re.test(fold(headers[map.price] ?? ""));
}

// ---------------------------------------------------------------------------
// Values
// ---------------------------------------------------------------------------

const EXCEL_EPOCH = Date.UTC(1899, 11, 30);

function serialDate(n: number): Date | null {
  if (!Number.isFinite(n) || n < 20_000 || n > 80_000) return null;
  return new Date(EXCEL_EPOCH + Math.round(n) * 86_400_000);
}

/** «$ 12.500.000», «12,5 M», «USD 14.000», «u$s 14.000», «14000»: amount and currency when it says. */
export function parseMoney(raw: string): { amount: number; currency: "ARS" | "USD" | null } | null {
  let s = String(raw ?? "").trim().toLowerCase();
  if (!s) return null;
  let currency: "ARS" | "USD" | null = null;
  if (/u\$s|us\$|usd|u\$d|dolar|dólar|\bus\b/.test(s)) currency = "USD";
  else if (/\$|ars|pesos/.test(s)) currency = "ARS";
  let mult = 1;
  if (/\d\s*(m|mill|millon|millones|palos)\b/.test(s)) mult = 1_000_000;
  else if (/\d\s*(k|mil)\b/.test(s)) mult = 1_000;
  s = s.replace(/[^\d.,]/g, "");
  if (!/\d/.test(s)) return null;
  const lastDot = s.lastIndexOf(".");
  const lastComma = s.lastIndexOf(",");
  let n: number;
  if (lastDot >= 0 && lastComma >= 0) {
    const dec = lastDot > lastComma ? "." : ",";
    const thou = dec === "." ? "," : ".";
    n = Number(s.split(thou).join("").replace(dec, "."));
  } else if (lastDot >= 0 || lastComma >= 0) {
    const sep = lastDot >= 0 ? "." : ",";
    const parts = s.split(sep);
    const thousands = parts.length > 2 || (mult === 1 && parts[parts.length - 1].length === 3);
    n = thousands ? Number(parts.join("")) : Number(parts.join("."));
  } else n = Number(s);
  if (!Number.isFinite(n) || n <= 0) return null;
  return { amount: Math.round(n * mult * 100) / 100, currency };
}

/** Explicit currency, else ARS from 1.000.000 up and USD below (matching.filter_currency). */
export function currencyFor(amount: number, explicit: string | null): "ARS" | "USD" {
  const e = fold(explicit ?? "");
  if (/^(usd|us|u s s|dolar|dolares|u s|us s)$/.test(e) || /usd|dolar/.test(e)) return "USD";
  if (/^(ars|pesos|peso|\$)$/.test(e) || /ars|peso/.test(e) || (explicit ?? "").trim() === "$") return "ARS";
  return amount >= 1_000_000 ? "ARS" : "USD";
}

export function parseYear(raw: string, now = new Date()): number | null {
  const s = String(raw ?? "").trim();
  if (!s) return null;
  const max = now.getUTCFullYear() + 1;
  const four = /(19[5-9]\d|20\d{2})/.exec(s);
  if (four) {
    const y = Number(four[1]);
    return y >= 1950 && y <= max ? y : null;
  }
  if (/^\d+(\.\d+)?$/.test(s)) {
    const d = serialDate(Number(s));
    if (d) {
      const y = d.getUTCFullYear();
      return y >= 1950 && y <= max ? y : null;
    }
  }
  return null;
}

export function parseKm(raw: string): number | null {
  const s = fold(String(raw ?? ""));
  if (!s) return null;
  if (/^(0 ?km|okm|0km|nuevo)$/.test(s)) return 0;
  const m = parseMoney(raw);
  if (!m) return null;
  const n = Math.round(m.amount);
  return n >= 0 && n <= 2_000_000 ? n : null;
}

export function parseTransmission(raw: string): "manual" | "automatic" | null {
  const s = fold(String(raw ?? ""));
  if (!s) return null;
  if (/\b(at|aut|auto|automatica|automatico|automatic|cvt|dsg|tiptronic|secuencial)\b/.test(s)) return "automatic";
  if (/\b(mt|man|manual|mecanica|mecanico|mec)\b/.test(s)) return "manual";
  return null;
}

export function parseFuel(raw: string): string | null {
  const s = fold(String(raw ?? ""));
  if (!s) return null;
  if (/hibrid/.test(s)) return "hibrido";
  if (/electri/.test(s)) return "electrico";
  if (/gnc|gas natural/.test(s)) return "gnc";
  if (/diesel|gasoil|gas oil|tdi|hdi|\bd\b/.test(s)) return "diesel";
  if (/nafta|naftero|gasolina/.test(s)) return "nafta";
  return null;
}

/** A day (AAAA-MM-DD) from «18/11/2026», «2026-11-18» or an Excel serial; null when it isn't one. */
export function parseDay(raw: string, now = new Date()): string | null {
  const s = String(raw ?? "").trim();
  if (!s) return null;
  let d: Date | null = null;
  let m = /^(\d{4})-(\d{1,2})-(\d{1,2})/.exec(s);
  if (m) d = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])));
  else if ((m = /^(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})$/.exec(s))) {
    const y = Number(m[3]) < 100 ? 2000 + Number(m[3]) : Number(m[3]);
    d = new Date(Date.UTC(y, Number(m[2]) - 1, Number(m[1])));
    if (d.getUTCDate() !== Number(m[1])) d = null;
  } else if (/^\d+(\.\d+)?$/.test(s)) d = serialDate(Number(s));
  if (!d || Number.isNaN(d.getTime())) return null;
  if (d.getUTCFullYear() < 1990 || d.getTime() > now.getTime() + 86_400_000) return null;
  return d.toISOString().slice(0, 10);
}

// ---------------------------------------------------------------------------
// Catalog
// ---------------------------------------------------------------------------

const MAKE_ALIASES: Record<string, string> = {
  vw: "volkswagen", volks: "volkswagen", chevy: "chevrolet", mb: "mercedes benz", mercedes: "mercedes benz",
  "mercedes benz": "mercedes benz", citroen: "citroen", "land rover": "land rover", alfa: "alfa romeo",
};

export type VehicleMatch = { make: string; model: string; trim: string | null; inCatalog: boolean };

/**
 * The catalog's spelling of a make and model. The model cell may carry the
 * trim («Focus SE 2.0»): the longest catalog model its words start with
 * wins, and the rest is the trim (kept as typed, unless it is a catalog trim).
 * With no model column, the make cell may carry it all («Ford Focus SE»).
 */
export function matchVehicle(makeText: string | null, modelText: string | null, catalog: Catalog): VehicleMatch | null {
  const makeRaw = (makeText ?? "").trim();
  const modelRaw = (modelText ?? "").trim();
  if (!makeRaw && !modelRaw) return null;
  const words = fold(`${makeRaw} ${modelRaw}`).split(" ").filter(Boolean);
  let make: Catalog[number] | undefined;
  let used = 0;
  for (let n = Math.min(3, words.length); n >= 1 && !make; n--) {
    const head = words.slice(0, n).join(" ");
    const target = MAKE_ALIASES[head] ?? head;
    make = catalog.find((m) => fold(m.make) === target);
    if (make) used = n;
  }
  if (!make) return { make: makeRaw || modelRaw, model: modelRaw, trim: null, inCatalog: false };
  const rest = words.slice(used);
  let best: { model: Catalog[number]["models"][number]; n: number } | null = null;
  for (const model of make.models) {
    const mw = fold(model.model).split(" ").filter(Boolean);
    if (mw.length && mw.length <= rest.length && mw.every((w, i) => rest[i] === w) && (!best || mw.length > best.n)) {
      best = { model, n: mw.length };
    }
  }
  if (!best) return { make: make.make, model: modelRaw || rest.join(" "), trim: null, inCatalog: false };
  const tail = rest.slice(best.n).join(" ");
  const trim = tail ? (best.model.trims.find((t) => fold(t) === tail) ?? originalTail(modelRaw || makeRaw, best.n, tail)) : null;
  return { make: make.make, model: best.model.model, trim, inCatalog: true };
}

/** The trim as the agency typed it (accents and case kept), from the model cell's words after the model. */
function originalTail(text: string, modelWords: number, foldedTail: string): string {
  const words = text.trim().split(/\s+/);
  const tail = words.slice(-foldedTail.split(" ").length).join(" ");
  return fold(tail) === foldedTail ? tail : words.slice(modelWords).join(" ") || foldedTail;
}

// ---------------------------------------------------------------------------
// Rows
// ---------------------------------------------------------------------------

/**
 * The sheet's rows as stock items, each with what is wrong with it. The
 * spreadsheet's line number is kept (header = line 1). Nothing is written.
 * price_far_from_market / price_looks_like_cost come after loading, from the
 * panel's insights (priceCheck), not here.
 */
export function toRows(table: SheetTable, map: ColumnMap, catalog: Catalog, now = new Date()): SheetRow[] {
  const cell = (row: string[], f: SheetField) => (map[f] === undefined ? "" : (row[map[f]!] ?? "").trim());
  const seen = new Map<string, number>();
  return table.rows.map((row, i) => {
    const issues: SheetIssue[] = [];
    // «Kangoo Confort 1.5 D 2011»: with no year of its own, the year written in the model cell, out of the trim.
    let modelText = cell(row, "model");
    let year = parseYear(cell(row, "year"), now);
    const yearInModel = /(?:^|\s)((?:19[5-9]|20\d)\d)$/.exec(modelText);
    if (yearInModel) {
      year ??= parseYear(yearInModel[1], now);
      modelText = modelText.slice(0, yearInModel.index).trim();
    }
    const vehicleMatch = matchVehicle(cell(row, "make") || null, modelText || null, catalog);
    const money = parseMoney(cell(row, "price"));
    const values: ItemValues = {
      make: vehicleMatch?.make || null,
      model: vehicleMatch?.model || null,
      trim: (cell(row, "trim") || vehicleMatch?.trim || null)?.slice(0, 80) ?? null,
      year,
      mileage_km: parseKm(cell(row, "mileage_km")),
      price: money?.amount ?? null,
      currency: money ? currencyFor(money.amount, cell(row, "currency") || money.currency) : null,
      transmission: parseTransmission(cell(row, "transmission")),
      fuel: parseFuel(cell(row, "fuel")),
      color: cell(row, "color").slice(0, 80) || null,
      in_stock_since: parseDay(cell(row, "in_stock_since"), now),
      title: cell(row, "title").slice(0, 160) || null,
      description: cell(row, "description").slice(0, 4000) || null,
    };
    if (!values.make) issues.push("no_make");
    if (!values.model) issues.push("no_model");
    if (values.make && values.model && !vehicleMatch?.inCatalog) issues.push("not_in_catalog");
    if (values.year == null) issues.push("no_year");
    if (values.price == null) issues.push("no_price");
    const key = [values.make, values.model, values.trim, values.year, values.mileage_km, values.price].map((v) => fold(String(v ?? ""))).join("|");
    if (values.make && values.model && seen.has(key)) issues.push("duplicate_in_sheet");
    else seen.set(key, i);
    return { line: i + 2, values, issues };
  });
}

/** Issues that keep a row out of «Cargar N autos» (a duplicate can still go: two equal cars exist). */
const BLOCKING: SheetIssue[] = ["no_make", "no_model", "not_in_catalog", "no_year", "no_price"];

export function rowAccepted(row: SheetRow): boolean {
  return !row.issues.some((i) => BLOCKING.includes(i));
}

export const ISSUE_TEXT: Record<SheetIssue, string> = {
  no_make: "Falta la marca",
  no_model: "Falta el modelo",
  not_in_catalog: "No está en el catálogo",
  no_year: "Falta el año",
  no_price: "Falta el precio",
  price_far_from_market: "Precio muy lejos del mercado",
  price_looks_like_cost: "Parece lo que pagaste",
  duplicate_in_sheet: "Repetido en la planilla",
};

export const FIELD_LABEL: Record<SheetField, string> = {
  make: "Marca", model: "Modelo", trim: "Versión", year: "Año", mileage_km: "Km", price: "Precio de venta", currency: "Moneda",
  transmission: "Caja", fuel: "Combustible", color: "Color", in_stock_since: "Ingreso", title: "Título", description: "Descripción",
};

/** The values dealer_import_items takes for one row (nulls dropped). */
export function importValues(values: ItemValues): Record<string, string | number> {
  const out: Record<string, string | number> = {};
  for (const [k, v] of Object.entries(values)) if (v !== null && v !== "") out[k] = v;
  return out;
}

export function sheetKind(filename: string, type: string | null | undefined): SheetKind | null {
  const name = filename.toLowerCase();
  if (name.endsWith(".xlsx") || type === "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet") return "xlsx";
  if (name.endsWith(".csv") || name.endsWith(".txt") || type === "text/csv") return "csv";
  return null;
}

/** Reads the file's bytes as its kind says; SheetError on a bad or too big file. */
export function readSheet(bytes: Uint8Array, kind: SheetKind): SheetTable {
  if (bytes.byteLength > SHEET_MAX_BYTES) throw new SheetError("too_big");
  if (kind === "xlsx") return parseXlsx(bytes);
  const text = new TextDecoder("utf-8", { fatal: false }).decode(bytes);
  // A CSV saved by Excel in Latin-1 shows U+FFFD for accents: read it again as windows-1252.
  return parseCsv(text.includes("�") ? new TextDecoder("windows-1252").decode(bytes) : text);
}
