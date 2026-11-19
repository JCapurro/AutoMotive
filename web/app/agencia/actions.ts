"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";

import { cityById } from "@/lib/argentina-locations";
import { requireUser } from "@/lib/auth";
import { loadCatalog } from "@/lib/catalog";
import { dealerErrorText } from "@/lib/dealer-program";
import {
  type ColumnMap,
  guessColumns,
  importValues,
  matchVehicle,
  priceColumnGuessed,
  readSheet,
  rowAccepted,
  SHEET_ERROR_TEXT,
  SHEET_FIELDS,
  SHEET_MAX_BYTES,
  SheetError,
  type SheetField,
  type SheetKind,
  sheetKind,
  type SheetRow,
  type SheetTable,
  toRows,
} from "@/lib/dealer-sheet";
import { stockReadState } from "@/lib/dealer-stock-photo";
import { normalizeArPhone } from "@/lib/phone";
import { createClient } from "@/lib/supabase/server";
import type { Json } from "@/types/database";

/**
 * The agency panel's writes (spec §6.2). Every one goes through an RPC with the
 * signed-in user's session: the RPC checks the switch, the membership and the
 * values. No service role, nothing about buyers in logs.
 */

export type ActionResult = { ok?: boolean; error?: string; id?: number; count?: number };

function done(): void {
  revalidatePath("/agencia", "layout");
}

function fail(message: string | undefined, where: string): ActionResult {
  // Only the code: never what the person typed.
  console.error(`agencia ${where}:`, String(message ?? "").slice(0, 80));
  return { error: dealerErrorText(message) };
}

const LINK_KINDS = ["mercadolibre", "facebook", "instagram", "web"] as const;

const DealerInput = z.object({
  name: z.string().trim().min(2, "Revisá el nombre.").max(80, "Revisá el nombre."),
  cityId: z.string().min(1, "Elegí la localidad."),
  phone: z.string().trim().max(40).optional().default(""),
  whatsapp: z.string().trim().max(40).optional().default(""),
  contactEmail: z.string().trim().max(200).optional().default(""),
  addressText: z.string().trim().max(160, "Revisá la dirección.").optional().default(""),
  links: z.array(z.object({ kind: z.enum(LINK_KINDS), url: z.string().trim().max(300) })).max(6).optional().default([]),
});

/** The form, as create_dealer / update_my_dealer take it; a message when something is off. */
function dealerArgs(input: unknown) {
  const parsed = DealerInput.safeParse(input);
  if (!parsed.success) return { error: parsed.error.issues[0]?.message ?? "Revisá los datos." };
  const v = parsed.data;
  const city = cityById(v.cityId);
  if (!city) return { error: "Elegí la localidad." };
  let whatsapp: string | null = null;
  if (v.whatsapp) {
    const e164 = normalizeArPhone(v.whatsapp);
    if (!e164) return { error: "Revisá el WhatsApp: escribilo con el código de área." };
    whatsapp = e164.replace(/\D/g, "");
  }
  const phone = v.phone ? v.phone.replace(/\D/g, "") : null;
  if (phone && !/^\d{8,15}$/.test(phone)) return { error: "Revisá el teléfono." };
  if (v.contactEmail && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v.contactEmail)) return { error: "Revisá el email." };
  const links = v.links.filter((l) => l.url !== "");
  if (links.some((l) => !/^https:\/\/\S+$/.test(l.url))) return { error: "Los links tienen que empezar con https://" };
  return {
    args: {
      p_name: v.name,
      p_locality_label: city.label,
      p_lat: city.lat,
      p_lon: city.lon,
      p_phone: phone,
      p_whatsapp: whatsapp,
      p_contact_email: v.contactEmail || null,
      p_address_text: v.addressText || null,
      p_profile_links: links as unknown as Json,
    },
  };
}

export async function createDealer(input: unknown): Promise<ActionResult> {
  await requireUser();
  const built = dealerArgs(input);
  if (!built.args) return { error: built.error };
  const supabase = await createClient();
  const { data, error } = await supabase.rpc("create_dealer", built.args);
  if (error) return fail(error.message, "create_dealer");
  done();
  return { ok: true, id: data };
}

export async function updateDealer(input: unknown): Promise<ActionResult> {
  await requireUser();
  const built = dealerArgs(input);
  if (!built.args) return { error: built.error };
  const supabase = await createClient();
  const { error } = await supabase.rpc("update_my_dealer", built.args);
  if (error) return fail(error.message, "update_my_dealer");
  done();
  return { ok: true };
}

const SourceInput = z.object({
  source: z.string().min(1).max(40),
  profileUrl: z.string().trim().max(300).optional().default(""),
  sellerNameHint: z.string().trim().max(80, "El nombre es muy largo.").optional().default(""),
});

export async function addDealerSource(input: unknown): Promise<ActionResult> {
  await requireUser();
  const parsed = SourceInput.safeParse(input);
  if (!parsed.success) return { error: parsed.error.issues[0]?.message ?? "Revisá los datos." };
  const { source, profileUrl, sellerNameHint } = parsed.data;
  if (profileUrl && !/^https:\/\/\S+$/.test(profileUrl)) return { error: "El link tiene que empezar con https://" };
  if (!profileUrl && !sellerNameHint) return { error: "Pegá el link de tu perfil o cómo figura tu nombre." };
  const supabase = await createClient();
  const { data, error } = await supabase.rpc("dealer_add_source", {
    p_source: source, p_profile_url: profileUrl || null, p_seller_name_hint: sellerNameHint || null,
  });
  if (error) return fail(error.message, "dealer_add_source");
  done();
  return { ok: true, id: data };
}

const ItemInput = z.object({
  make: z.string().trim().min(1, "Elegí la marca.").max(60),
  model: z.string().trim().min(1, "Elegí el modelo.").max(60),
  trim: z.string().trim().max(80).optional().default(""),
  year: z.coerce.number().int("Revisá el año.").min(1950, "Revisá el año.").max(new Date().getFullYear() + 1, "Revisá el año."),
  mileageKm: z.union([z.literal(""), z.coerce.number().int("Revisá los km.").min(0, "Revisá los km.").max(2_000_000, "Revisá los km.")]).optional().default(""),
  price: z.coerce.number().positive("Revisá el precio.").max(999_999_999_999, "Revisá el precio."),
  currency: z.enum(["ARS", "USD"]),
  transmission: z.enum(["", "manual", "automatic"]).optional().default(""),
  fuel: z.string().trim().max(40).optional().default(""),
  color: z.string().trim().max(80).optional().default(""),
  inStockSince: z.union([z.literal(""), z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "Revisá la fecha de ingreso.")]).optional().default(""),
  title: z.string().trim().max(160).optional().default(""),
  description: z.string().trim().max(4000, "La descripción es muy larga.").optional().default(""),
  images: z.array(z.string().trim().max(1000)).max(10, "Hasta 10 fotos.").optional().default([]),
});

/** Create (itemId null) or edit a car of my stock; it goes back to «pendiente» and the worker rewrites its listing. */
export async function saveItem(itemId: number | null, input: unknown): Promise<ActionResult> {
  await requireUser();
  if (itemId !== null && (!Number.isInteger(itemId) || itemId <= 0)) return { error: "No encontramos ese auto en tu stock." };
  const parsed = ItemInput.safeParse(input);
  if (!parsed.success) return { error: parsed.error.issues[0]?.message ?? "Revisá los datos." };
  const v = parsed.data;
  const images = v.images.filter(Boolean);
  // https only; http just for the local stack's own storage (the SQL validator says the same).
  if (images.some((u) => !/^(https:\/\/|http:\/\/(127\.0\.0\.1|localhost)[:/])\S+$/.test(u))) return { error: "Los links de las fotos tienen que empezar con https://" };
  const supabase = await createClient();
  // The catalog's spelling (the worker normalizes again when it writes the listing).
  const match = matchVehicle(v.make, v.model, await loadCatalog(supabase));
  const values = {
    make: match?.inCatalog ? match.make : v.make,
    model: match?.inCatalog ? match.model : v.model,
    trim: v.trim || null,
    year: v.year,
    mileage_km: v.mileageKm === "" ? null : v.mileageKm,
    price: v.price,
    currency: v.currency,
    transmission: v.transmission || null,
    fuel: v.fuel || null,
    color: v.color || null,
    in_stock_since: v.inStockSince || null,
    title: v.title || null,
    description: v.description || null,
    images,
  };
  const { data, error } = await supabase.rpc("dealer_upsert_item", { p_item_id: itemId, p_values: values as unknown as Json });
  if (error) return fail(error.message, "dealer_upsert_item");
  done();
  return { ok: true, id: data };
}

// --- The spreadsheet ---

export type SheetPreview = {
  ok?: boolean;
  error?: string;
  filename?: string;
  kind?: SheetKind | "photo" | "pdf";
  /** A photo or PDF still being read by the worker: ask again in a few seconds. */
  pending?: boolean;
  /** The list had more cars than one read takes (llm STOCK_SHEET_MAX_ROWS). */
  truncated?: boolean;
  headers?: string[];
  sample?: string[][];
  map?: ColumnMap;
  priceGuessed?: boolean;
  rows?: SheetRow[];
};

type Overrides = Record<string, { make?: string; model?: string }>;

const MapInput = z.record(z.enum(SHEET_FIELDS as [SheetField, ...SheetField[]]), z.number().int().min(0).max(200));
const OverridesInput = z.record(z.string().regex(/^\d+$/), z.object({ make: z.string().max(60).optional(), model: z.string().max(60).optional() })).optional();

type Upload = { table: SheetTable; filename: string; kind: SheetKind | "photo" | "pdf"; truncated?: boolean };

/**
 * A photo or a PDF already read by the worker (fase 1): the llm_jobs row the
 * browser queued with dealer_request_stock_read(). RLS lets the person read
 * only their own jobs; the job must be a stock read of their agency. The
 * table comes from the worker, never from the browser.
 */
async function readStockJob(raw: string): Promise<Upload | { error: string } | { pending: true }> {
  if (!/^\d{1,15}$/.test(raw)) return { error: "No encontramos esa lectura. Subí el archivo de nuevo." };
  const supabase = await createClient();
  const [{ data: job }, { data: dealer }] = await Promise.all([
    supabase.from("llm_jobs").select("kind, status, input, output").eq("id", Number(raw)).maybeSingle(),
    supabase.rpc("my_dealer"),
  ]);
  const dealerId = (dealer as { id?: number } | null)?.id;
  const input = (job?.input ?? {}) as { dealer_id?: unknown };
  if (!job || job.kind !== "dealer_stock_read" || dealerId == null || input.dealer_id !== dealerId) {
    return { error: "No encontramos esa lectura. Subí el archivo de nuevo." };
  }
  const read = stockReadState(job);
  if (read.state === "pending") return { pending: true };
  if (read.state === "error") return { error: read.message };
  return { table: read.table, filename: read.kind === "pdf" ? "PDF de la lista" : "Foto de la lista", kind: read.kind, truncated: read.truncated };
}

async function readUpload(form: FormData): Promise<Upload | { error: string } | { pending: true }> {
  const job = form.get("job");
  if (typeof job === "string" && job) return readStockJob(job);
  const file = form.get("file");
  if (!(file instanceof File) || file.size === 0) return { error: "Elegí una planilla CSV o XLSX." };
  if (file.size > SHEET_MAX_BYTES) return { error: SHEET_ERROR_TEXT.too_big };
  const kind = sheetKind(file.name, file.type);
  if (!kind) return { error: "La planilla tiene que ser CSV o XLSX." };
  try {
    const table = readSheet(new Uint8Array(await file.arrayBuffer()), kind);
    return { table, filename: file.name.slice(0, 200), kind };
  } catch (error) {
    return { error: error instanceof SheetError ? SHEET_ERROR_TEXT[error.code] : SHEET_ERROR_TEXT.unreadable };
  }
}

function columnMap(form: FormData, table: SheetTable): ColumnMap | null {
  const raw = form.get("map");
  if (typeof raw !== "string" || !raw) return guessColumns(table.headers, table.rows);
  try {
    const parsed = MapInput.safeParse(JSON.parse(raw));
    if (!parsed.success) return null;
    const map: ColumnMap = {};
    for (const [field, col] of Object.entries(parsed.data)) if (col < table.headers.length) map[field as SheetField] = col;
    return map;
  } catch {
    return null;
  }
}

function overrides(form: FormData): Overrides {
  const raw = form.get("overrides");
  if (typeof raw !== "string" || !raw) return {};
  try {
    return OverridesInput.parse(JSON.parse(raw)) ?? {};
  } catch {
    return {};
  }
}

/** The rows with the person's catalog fixes, checked against the catalog again. */
function applyOverrides(rows: SheetRow[], fixes: Overrides, catalog: Awaited<ReturnType<typeof loadCatalog>>): SheetRow[] {
  return rows.map((row) => {
    const fix = fixes[String(row.line)];
    if (!fix?.make || !fix.model) return row;
    const match = matchVehicle(fix.make, fix.model, catalog);
    if (!match?.inCatalog) return row;
    const values = { ...row.values, make: match.make, model: match.model };
    const issues = row.issues.filter((i) => i !== "no_make" && i !== "no_model" && i !== "not_in_catalog");
    return { ...row, values, issues };
  });
}

/** Reads the uploaded sheet and shows what would load. Writes nothing. */
export async function previewSheet(form: FormData): Promise<SheetPreview> {
  await requireUser();
  const read = await readUpload(form);
  if ("pending" in read) return { pending: true };
  if ("error" in read) return { error: read.error };
  const map = columnMap(form, read.table);
  if (!map) return { error: "Revisá las columnas elegidas." };
  const supabase = await createClient();
  const catalog = await loadCatalog(supabase);
  const rows = applyOverrides(toRows(read.table, map, catalog), overrides(form), catalog);
  return {
    ok: true,
    filename: read.filename,
    kind: read.kind,
    headers: read.table.headers,
    sample: read.table.rows.slice(0, 3),
    map,
    priceGuessed: priceColumnGuessed(read.table.headers, map),
    rows,
    truncated: read.truncated ?? false,
  };
}

/**
 * «Cargar N autos»: the same file read again on the server (nothing the
 * browser says about the values is trusted), minus the lines the person
 * took out, with their catalog fixes. All or nothing.
 */
export async function importSheet(form: FormData): Promise<ActionResult> {
  await requireUser();
  const read = await readUpload(form);
  if ("pending" in read) return { error: "Todavía estamos leyendo el archivo." };
  if ("error" in read) return { error: read.error };
  const map = columnMap(form, read.table);
  if (!map) return { error: "Revisá las columnas elegidas." };
  const skipRaw = form.get("skip");
  let skip = new Set<number>();
  try {
    skip = new Set(z.array(z.number().int()).max(1000).parse(typeof skipRaw === "string" && skipRaw ? JSON.parse(skipRaw) : []));
  } catch {
    return { error: "Revisá las filas elegidas." };
  }
  const supabase = await createClient();
  const catalog = await loadCatalog(supabase);
  const accepted = applyOverrides(toRows(read.table, map, catalog), overrides(form), catalog)
    .filter((r) => !skip.has(r.line) && rowAccepted(r));
  if (!accepted.length) return { error: "No quedó ningún auto para cargar." };
  const { data, error } = await supabase.rpc("dealer_import_items", {
    p_rows: accepted.map((r) => importValues(r.values)) as unknown as Json,
    p_filename: read.filename,
    p_kind: read.kind,
  });
  if (error) {
    // invalid_item:<n>:<campo> counts the accepted rows: name the spreadsheet's line instead.
    const m = /^invalid_item:(\d+):([a-z_]+)$/.exec(String(error.message ?? "").trim());
    if (m) return fail(`invalid_item:${accepted[Number(m[1]) - 1]?.line ?? m[1]}:${m[2]}`, "dealer_import_items");
    return fail(error.message, "dealer_import_items");
  }
  const imported = (data as { imported?: number } | null)?.imported ?? accepted.length;
  done();
  return { ok: true, count: imported };
}

/** Fase 1: the agency's alert emails on or off (dealer_set_alerts; the program's switch still decides if any go). */
export async function setDealerAlerts(on: boolean): Promise<ActionResult> {
  await requireUser();
  if (typeof on !== "boolean") return { error: dealerErrorText("invalid_dealer:alerts_email") };
  const supabase = await createClient();
  const { error } = await supabase.rpc("dealer_set_alerts", { p_on: on });
  if (error) return fail(error.message, "dealer_set_alerts");
  done();
  return { ok: true };
}

// --- Status, confirmation, review, private data, leads ---

const ITEM_STATUSES = ["available", "reserved", "sold", "archived"] as const;

export async function setItemStatus(itemId: number, status: string): Promise<ActionResult> {
  await requireUser();
  if (!Number.isInteger(itemId) || !(ITEM_STATUSES as readonly string[]).includes(status)) return { error: dealerErrorText("invalid_status") };
  const supabase = await createClient();
  const { error } = await supabase.rpc("dealer_set_item_status", { p_item_id: itemId, p_status: status });
  if (error) return fail(error.message, "dealer_set_item_status");
  done();
  return { ok: true };
}

/** «Confirmar stock»: all my available cars (ids null) or the given ones. */
export async function confirmStock(ids: number[] | null = null): Promise<ActionResult> {
  await requireUser();
  if (ids !== null && (!Array.isArray(ids) || ids.length > 1000 || ids.some((i) => !Number.isInteger(i)))) return { error: "Revisá los autos elegidos." };
  const supabase = await createClient();
  const { data, error } = await supabase.rpc("dealer_confirm_items", { p_item_ids: ids });
  if (error) return fail(error.message, "dealer_confirm_items");
  done();
  return { ok: true, count: data ?? 0 };
}

export async function resolveDuplicate(itemId: number, mine: boolean): Promise<ActionResult> {
  await requireUser();
  if (!Number.isInteger(itemId) || typeof mine !== "boolean") return { error: dealerErrorText("item_not_found") };
  const supabase = await createClient();
  const { error } = await supabase.rpc("dealer_resolve_duplicate", { p_item_id: itemId, p_mine: mine });
  if (error) return fail(error.message, "dealer_resolve_duplicate");
  done();
  return { ok: true };
}

const PrivateInput = z.object({
  purchasePrice: z.union([z.literal(""), z.coerce.number().positive("Revisá lo que pagaste.").max(999_999_999_999, "Revisá lo que pagaste.")]).optional().default(""),
  purchaseCurrency: z.enum(["", "ARS", "USD"]).optional().default(""),
  notes: z.string().trim().max(1000, "Las notas son muy largas.").optional().default(""),
});

export async function saveItemPrivate(itemId: number, input: unknown): Promise<ActionResult> {
  await requireUser();
  if (!Number.isInteger(itemId)) return { error: dealerErrorText("item_not_found") };
  const parsed = PrivateInput.safeParse(input);
  if (!parsed.success) return { error: parsed.error.issues[0]?.message ?? "Revisá los datos." };
  const { purchasePrice, purchaseCurrency, notes } = parsed.data;
  if (purchasePrice !== "" && !purchaseCurrency) return { error: "Elegí la moneda de lo que pagaste." };
  const supabase = await createClient();
  const { error } = await supabase.rpc("dealer_set_item_private", {
    p_item_id: itemId,
    p_purchase_price: purchasePrice === "" ? null : purchasePrice,
    p_purchase_currency: purchasePrice === "" ? null : purchaseCurrency,
    p_notes: notes || null,
  });
  if (error) return fail(error.message, "dealer_set_item_private");
  done();
  return { ok: true };
}

const LEAD_STATUSES = ["new", "contacted", "reserved", "sold", "lost"] as const;

export async function setLeadStatus(leadId: number, status: string): Promise<ActionResult> {
  await requireUser();
  if (!Number.isInteger(leadId) || !(LEAD_STATUSES as readonly string[]).includes(status)) return { error: dealerErrorText("invalid_status") };
  const supabase = await createClient();
  const { error } = await supabase.rpc("dealer_set_lead_status", { p_lead_id: leadId, p_status: status });
  if (error) return fail(error.message, "dealer_set_lead_status");
  done();
  return { ok: true };
}
