/**
 * X-01 (docs/superpowers/specs/2026-10-29-x01-seguimiento-design.md): the
 * rules of a listing's follow-up — which states the user picks, what
 * "Guardar" does to them and what a private note may hold. The server
 * actions and the "Seguimiento" block share them.
 */
import { type InteractionStatus, STATUS } from "@/lib/copy";

/** app_config.listing_tracking.note_max_chars when the row is missing (design §10). */
export const NOTE_MAX_DEFAULT = 500;

const SELECTABLE: InteractionStatus[] = ["seen", "interested", "contacted", "visit_scheduled", "purchased", "discarded"];

/** The select's options: "Nuevo" is the worker's, never the user's. */
export function selectableStatuses(): { value: InteractionStatus; label: string }[] {
  return SELECTABLE.map((value) => ({ value, label: STATUS[value] }));
}

/** States that mean the user is following the listing past "Guardada". */
const FOLLOW_UP: InteractionStatus[] = ["contacted", "visit_scheduled"];

/** "Guardar" never lowers a follow-up: on Contactado or Visita agendada it only sets saved. */
export function statusOnSave(current: InteractionStatus): { kind: "setSaved" } | { kind: "setStatus"; status: "interested" } {
  return FOLLOW_UP.includes(current) ? { kind: "setSaved" } : { kind: "setStatus", status: "interested" };
}

/** Comprado is terminal in v1 and only reachable through recordPurchase; Nuevo is never picked. */
export function canChangeStatus(from: InteractionStatus, to: InteractionStatus): boolean {
  return from !== "purchased" && to !== "purchased" && to !== "new";
}

/**
 * A note as stored: trimmed, without NUL (Postgres text can't hold it), null
 * when empty. Over the limit is an error, never a silent cut. Characters are
 * counted like the database's char_length (code points, not UTF-16 units).
 */
export function normalizeNote(raw: string, max: number): { note: string | null } | { error: string } {
  const note = raw.replace(/\u0000/g, "").trim();
  if (!note) return { note: null };
  if ([...note].length > max) return { error: `La nota puede tener hasta ${max} caracteres.` };
  return { note };
}

/** app_config.listing_tracking, with the default when missing or malformed. */
export function listingTrackingConfig(raw: unknown): { noteMaxChars: number } {
  const value = (raw ?? {}) as Record<string, unknown>;
  const n = typeof value.note_max_chars === "number" ? value.note_max_chars : Number.NaN;
  return { noteMaxChars: Number.isFinite(n) && n > 0 ? Math.floor(n) : NOTE_MAX_DEFAULT };
}
