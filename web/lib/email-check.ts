import "server-only";

import { promises as dns } from "node:dns";

import { emailSuggestion } from "@/lib/email-typos";

/**
 * «Mails que no son mails» (docs/AUTENTICACION.md): la prueba no pide
 * confirmar el mail, así que antes de crear una cuenta nueva se descarta lo
 * que no puede recibir nuestras alertas. Tres pasos, del más barato al más caro:
 *
 * 1. Errores de tipeo de los dominios comunes (gmail.con): los mismos que la
 *    landing ya sugiere (lib/email-typos.ts), acá frenan.
 * 2. Dominios de mail descartable (mailinator, yopmail…).
 * 3. El dominio tiene que aceptar mail (registros MX en el DNS). Si el DNS no
 *    contesta a tiempo, se deja pasar: una falla nuestra no frena a nadie.
 *
 * Solo para cuentas nuevas: quien ya tiene cuenta entra como siempre.
 */

export type EmailProblem = { reason: "typo"; suggestion: string } | { reason: "disposable" } | { reason: "no_mail" };

/** The usual throwaway inboxes. Matched on the domain and any subdomain of it. */
const DISPOSABLE = new Set([
  "mailinator.com", "yopmail.com", "yopmail.fr", "yopmail.net", "guerrillamail.com", "guerrillamail.net", "guerrillamail.org",
  "guerrillamailblock.com", "sharklasers.com", "grr.la", "pokemail.net", "spam4.me", "10minutemail.com", "10minutemail.net",
  "10minemail.com", "tempmail.com", "temp-mail.org", "temp-mail.io", "tempmail.net", "tempmailo.com", "tmpmail.org", "tmpmail.net",
  "tempr.email", "trashmail.com", "trashmail.de", "trashmail.net", "dispostable.com", "getnada.com", "nada.email", "maildrop.cc",
  "mohmal.com", "emailondeck.com", "fakeinbox.com", "throwawaymail.com", "mailnesia.com", "minuteinbox.com", "burnermail.io",
  "mailcatch.com", "mintemail.com", "mytemp.email", "moakt.com", "emailfake.com", "fakemail.net", "inboxkitten.com",
  "harakirimail.com", "mailpoof.com", "33mail.com", "getairmail.com", "dropmail.me", "1secmail.com", "1secmail.net",
  "1secmail.org", "mail.tm", "mailsac.com", "spamgourmet.com", "jetable.org", "luxusmail.org", "tempinbox.com", "hidingpost.com",
]);

/** Answers for a domain, kept for a while: the same domain comes back all day. */
const cache = new Map<string, { ok: boolean; at: number }>();
const CACHE_MS = 6 * 3600 * 1000;
const DNS_TIMEOUT_MS = 2500;

function domainOf(email: string): string {
  return email.slice(email.lastIndexOf("@") + 1).toLowerCase();
}

function isDisposable(domain: string): boolean {
  const parts = domain.split(".");
  for (let i = 0; i < parts.length - 1; i++) if (DISPOSABLE.has(parts.slice(i).join("."))) return true;
  return false;
}

/** True when the domain can take mail, false when the DNS says it can't, null when the DNS didn't answer. */
async function acceptsMail(domain: string): Promise<boolean | null> {
  const hit = cache.get(domain);
  if (hit && Date.now() - hit.at < CACHE_MS) return hit.ok;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<null>((resolve) => { timer = setTimeout(() => resolve(null), DNS_TIMEOUT_MS); });
  const lookup = dns.resolveMx(domain).then(
    // A "null MX" (RFC 7505: one record, exchange ".") says the domain takes no mail.
    (records) => records.some((r) => r.exchange && r.exchange !== "."),
    (error: NodeJS.ErrnoException) => (error.code === "ENOTFOUND" || error.code === "ENODATA" ? false : null),
  );
  const ok = await Promise.race([lookup, timeout]);
  clearTimeout(timer);
  if (ok !== null) cache.set(domain, { ok, at: Date.now() });
  return ok;
}

/** Why this (already well-formed, lower-case) email can't start a trial, or null when it can. */
export async function emailProblem(email: string): Promise<EmailProblem | null> {
  const domain = domainOf(email);
  const suggestion = emailSuggestion(email);
  if (suggestion) return { reason: "typo", suggestion };
  if (isDisposable(domain)) return { reason: "disposable" };
  if ((await acceptsMail(domain)) === false) return { reason: "no_mail" };
  return null;
}

/** What the person reads. */
export function emailProblemMessage(problem: EmailProblem): string {
  if (problem.reason === "typo") return `¿Quisiste decir ${problem.suggestion}? Revisá cómo escribiste tu email.`;
  if (problem.reason === "disposable") return "Usá tu email de siempre: a los emails temporales no les llegan las alertas.";
  return "Ese email no puede recibir mensajes. Revisá cómo lo escribiste (por ejemplo: nombre@gmail.com).";
}

/** For tests only. */
export function clearEmailCheckCache(): void {
  cache.clear();
}
