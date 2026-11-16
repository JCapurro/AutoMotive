/**
 * /admin/prospeccion: the cold prospecting bot's batch (worker/prospector,
 * docs/PROSPECCION.md). Pure: types, the wa.me link, the ready-made replies
 * and the weekly reply-rate summary. The page reads the rows with the service
 * role; every write goes through public.admin_prospect_action.
 */

export const FOUNDER_LINK = "https://www.eseauto.com.ar/fundador/f2458e22c59b";
/** Juan's guardrail: WhatsApp flags numbers that message many strangers a day. */
export const DAILY_CAP = 30;
const TIME_ZONE = "America/Argentina/Buenos_Aires";

export type ProspectStatus =
  | "new" | "no_contact" | "queued" | "contacted" | "followed_up" | "replied" | "not_interested" | "wrong_number" | "closed";
export type MessageStep = "first" | "followup" | "last";
export type HookType = "oportunidad" | "stock_viejo" | "precio_vs_zona" | "demanda" | "dejaron_de_publicarse";

export type ProspectRow = {
  id: number;
  kind: "agencia" | "persona";
  display_name: string;
  first_name: string | null;
  sources: string[];
  region: string | null;
  locality: string | null;
  phone: string | null;
  phone_source: string | null;
  phone_evidence: string | null;
  status: ProspectStatus;
  step_sent: number;
  next_due_on: string | null;
  listing_count: number | null;
  first_sent_at: string | null;
  last_sent_at: string | null;
  replied_at: string | null;
};

export type Variant = { hook_type: HookType; text: string; problems?: string[] };

export type MessageRow = {
  id: number;
  prospect_id: number;
  step: MessageStep;
  batch_date: string;
  status: "ready" | "sent" | "skipped" | "rejected" | "expired";
  facts: Record<string, unknown>;
  variants: Variant[];
  chosen_index: number | null;
  final_text: string | null;
  edited: boolean;
  hook_type: HookType | null;
  hook_url: string | null;
  review: Record<string, unknown>;
  sent_at: string | null;
};

export type EventRow = { prospect_id: number; message_id: number | null; kind: string; created_at: string };

export const STEP_LABEL: Record<MessageStep, string> = { first: "Primer mensaje", followup: "Seguimiento", last: "Último mensaje" };
export const HOOK_LABEL: Record<HookType, string> = {
  oportunidad: "Oportunidad fresca",
  stock_viejo: "Stock con más de 45 días",
  precio_vs_zona: "Precio contra su zona",
  demanda: "Búsquedas en su zona",
  dejaron_de_publicarse: "Avisos que dejaron de publicarse",
};
export const STATUS_LABEL: Record<ProspectStatus, string> = {
  new: "Sin mensaje", no_contact: "Sin contacto", queued: "Listo para enviar", contacted: "Enviado",
  followed_up: "Seguimiento enviado", replied: "Respondió", not_interested: "No le interesa",
  wrong_number: "Número equivocado", closed: "Cerrado",
};
export const REGION_LABEL: Record<string, string> = {
  amba: "AMBA", buenos_aires_resto: "Interior de Buenos Aires", cordoba: "Córdoba", litoral: "Litoral",
  nea: "NEA", cuyo: "Cuyo", noa: "NOA", patagonia: "Patagonia",
};

/** The calendar day in Argentina, YYYY-MM-DD. */
export function artDay(value: Date | string = new Date()): string {
  const d = typeof value === "string" ? new Date(value) : value;
  return new Intl.DateTimeFormat("en-CA", { timeZone: TIME_ZONE, year: "numeric", month: "2-digit", day: "2-digit" }).format(d);
}

export function waLink(phone: string | null, text: string): string | null {
  if (!phone || !/^549[1-3]\d{9}$/.test(phone)) return null;
  return `https://wa.me/${phone}?text=${encodeURIComponent(text)}`;
}

/** What Juan typed after the ML button showed the number, as 549XXXXXXXXXX; null when it isn't an Argentine mobile. */
export function waNumber(value: string): string | null {
  let d = value.replace(/\D/g, "").replace(/^00/, "");
  if (d.length === 11 && d.startsWith("0")) d = d.slice(1);
  if (d.length === 10) d = `549${d}`;
  else if (d.length === 12 && d.startsWith("54")) d = `549${d.slice(2)}`;
  return /^549[1-3]\d{9}$/.test(d) ? d : null;
}

/** "+54 9 341 312-3456"-ish for reading, not for dialing. */
export function phoneLabel(phone: string | null): string {
  if (!phone) return "—";
  const d = phone.replace(/^549/, "");
  const area = d.startsWith("11") ? 2 : 3;
  return `+54 9 ${d.slice(0, area)} ${d.slice(area, -4)}-${d.slice(-4)}`;
}

export function greetingName(p: Pick<ProspectRow, "first_name" | "display_name" | "kind">): string {
  return p.first_name ?? (p.kind === "agencia" ? p.display_name : "");
}

// ---------------------------------------------------------------------------
// Ready-made replies (the manual generator's, with the founder price for 3 months)
// ---------------------------------------------------------------------------

export type Reply = { key: string; label: string; text: (ctx: ReplyContext) => string };
export type ReplyContext = { name: string; hookUrl: string | null; hookCar: string | null; zone: string | null };

const hi = (name: string) => (name ? `Hola, ${name}. ` : "");

export const REPLIES: Reply[] = [
  {
    key: "pasamelo",
    label: "«Sí, pasámelo»",
    text: (c) =>
      `Dale, acá está${c.hookCar ? ` el ${c.hookCar}` : ""}: ${c.hookUrl ?? "(link del aviso)"}\n\n` +
      `Si te sirve que te avise de estos apenas salen, te armo la búsqueda con tus modelos${c.zone ? ` en ${c.zone}` : ""} y la dejás corriendo 7 días sin costo. ¿Qué modelos, años y presupuesto te armo?`,
  },
  {
    key: "info",
    label: "«Pasame más info»",
    text: () =>
      "Te cuento corto: cargás qué auto buscás (modelo, años, km, presupuesto y zona). Ese Auto lee los avisos nuevos de Mercado Libre, Marketplace, deRuedas, RosarioGarage y sitios de agencias, los compara con autos parecidos y te avisa cuando uno sale por debajo del resto.\n\n" +
      "Lo más rápido para verlo es con un caso tuyo: pasame uno o dos modelos que estés buscando y te la dejo andando 7 días sin costo.",
  },
  {
    key: "si",
    label: "«Sí, compramos»",
    text: () =>
      "Genial, gracias. ¿Qué modelos están buscando hoy, en qué años y en qué zona?\n\n" +
      "Te armo la búsqueda con un umbral, por ejemplo que te avise cuando un auto esté 10 % abajo de los comparables. En 7 días te cuento qué apareció y vemos si te sirve.",
  },
  { key: "mail", label: "Pedirle el mail", text: () => "Para armarte la cuenta necesito un mail: ahí te llegan los avisos. ¿Cuál uso?" },
  {
    key: "precio",
    label: "«¿Cuánto sale?»",
    text: () =>
      "El plan para agencias sale $100.000 por mes, con hasta 20 búsquedas a la vez. Para las primeras agencias hay precio fundador: $50.000 por mes los primeros 3 meses.\n\n" +
      "Pero antes te propongo probarlo 7 días gratis con tus modelos, sin tarjeta: si no te trae nada útil, no seguimos. ¿Qué modelos y zona te armo?",
  },
  {
    key: "mas",
    label: "«¿Qué más hace?»",
    text: () =>
      "Además de avisarte cuando aparece un auto por debajo del resto:\n\n" +
      "• Margen estimado en cada auto: lo que costaría comprarlo y ponerlo en condiciones contra lo que publican otras agencias por ese modelo.\n" +
      "• Alerta por margen: le ponés un mínimo en USD y te avisa al momento.\n" +
      "• Solo particulares: filtrás para que no te lleguen avisos de otras agencias.\n" +
      "• Mensaje listo para el vendedor, con las preguntas que conviene hacerle.\n" +
      "• Señales de riesgo: un «particular» con muchos avisos, el mismo auto en otro portal o fotos repetidas.\n\n" +
      "Si me pasás tu stock, te mando a mano cómo está cada auto contra los parecidos de tu zona, sin costo.",
  },
  {
    key: "stock",
    label: "«Mandame lo del stock»",
    text: () =>
      "Dale. Pasame los autos que tenés a la venta con modelo, versión, año, km y precio publicado (una foto de la lista también me sirve).\n\n" +
      "Te devuelvo cada auto contra los avisos parecidos de tu zona: cuántos hay, a qué precios están publicados y si apareció alguno más barato en los últimos días. Son precios publicados, no de venta.",
  },
  {
    key: "contratar",
    label: "«Lo quiero contratar»",
    text: () =>
      `¡Buenísimo! Desde este link lo contratás con el precio fundador, $50.000 por mes los primeros 3 meses (después pasa a $100.000, con aviso antes):\n${FOUNDER_LINK}\n\n` +
      "Entrás con tu mail, pagás por Mercado Pago y queda activo apenas se aprueba el pago. Podés cancelar cuando quieras desde Ajustes.",
  },
  {
    key: "amano",
    label: "«Ya lo miro yo»",
    text: () =>
      "Tiene sentido, la mayoría lo hace así. La diferencia es que no tenés que entrar a buscar: te llega el aviso cuando aparece y con cuánto está abajo de los comparables.\n\n" +
      "Si querés, lo probás 7 días al lado de lo que ya hacés y me decís cuál te encontró antes los autos.",
  },
  {
    key: "no",
    label: "«No compramos»",
    text: () => "Entiendo, gracias por responder. Si algún día salen a buscar, me escribís.\n\n¿Conocés a alguien del rubro que compre seguido? Me ayudaría mucho que me lo pases.",
  },
  { key: "luego", label: "«Ahora no / más adelante»", text: (c) => `${hi(c.name)}Dale, sin apuro. ¿Te parece si te escribo la semana que viene?` },
];

/** The facts' first hook, for the «pasámelo» reply. */
const spaces = (s: string) => s.replace(/\s+/g, " ");

/** The hook car the message actually offers: the one whose price is in its final text
 *  (Juan may have edited it or picked the other variant). None when it offers no car. */
export type Hook = { car: string | null; url: string | null; checkedAt: string | null; checkedBy: "pagina" | "colector" | null };

export function hookOf(m: Pick<MessageRow, "facts" | "final_text"> | null | undefined): Hook {
  const hooks = Array.isArray(m?.facts?.ganchos) ? (m!.facts.ganchos as Record<string, unknown>[]) : [];
  const text = spaces(m?.final_text ?? "");
  const h = hooks.find((g) => typeof g.precio_publicado === "string" && text.includes(spaces(g.precio_publicado)));
  const v = (h?.verificado ?? null) as { en?: unknown; como?: unknown } | null;
  return {
    car: typeof h?.auto === "string" ? h.auto : null,
    url: typeof h?.url === "string" ? h.url : null,
    checkedAt: typeof v?.en === "string" ? v.en : null,
    checkedBy: v?.como === "pagina" || v?.como === "colector" ? v.como : null,
  };
}

/** Past this, the hook car may be gone: Juan opens the listing before sending. */
export const HOOK_RECHECK_HOURS = 24;

export function hoursSince(iso: string | null, now: Date): number | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  return Number.isNaN(t) ? null : Math.max(0, Math.floor((now.getTime() - t) / 3_600_000));
}

// ---------------------------------------------------------------------------
// Today and the weekly summary
// ---------------------------------------------------------------------------

export function sentToday(events: EventRow[], today: string): { total: number; first: number } {
  const sent = events.filter((e) => e.kind === "sent" && artDay(e.created_at) === today);
  return { total: sent.length, first: sent.length };
}

export type RateRow = { key: string; label: string; sent: number; replied: number };

/**
 * Reply rate of the first messages sent in [from, to): a prospect counts as
 * replied when Juan marked it (replied_at set), whatever message it answered.
 */
export function replyRates(prospects: ProspectRow[], messages: MessageRow[], from: Date, to: Date) {
  const byId = new Map(prospects.map((p) => [p.id, p]));
  const firsts = messages.filter((m) => m.step === "first" && m.status === "sent" && m.sent_at
    && new Date(m.sent_at) >= from && new Date(m.sent_at) < to);
  const groups = {
    hook: new Map<string, RateRow>(), source: new Map<string, RateRow>(),
    kind: new Map<string, RateRow>(), region: new Map<string, RateRow>(),
  };
  const add = (map: Map<string, RateRow>, key: string, label: string, replied: boolean) => {
    const row = map.get(key) ?? { key, label, sent: 0, replied: 0 };
    row.sent += 1;
    if (replied) row.replied += 1;
    map.set(key, row);
  };
  let replied = 0;
  for (const m of firsts) {
    const p = byId.get(m.prospect_id);
    if (!p) continue;
    const r = Boolean(p.replied_at);
    if (r) replied += 1;
    add(groups.hook, m.hook_type ?? "?", m.hook_type ? HOOK_LABEL[m.hook_type] : "Sin tipo", r);
    for (const s of p.sources.length ? p.sources : ["?"]) add(groups.source, s, SOURCE_LABEL[s] ?? s, r);
    add(groups.kind, p.kind, p.kind === "agencia" ? "Agencia" : "Persona", r);
    add(groups.region, p.region ?? "?", (p.region && REGION_LABEL[p.region]) || "Sin región", r);
  }
  const sort = (m: Map<string, RateRow>) => [...m.values()].sort((a, b) => b.sent - a.sent);
  return {
    sent: firsts.length,
    replied,
    hook: sort(groups.hook), source: sort(groups.source), kind: sort(groups.kind), region: sort(groups.region),
  };
}

export const SOURCE_LABEL: Record<string, string> = {
  mercadolibre: "Mercado Libre", facebook: "Marketplace", deruedas: "deRuedas", rosariogarage: "RosarioGarage", autocosmos: "Autocosmos",
};

export type Board = {
  today: string;
  newToday: { message: MessageRow; prospect: ProspectRow }[];
  dueToday: { message: MessageRow; prospect: ProspectRow }[];
  waiting: ProspectRow[];
  replied: ProspectRow[];
  sentToday: number;
};

/** Splits the rows the page reads into its sections. */
export function buildBoard(prospects: ProspectRow[], messages: MessageRow[], events: EventRow[], now: Date): Board {
  const today = artDay(now);
  const byId = new Map(prospects.map((p) => [p.id, p]));
  const ready = messages
    .filter((m) => m.status === "ready" && byId.has(m.prospect_id))
    .map((message) => ({ message, prospect: byId.get(message.prospect_id)! }))
    .sort((a, b) => a.message.id - b.message.id);
  return {
    today,
    dueToday: ready.filter((r) => r.message.step !== "first"),
    newToday: ready.filter((r) => r.message.step === "first"),
    waiting: prospects
      .filter((p) => p.status === "contacted" || p.status === "followed_up")
      .sort((a, b) => (b.last_sent_at ?? "").localeCompare(a.last_sent_at ?? "")),
    replied: prospects.filter((p) => p.status === "replied").sort((a, b) => (b.replied_at ?? "").localeCompare(a.replied_at ?? "")),
    sentToday: sentToday(events, today).total,
  };
}
