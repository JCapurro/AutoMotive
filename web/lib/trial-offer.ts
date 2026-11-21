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

/**
 * What the trial shows and what Particular adds. «Mejor oportunidad» is the list's default order (lib/sorts.ts).
 * `randomStock` (app_config.trial_reserve.random_stock): the trial shows a random sample, not the first ones found.
 */
export function cardLead({ shown, total }: TrialOffer, randomStock = false): string {
  // A random sample (docs/PRUEBA_COMPLETA.md): «Tu prueba muestra 45 de los 68.»
  if (randomStock && shown > 0) {
    return `Tu prueba muestra ${shown} de los ${total}. Con Particular los ves todos, ordenados por mejor oportunidad, y te avisamos de los que aparezcan.`;
  }
  const first = shown === 0 ? "Tu prueba no muestra ninguno."
    : shown === 1 ? "Tu prueba muestra el primero que encontramos." : `Tu prueba muestra los primeros ${shown} que encontramos.`;
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

/*
 * «40 + N» (docs/PRUEBA_COMPLETA.md): the trial has shown its `newMax` new
 * cars and adds no more. The same sheet and strip, in a "complete" variant;
 * `offer` holds the search's counts (hidden may be 0 here).
 */

/** «Tu prueba ya te mostró sus 5 autos nuevos», for the page's other notices. */
export function trialCompleteText(newMax: number): string {
  return newMax === 1 ? "Tu prueba ya te mostró su auto nuevo" : `Tu prueba ya te mostró sus ${newMax} autos nuevos`;
}

/** For the new-search forms: «Tu prueba ya te mostró sus 5 autos nuevos, así que no vamos a avisarte de otros.» */
export function trialCompleteNoAlerts(newUsed: number): string {
  return `${trialCompleteText(newUsed)}, así que no vamos a avisarte de otros.`;
}

/** The sheet's title: «Tu prueba ya te mostró 5 autos nuevos.» */
export function completeTitle(newMax: number): string {
  return `Tu prueba ya te mostró ${autos(newMax)} ${newMax === 1 ? "nuevo" : "nuevos"}.`;
}

/** «Hay 23 más que coinciden con lo que pediste y siguen publicados.», or that nothing new comes in. */
export function completeLead({ hidden }: TrialOffer): Segment[] {
  const stopped = "Desde ahora tu prueba no suma autos nuevos.";
  if (hidden === 0) return [stopped];
  return hidden === 1
    ? [`${stopped} Hay 1 más que coincide con lo que pediste y sigue publicado.`]
    : [`${stopped} Hay `, { mark: String(hidden) }, " más que coinciden con lo que pediste y siguen publicados."];
}

/** The pay button: payLabel with matches to see, «Seguir recibiendo · 7 días por $ 5.000» without. */
export function completePayLabel(offer: TrialOffer, days: number, price: string): string {
  return offer.hidden > 0 ? payLabel(offer, days, price) : `Seguir recibiendo · ${days} días por ${price}`;
}

/** The strip: «Tu prueba ya te mostró sus 5 autos nuevos. Hay 23 más que coinciden.» */
export function completeStripText({ hidden }: TrialOffer, newMax: number): Segment[] {
  const done: Segment[] = newMax === 1
    ? ["Tu prueba ya te mostró su auto nuevo."]
    : ["Tu prueba ya te mostró sus ", { mark: String(newMax) }, " autos nuevos."];
  if (hidden === 0) return done;
  return hidden === 1
    ? [...done, " Hay 1 más que coincide."]
    : [...done, " Hay ", { mark: String(hidden) }, " más que coinciden."];
}

/** The strip's button in the complete variant. */
export const COMPLETE_STRIP_BUTTON = "Seguir recibiendo";

/** The sheet's badge in the complete variant. */
export const COMPLETE_BADGE = "Prueba gratis completa";
