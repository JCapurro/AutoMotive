/**
 * X-01 (docs/superpowers/specs/2026-10-29-x01-seguimiento-design.md): the
 * rules of a listing's follow-up — which states the user picks, what
 * "Guardar" does to them. The server actions and the "Seguimiento" block
 * share them. The private note was removed (Juan, 02/11): the column
 * user_listing_interactions.note stays dormant, nothing reads or writes it.
 */
import { type InteractionStatus, STATUS, TRACKING } from "@/lib/copy";

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
 * "Precio que pagaste" (§38): whole numbers only, "." as an optional
 * thousands separator ("9800", "9.800"). Anything else ("9800.50", "9,800")
 * is an error, never a guess: "9800.50" read as 980050 would store a wrong price.
 */
export function parsePurchasePrice(raw: string): { price: number | null } | { error: string } {
  const text = raw.trim();
  if (!text) return { price: null };
  const price = /^(\d+|\d{1,3}(\.\d{3})+)$/.test(text) ? Number(text.replace(/\./g, "")) : Number.NaN;
  if (!(Number.isSafeInteger(price) && price > 0)) return { error: TRACKING.purchasePriceInvalid };
  return { price };
}
