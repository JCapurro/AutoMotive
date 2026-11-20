/**
 * The mobile, asked again (Juan, 20/11: a user who created the search without
 * leaving it is asked on the other pages too). Each place keeps its own
 * «closed» mark in the browser, and the mark expires: closing the prompt on the
 * results does not silence it on the home, and after a week it comes back.
 * Pure: the component reads and writes localStorage.
 */

export const PHONE_PROMPT_PLACES = ["results", "home", "saved", "listing"] as const;
export type PhonePromptPlace = (typeof PHONE_PROMPT_PLACES)[number];

/** How long a closed prompt stays closed in that place. */
export const PHONE_PROMPT_QUIET_DAYS = 7;
const DAY_MS = 86_400_000;

export const closedKey = (place: PhonePromptPlace) => `ea_phone_prompt_closed_${place}`;
export const viewedKey = (place: PhonePromptPlace) => `ea_phone_prompt_viewed_${place}`;

/** `raw`: what closedKey() holds (the time it was closed, in ms), or null. */
export function promptQuiet(raw: string | null, now: number): boolean {
  const at = Number(raw);
  if (!raw || !Number.isFinite(at) || at <= 0 || at > now) return false;
  return now - at < PHONE_PROMPT_QUIET_DAYS * DAY_MS;
}

export function isPhonePromptPlace(value: unknown): value is PhonePromptPlace {
  return (PHONE_PROMPT_PLACES as readonly unknown[]).includes(value);
}

/** Why leave it, said for where the person is. */
export const PHONE_PROMPT_TEXT: Record<PhonePromptPlace, { title: string; body: string }> = {
  results: {
    title: "Dejanos tu celular",
    body: "Es opcional. Lo usamos solo por si necesitamos contactarte sobre tu búsqueda o tu cuenta. No se lo pasamos a nadie sin tu permiso: solo llega a una agencia si vos pedís que te contacte por un auto.",
  },
  home: {
    title: "Todavía no nos dejaste tu celular",
    body: "Es opcional. Sirve por si necesitamos contactarte por una búsqueda, y para tenerlo listo si le pedís a una agencia que te llame por un auto. No se lo pasamos a nadie sin tu permiso.",
  },
  saved: {
    title: "¿Te avisamos al celular por estos autos?",
    body: "Es opcional. Dejalo por si necesitamos contactarte por alguno de tus guardados. No se lo pasamos a nadie sin tu permiso.",
  },
  listing: {
    title: "Dejá tu celular para no perder este auto",
    body: "Es opcional. Sirve por si necesitamos contactarte por tu búsqueda, y queda listo si pedís que una agencia te llame. No se lo pasamos a nadie sin tu permiso.",
  },
};
