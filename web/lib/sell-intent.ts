/**
 * PAR-05, Prueba B (docs/BACKLOG_PRODUCTO_2026-10.md): «¿Tenés que vender tu
 * auto actual para comprar?», asked in the welcome email and as one line in
 * the listing page. A «Sí» leads to /vender-mi-auto, which only offers to let
 * the person know when the reference of published prices exists: it never
 * promises a price, an amount or that the reference is ready. Nothing is
 * shared with anyone. Pure: tests, pages and actions import it.
 */

export const SELL_INTENT = {
  question: "¿Tenés que vender tu auto actual para comprar?",
  yes: "Sí",
  no: "No",
  pitch:
    "Estamos armando una referencia de precios publicados para el auto que vas a vender. ¿Querés que te avisemos cuando esté?",
  emailLabel: "Te avisamos a",
  notify: "Avisame cuando esté",
  agencies: "También me interesa que agencias me contacten para comprarlo",
  notified: "Listo. Te vamos a avisar cuando la referencia esté lista.",
  save: "Guardar",
  noThanks: "Gracias por responder.",
  noThanksDetail: "Seguimos buscando el auto que querés comprar.",
  confirm: "Confirmá tu respuesta",
  send: "Enviar",
  invalid: "Este link no es válido",
  invalidDetail: "Si querés responder, entrá a Ese Auto y abrí cualquier publicación.",
} as const;

/**
 * The Privacy line for the agencies checkbox: a draft for Juan. It shows only
 * with app_config.sell_intent.agencies_contact on, the same flag as the checkbox.
 */
export const SELL_INTENT_PRIVACY_LINE =
  "Si marcás que te interesa que agencias te contacten para comprar tu auto, guardamos esa preferencia. No compartimos tus datos con ninguna agencia sin que lo marques, y podés desmarcarlo cuando quieras.";

export type SellIntentAnswer = "yes" | "no";
export type SellIntentSource = "email" | "ficha";

export type SellIntentConfig = {
  /** The question is shown (email and listing page). */
  ask: boolean;
  /** The agencies checkbox and its Privacy line. OFF until Juan approves the line. */
  agenciesContact: boolean;
};

/** app_config.sell_intent; each switch only when explicitly true (no row: nothing shows). */
export function sellIntentConfig(raw: unknown): SellIntentConfig {
  const value = raw !== null && typeof raw === "object" && !Array.isArray(raw) ? (raw as Record<string, unknown>) : {};
  return { ask: value.ask === true, agenciesContact: value.agencies_contact === true };
}

/** "si" / "no" from the email links, "yes" / "no" from the forms; anything else is null. */
export function sellIntentAnswer(value: unknown): SellIntentAnswer | null {
  if (value === "si" || value === "yes") return "yes";
  if (value === "no") return "no";
  return null;
}

/** A lifecycle_emails id from a link or a hidden input. */
export function sellIntentEmailId(value: unknown): number | null {
  return typeof value === "string" && /^\d{1,15}$/.test(value) ? Number(value) : null;
}

/** juan@gmail.com → j***@gmail.com, for an unsigned link (only without ALERT_LINK_SECRET). */
export function maskEmail(email: string): string {
  const at = email.lastIndexOf("@");
  if (at < 1) return "***";
  return `${email[0]}***${email.slice(at)}`;
}

/** Only an account with an email answers: never an anonymous (Telegram) session. */
export function canAnswer(user: { email: string | null } | null): boolean {
  return Boolean(user?.email);
}

/** The ficha line: the question is on, the account can answer and hasn't yet. */
export function showFichaQuestion(config: SellIntentConfig, user: { email: string | null } | null, answered: boolean): boolean {
  return config.ask && canAnswer(user) && !answered;
}

/** The answer's columns. «No» clears the notice and the agencies preference (the table's check). */
export function answerRow(answer: SellIntentAnswer, source: SellIntentSource) {
  return answer === "no"
    ? { answer, source, wants_notice: false, agencies_contact_ok: false }
    : { answer, source };
}

/** The notice's columns, after «Sí». The agencies box only counts with the flag on. */
export function noticeRow(agencies: boolean, config: SellIntentConfig): { wants_notice: true; agencies_contact_ok?: boolean } {
  return config.agenciesContact ? { wants_notice: true, agencies_contact_ok: agencies } : { wants_notice: true };
}

/** Where the ficha line goes back to after «No»: only a listing page. */
export function fichaReturnPath(value: unknown): string | null {
  return typeof value === "string" && /^\/app\/listings\/\d{1,18}$/.test(value) ? value : null;
}

export type SellIntentCounts = { answered: number; yes: number; no: number; pctYes: number | null; wantsNotice: number; agenciesContactOk: number };
export type SellIntentMetrics = SellIntentCounts & {
  since: string | null;
  newAccounts: number;
  askedByEmail: number;
  listingViewers: number;
  bySource: Record<SellIntentSource, SellIntentCounts>;
};

/** public.admin_sell_intent_metrics' jsonb, tolerant: a missing number is 0. */
export function sellIntentMetrics(raw: unknown): SellIntentMetrics | null {
  if (raw === null || typeof raw !== "object" || Array.isArray(raw)) return null;
  const value = raw as Record<string, unknown>;
  const n = (v: unknown) => (typeof v === "number" && Number.isFinite(v) ? v : 0);
  const counts = (v: unknown): SellIntentCounts => {
    const c = v !== null && typeof v === "object" ? (v as Record<string, unknown>) : {};
    return {
      answered: n(c.answered), yes: n(c.yes), no: n(c.no),
      pctYes: typeof c.pctYes === "number" ? c.pctYes : null,
      wantsNotice: n(c.wantsNotice), agenciesContactOk: n(c.agenciesContactOk),
    };
  };
  const bySource = (value.bySource ?? {}) as Record<string, unknown>;
  return {
    ...counts(value),
    since: typeof value.since === "string" ? value.since : null,
    newAccounts: n(value.newAccounts),
    askedByEmail: n(value.askedByEmail),
    listingViewers: n(value.listingViewers),
    bySource: { email: counts(bySource.email), ficha: counts(bySource.ficha) },
  };
}
