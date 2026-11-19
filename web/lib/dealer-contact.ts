/**
 * «Quiero que me contacten» (spec §3.8, §6.4): the consent the buyer ticks,
 * the phone as the RPC stores it and the WhatsApp link shown after the lead
 * exists. Pure; no buyer data leaves through here except in the link the
 * buyer opens themself.
 */

/** /privacidad's line (spec §6.4): shown only with the channel on; Juan approves it before turning the channel on. */
export const DEALER_CONTACT_PRIVACY_LINE =
  "Si tocás «Quiero que me contacten», le pasamos tu nombre, tu teléfono y tu mensaje a esa agencia, y a nadie más.";

/** The text saved with the lead (dealer_leads.consent_text, 20 to 300 characters). */
export function consentText(dealerName: string): string {
  const name = dealerName.trim() || "la agencia";
  return `Acepto que Ese Auto le pase mi nombre, mi teléfono y mi mensaje a ${name} para que me contacte por este auto.`.slice(0, 300);
}

/** Digits only, 8 to 15 of them (what request_dealer_contact keeps), or null. */
export function normalizePhone(raw: string | null | undefined): string | null {
  const digits = String(raw ?? "").replace(/\D/g, "");
  return /^\d{8,15}$/.test(digits) ? digits : null;
}

/** «Hola, me interesa el Ford Focus 2017. ¿Sigue disponible?»: the message's starting text. */
export function defaultMessage(vehicle: string): string {
  return `Hola, me interesa el ${vehicle}. ¿Sigue disponible?`;
}

/** «Hola, vi tu Ford Focus 2017 en Ese Auto y te pedí que me contactes. Soy Ana.» */
export function whatsappText(vehicle: string, name: string): string {
  const who = name.trim();
  return `Hola, vi tu ${vehicle} en Ese Auto y te pedí que me contactes.${who ? ` Soy ${who}.` : ""}`;
}

/** wa.me link for the dealer's WhatsApp (digits with 54), or null when there is none. */
export function whatsappUrl(digits: string | null | undefined, text: string): string | null {
  const phone = String(digits ?? "").replace(/\D/g, "");
  if (!/^\d{10,15}$/.test(phone)) return null;
  return `https://wa.me/${phone}?text=${encodeURIComponent(text)}`;
}

/** §6.6: the buyer's errors in words. */
export function leadErrorText(message: string | null | undefined): string {
  const code = String(message ?? "").trim();
  if (code === "consent_required") return "Marcá la casilla para que le pasemos tus datos.";
  if (code === "contact_unavailable") return "Este auto ya no está disponible.";
  if (code === "invalid_contact:phone") return "Revisá el teléfono.";
  if (code === "invalid_contact:name") return "Revisá tu nombre.";
  if (code === "invalid_contact:message") return "El mensaje es muy largo.";
  if (code === "rate_limited") return "Ya pediste muchos contactos hoy. Probá mañana.";
  if (code === "dealer_program_off") return "Esto todavía no está disponible.";
  if (code === "not_signed_in") return "Entrá a tu cuenta para pedir contacto.";
  return "No pudimos guardar. Probá de nuevo.";
}

/** «el 18/11» for «Ya le pediste a … que te contacte el …». */
export function leadDate(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString("es-AR", { day: "numeric", month: "numeric", timeZone: "America/Argentina/Buenos_Aires" });
}

/** listing_dealer_card()'s JSON (spec §3.8), read tolerantly. */
export type DealerCard = {
  dealerId: number | null;
  dealerName: string | null;
  badge: boolean;
  isDirecto: boolean;
  hiddenReason: string | null;
  confirmedAt: string | null;
  viewerIsMember: boolean;
  canRequest: boolean;
  myLead: { id: number; createdAt: string; status: string } | null;
  whatsapp: string | null;
};

export function parseDealerCard(raw: unknown): DealerCard | null {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const r = raw as Record<string, unknown>;
  const lead = r.my_lead && typeof r.my_lead === "object" ? (r.my_lead as Record<string, unknown>) : null;
  const str = (v: unknown) => (typeof v === "string" && v ? v : null);
  return {
    dealerId: typeof r.dealer_id === "number" ? r.dealer_id : null,
    dealerName: str(r.dealer_name),
    badge: r.badge === true,
    isDirecto: r.is_directo === true,
    hiddenReason: str(r.hidden_reason),
    confirmedAt: str(r.confirmed_at),
    viewerIsMember: r.viewer_is_member === true,
    canRequest: r.can_request === true,
    myLead: lead && typeof lead.id === "number" ? { id: lead.id, createdAt: str(lead.created_at) ?? "", status: str(lead.status) ?? "new" } : null,
    whatsapp: str(r.whatsapp),
  };
}

/** request_dealer_contact()'s answer. */
export type LeadResult = { leadId: number; created: boolean; dealerName: string; whatsapp: string | null; vehicle: string; createdAt: string };

export function parseLeadResult(raw: unknown): LeadResult | null {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const r = raw as Record<string, unknown>;
  if (typeof r.lead_id !== "number") return null;
  return {
    leadId: r.lead_id,
    created: r.created === true,
    dealerName: typeof r.dealer_name === "string" ? r.dealer_name : "la agencia",
    whatsapp: typeof r.whatsapp === "string" && r.whatsapp ? r.whatsapp : null,
    vehicle: typeof r.vehicle === "string" ? r.vehicle : "auto",
    createdAt: typeof r.created_at === "string" ? r.created_at : "",
  };
}

/** «Stock confirmado hace 3 días» (directo listings only). */
export function confirmedAgoText(iso: string | null, now: Date = new Date()): string | null {
  if (!iso) return null;
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return null;
  const days = Math.max(0, Math.floor((now.getTime() - at.getTime()) / 86_400_000));
  if (days === 0) return "Stock confirmado hoy";
  return `Stock confirmado hace ${days} ${days === 1 ? "día" : "días"}`;
}
