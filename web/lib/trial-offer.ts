/**
 * Oferta cuando la prueba oculta autos (docs/OFERTA_PRUEBA.md). With the
 * trial's reserve on, a search with more published matches than the trial
 * admits shows part of them. The results page says how many it shows of how
 * many there are and offers the pass right there: a sheet that opens once, a
 * strip above the list and a card at its end.
 *
 * Counts only: nothing of a hidden listing reaches the browser
 * (my_search_hidden_results). The texts live here so the three places say the
 * same and the singulars are tested once.
 */

/** With fewer hidden matches than this the sheet never opens by itself. */
export const TRIAL_OFFER_SHEET_MIN = 5;

/** Where the offer is on the results page, as the events name it (trackTrialOffer). */
export const TRIAL_OFFER_SURFACES = ["sheet", "strip", "card"] as const;
export type TrialOfferSurface = (typeof TRIAL_OFFER_SURFACES)[number];

/** `shown`: what the list shows; `hidden`: published matches the trial doesn't show. */
export type TrialOffer = { shown: number; hidden: number; total: number };

/** A sentence in pieces: `mark` is the figure the page highlights. */
export type Segment = string | { mark: string };

const whole = (n: unknown): number => (typeof n === "number" && Number.isInteger(n) && n > 0 ? n : 0);

/** The offer's counts, or null when the trial hides nothing of this search. */
export function trialOffer(shown: unknown, hidden: unknown): TrialOffer | null {
  const h = whole(hidden);
  if (h === 0) return null;
  const s = whole(shown);
  return { shown: s, hidden: h, total: s + h };
}

/** Worth interrupting for: enough hidden matches (the strip and the card show with any). */
export function opensSheet(offer: TrialOffer): boolean {
  return offer.hidden >= TRIAL_OFFER_SHEET_MIN;
}

const autos = (n: number) => `${n} ${n === 1 ? "auto" : "autos"}`;

/** «Encontramos 78 autos. Tu prueba muestra 30.» */
export function sheetTitle({ shown, total }: TrialOffer): string {
  if (shown > 0) return `Encontramos ${autos(total)}. Tu prueba muestra ${shown}.`;
  return total === 1 ? "Encontramos 1 auto. Tu prueba no lo muestra." : `Encontramos ${autos(total)}. Tu prueba no muestra ninguno.`;
}

/** «Los otros 48 también coinciden con lo que pediste y siguen publicados.» */
export function sheetLead({ shown, hidden }: TrialOffer): Segment[] {
  if (shown === 0) {
    return hidden === 1
      ? ["Coincide con lo que pediste y sigue publicado."]
      : ["Los ", { mark: String(hidden) }, " coinciden con lo que pediste y siguen publicados."];
  }
  return hidden === 1
    ? ["El otro también coincide con lo que pediste y sigue publicado."]
    : ["Los otros ", { mark: String(hidden) }, " también coinciden con lo que pediste y siguen publicados."];
}

/** The strip: «Tu prueba muestra 30 de los 78 autos que coinciden.» */
export function stripText({ shown, total }: TrialOffer): Segment[] {
  if (shown === 0) {
    return total === 1
      ? ["Tu prueba no muestra el auto que coincide."]
      : ["Tu prueba no muestra ninguno de los ", { mark: String(total) }, " autos que coinciden."];
  }
  return ["Tu prueba muestra ", { mark: String(shown) }, " de los ", { mark: String(total) }, " autos que coinciden."];
}

/** The strip's button, which opens the sheet. */
export function seeAllLabel({ total }: TrialOffer): string {
  return total === 1 ? "Verlo" : "Ver todos";
}

/** The card's heading: «Y 48 más que coinciden». */
export function cardTitle({ shown, hidden }: TrialOffer): Segment[] {
  if (shown === 0) return ["Hay ", { mark: String(hidden) }, hidden === 1 ? " auto que coincide" : " autos que coinciden"];
  return ["Y ", { mark: String(hidden) }, hidden === 1 ? " más que coincide" : " más que coinciden"];
}

/** What the trial shows and what Particular adds. «Mejor oportunidad» is the list's default order (lib/sorts.ts). */
export function cardLead({ shown, total }: TrialOffer): string {
  const first = shown === 0 ? "Tu prueba no muestra ninguno." : shown === 1 ? "Tu prueba muestra el primero que encontramos." : `Tu prueba muestra los primeros ${shown} que encontramos.`;
  const all = total === 1 ? "lo ves" : `ves los ${total}, ordenados por mejor oportunidad,`;
  return `${first} Con Particular ${all} y te avisamos de los que aparezcan.`;
}

/** The pay button: «Ver los 78 · 7 días por $ 5.000». `price` already formatted (planPrice). */
export function payLabel({ total }: TrialOffer, days: number, price: string): string {
  return `${total === 1 ? "Verlo" : `Ver los ${total}`} · ${days} días por ${price}`;
}

/** The way out of the sheet: «Seguir con mis 30». */
export function keepLabel({ shown }: TrialOffer): string {
  return shown > 1 ? `Seguir con mis ${shown}` : shown === 1 ? "Seguir con el que veo" : "Ahora no";
}
