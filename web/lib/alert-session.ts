import "server-only";

import { createHmac, timingSafeEqual } from "node:crypto";

/**
 * Scoped email signatures retained for feedback and previously sent links.
 * A signature is never proof of identity and must never create a session.
 * /r and /m only navigate; /f validates the "m" signature for that email.
 */
const MIN_SECRET_LENGTH = 32;
const SIGNATURE = /^[A-Za-z0-9_-]{22}$/;

/** Legacy signature scopes; retained for compatibility, never authentication. */
export type AlertLinkScope = "r" | "m";
export type AlertLink = { scope: AlertLinkScope; id: number; signature: string | null };

/** ALERT_LINK_SECRET, plus ALERT_LINK_SECRET_PREVIOUS while rotating. Shorter than 32 characters: ignored. */
export function alertLinkSecrets(env: Record<string, string | undefined> = process.env): string[] {
  return [env.ALERT_LINK_SECRET, env.ALERT_LINK_SECRET_PREVIOUS]
    .map((secret) => (secret ?? "").trim())
    .filter((secret) => secret.length >= MIN_SECRET_LENGTH);
}

/** HMAC-SHA256 of v1:<scope>:<id>:<user_id>, 128 bits, base64url: the same as worker/notifications/links.py. */
export function alertLinkSignature(secret: string, scope: AlertLinkScope, id: number, userId: string): string {
  return createHmac("sha256", secret).update(`v1:${scope}:${id}:${userId}`).digest().subarray(0, 16).toString("base64url");
}

export function validAlertLinkSignature(link: AlertLink, userId: string, secrets: string[] = alertLinkSecrets()): boolean {
  if (!link.signature || !SIGNATURE.test(link.signature)) return false;
  const given = Buffer.from(link.signature);
  return secrets.some((secret) => timingSafeEqual(given, Buffer.from(alertLinkSignature(secret, link.scope, link.id, userId))));
}
