import "server-only";

import { createHash, randomUUID } from "node:crypto";

import { cookies } from "next/headers";

import type { ExistingAccount } from "@/lib/email-only";
import { createAdminClient } from "@/lib/supabase/admin";

/**
 * Una prueba por persona (docs/AUTENTICACION.md, migración
 * 20261224120000_trial_signals): otra forma del mismo mail es la misma cuenta,
 * y cada cuenta nueva guarda el hash de su IP y de su dispositivo. Nada de
 * esto puede romper un alta: si falla, se registra y la prueba sigue.
 */

/** Long-lived and httpOnly: only the server reads it, and only to hash it. */
export const DEVICE_COOKIE = "am_dev";
const DEVICE_MAX_AGE = 2 * 365 * 86400;
const DEVICE_ID = /^[0-9a-f-]{36}$/;

export type CanonicalAccount = ExistingAccount & { email: string };

/** The account that owns another spelling of this inbox (juan.perez+2@gmail.com → juanperez@gmail.com), or null. */
export async function accountForCanonicalEmail(email: string): Promise<CanonicalAccount | null> {
  const { data, error } = await createAdminClient().rpc("auth_account_for_canonical_email", { p_email: email });
  if (error) {
    console.error("auth_account_for_canonical_email failed:", error.message);
    return null;
  }
  const row = data?.[0];
  return row ? { user_id: row.user_id, email: row.email, email_only: row.email_only, confirmed: row.confirmed } : null;
}

/** This browser's device id as a hash, minting the cookie the first time. Null if cookies can't be read or written here. */
export async function deviceKey(): Promise<string | null> {
  try {
    const store = await cookies();
    let id = store.get(DEVICE_COOKIE)?.value;
    if (!id || !DEVICE_ID.test(id)) {
      id = randomUUID();
      store.set(DEVICE_COOKIE, id, { httpOnly: true, secure: true, sameSite: "lax", path: "/", maxAge: DEVICE_MAX_AGE });
    }
    return createHash("sha256").update(`device:${id}`).digest("hex").slice(0, 32);
  } catch (error) {
    console.error("device cookie failed:", error instanceof Error ? error.message : error);
    return null;
  }
}

/** Saves the new account's signals. Never throws. */
export async function recordTrialSignals(userId: string, email: string, ipKey: string): Promise<void> {
  try {
    const { error } = await createAdminClient().rpc("record_trial_signals", {
      p_user: userId, p_email: email, p_ip_key: ipKey, p_device_key: await deviceKey(),
    });
    if (error) console.error("record_trial_signals failed:", error.message);
  } catch (error) {
    console.error("record_trial_signals failed:", error instanceof Error ? error.message : error);
  }
}
