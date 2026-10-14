/**
 * Pro (3.3, docs/PLANES_2026-10.md): the results of a search, or of all of
 * them, as a spreadsheet. UTF-8 with BOM and semicolons, which Excel expects
 * in Argentina; Google Sheets reads the same file. The rows come from
 * public.export_search_results, the column names from the product's fields.
 */
export type ExportRow = {
  search_name: string | null;
  detected_at: string | null;
  source_name: string | null;
  title: string | null;
  version: string | null;
  year: number | null;
  mileage_km: number | null;
  price: number | null;
  currency: string | null;
  /** Price against comparables: -12 is 12% below. Null without enough of them. */
  comparables_pct: number | null;
  score: number | null;
  url: string | null;
};

export const CSV_COLUMNS = [
  "Búsqueda", "Fecha de detección", "Portal", "Título", "Versión", "Año", "Kilometraje",
  "Precio", "Moneda", "% frente a comparables", "Puntaje", "Enlace",
] as const;

const BOM = "﻿";
const TIME_ZONE = "America/Argentina/Buenos_Aires";

/** "2026-10-14 15:30", Argentine time: both Excel and Sheets read it as a date. */
export function csvDate(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const parts = Object.fromEntries(new Intl.DateTimeFormat("en-CA", {
    timeZone: TIME_ZONE, year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).formatToParts(date).map((p) => [p.type, p.value]));
  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}`;
}

/** 10300 → "10300", 12.5 → "12,5": no thousands separator, Excel's decimal comma in Argentina. */
export function csvNumber(value: number | null): string {
  if (value == null || !Number.isFinite(value)) return "";
  return String(Math.round(value * 100) / 100).replace(".", ",");
}

/** A text cell: quoted when it carries a separator, a quote or a line break;
 * one Excel would run as a formula (=, +, -, @) starts with an apostrophe. */
export function csvText(value: string | null): string {
  if (!value) return "";
  const text = /^[=+\-@\t\r]/.test(value) ? `'${value}` : value;
  return /[;"\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

export function resultsCsv(rows: readonly ExportRow[]): string {
  const lines = [CSV_COLUMNS.join(";")];
  for (const r of rows) {
    lines.push([
      csvText(r.search_name), csvDate(r.detected_at), csvText(r.source_name), csvText(r.title),
      csvText(r.version), csvNumber(r.year), csvNumber(r.mileage_km), csvNumber(r.price), csvText(r.currency),
      csvNumber(r.comparables_pct), csvNumber(r.score), csvText(r.url),
    ].join(";"));
  }
  return BOM + lines.join("\r\n") + "\r\n";
}

/** "ese-auto-ford-fiesta-2026-10-14.csv"; all searches: "ese-auto-busquedas-2026-10-14.csv". */
export function exportFilename(searchName: string | null, now = new Date()): string {
  const slug = (searchName ?? "busquedas").normalize("NFD").replace(/[̀-ͯ]/g, "")
    .toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 60) || "busqueda";
  return `ese-auto-${slug}-${csvDate(now.toISOString()).slice(0, 10)}.csv`;
}
