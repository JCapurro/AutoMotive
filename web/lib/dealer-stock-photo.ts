import type { SheetTable } from "@/lib/dealer-sheet";

/**
 * Agencias, fase 1: the stock list from a photo or a PDF. The browser sends the
 * file to public.dealer_request_stock_read() (an llm_jobs row of kind
 * dealer_stock_read), the worker reads it with the LLM and leaves a table with
 * fixed headers in the job's output; this module reads that output back as the
 * SheetTable the spreadsheet preview already knows. Pure.
 */

export type StockMedia = "image/jpeg" | "image/png" | "image/webp" | "application/pdf";

/** 4 MB, the SQL cap on the decoded file (dealer_stock_reads.bytes). */
export const STOCK_PHOTO_MAX_BYTES = 4 * 1024 * 1024;
/** How long the panel waits for the worker before saying «tarda más de lo normal». */
export const STOCK_READ_WAIT_MS = 150_000;

/** A photo or a PDF the reader takes, by type or name; null for anything else (a spreadsheet goes the old way). */
export function stockMedia(filename: string, type: string | null | undefined): StockMedia | null {
  const t = (type ?? "").toLowerCase();
  const name = filename.toLowerCase();
  if (t === "application/pdf" || name.endsWith(".pdf")) return "application/pdf";
  if (t === "image/jpeg" || /\.jpe?g$/.test(name)) return "image/jpeg";
  if (t === "image/png" || name.endsWith(".png")) return "image/png";
  if (t === "image/webp" || name.endsWith(".webp")) return "image/webp";
  // A phone's HEIC or any other image: the browser re-encodes it as JPEG first.
  if (t.startsWith("image/")) return "image/jpeg";
  return null;
}

export function sheetKindOf(media: string): "photo" | "pdf" | "csv" {
  return media === "application/pdf" ? "pdf" : media === SHEET_TEXT_TYPE ? "csv" : "photo";
}

/** A spreadsheet goes to the reader as text (20270103120000_dealer_stock_read_text.sql). */
export const SHEET_TEXT_TYPE = "text/csv";
/** The reader takes this many cars in one read (worker llm/schemas.py STOCK_SHEET_MAX_ROWS). */
export const STOCK_READ_MAX_ROWS = 200;

/**
 * A spreadsheet's table as the text the reader gets: one row per line, cells
 * joined by « ; ». The table comes from readSheet(), so plate columns are
 * already gone. Null when it has more rows than one read takes (the panel then
 * reads it by columns, as before) or nothing to read.
 */
export function tableToText(table: SheetTable): string | null {
  if (table.rows.length === 0 || table.rows.length > STOCK_READ_MAX_ROWS) return null;
  const cell = (v: string) => v.replace(/[\r\n;]+/g, " ").replace(/\s+/g, " ").trim();
  const line = (r: string[]) => r.map(cell).join(" ; ");
  const lines = [line(table.headers), ...table.rows.map(line)].filter((l) => l.replace(/[ ;]/g, "") !== "");
  return lines.join("\n");
}

/** Bytes as base64 (what the RPC decodes), in chunks so a 4 MB file doesn't blow the stack. */
export function toBase64(bytes: Uint8Array): string {
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(binary);
}

export type StockReadState =
  | { state: "pending" }
  | { state: "error"; message: string }
  | { state: "ok"; table: SheetTable; kind: "photo" | "pdf" | "csv"; truncated: boolean };

const isStrings = (v: unknown): v is string[] => Array.isArray(v) && v.every((x) => typeof x === "string");

/** An llm_jobs row (status, output) of kind dealer_stock_read, read tolerantly. */
export function stockReadState(job: { status: string; output: unknown } | null): StockReadState {
  if (!job) return { state: "error", message: "No encontramos esa lectura. Subí el archivo de nuevo." };
  if (job.status === "queued" || job.status === "running") return { state: "pending" };
  if (job.status !== "done") return { state: "error", message: "No pudimos leer el archivo. Probá con una foto más nítida o subí la planilla." };
  const out = (job.output && typeof job.output === "object" && !Array.isArray(job.output) ? job.output : {}) as Record<string, unknown>;
  const headers = out.headers;
  const rows = Array.isArray(out.rows) ? out.rows.filter(isStrings) : [];
  if (out.readable !== true || !isStrings(headers) || rows.length === 0) {
    return { state: "error", message: "No encontramos autos en el archivo. Probá con una foto más nítida, derecha y con la lista entera." };
  }
  const media = typeof out.media_type === "string" ? out.media_type : "image/jpeg";
  return {
    state: "ok",
    table: { headers, rows: rows.map((r) => headers.map((_, i) => r[i] ?? "")) },
    kind: sheetKindOf(media),
    truncated: out.truncated === true,
  };
}
