import { expect, type Page } from "@playwright/test";

import { createClient } from "@supabase/supabase-js";

import { query } from "./db";
import { SUPABASE_URL } from "./env";

export const E2E_PASSWORD = "e2e-password-123";

/**
 * A valid code for `email`, after the page asked for one. The local stack
 * renders the email templates it was started with, so instead of reading the
 * email, the Admin API issues the account's code again (it replaces the one
 * just mailed, as a second email would). The template itself is checked in
 * lib/auth-email-template.test.ts.
 */
export async function entryCode(email: string): Promise<string> {
  const admin = createClient(SUPABASE_URL, process.env.SUPABASE_SERVICE_ROLE_KEY!, { auth: { persistSession: false, autoRefreshToken: false } });
  const { data, error } = await admin.auth.admin.generateLink({ type: "recovery", email });
  const code = data?.properties?.email_otp;
  if (error || !code) throw new Error(`no entry code for ${email}: ${error?.message ?? "no email_otp"}`);
  return code;
}

/**
 * The suite signs up dozens of accounts from one IP within the hour, past the
 * real brakes (app_config.email_only_signup). The local database only: the
 * specs that test the brakes set their own rows.
 */
export async function resetAuthBrakes() {
  await query("delete from public.auth_throttle");
}

/** Enters through /login with the emailed code. A new email gets its email-only account here. */
export async function enterWithCode(page: Page, email: string, next = "/app") {
  await resetAuthBrakes();
  await page.goto(`/login?next=${encodeURIComponent(next)}`);
  await page.getByLabel("Email", { exact: true }).fill(email);
  const sent = page.getByText("Revisá tu email");
  const tooSoon = page.getByRole("alert").filter({ hasText: "tan seguido" });
  await page.getByRole("button", { name: "Mandame un código" }).click();
  await expect(sent.or(tooSoon)).toBeVisible();
  // Auth's own minimum between two emails to one address: the same email asked again within it.
  if (await tooSoon.isVisible()) {
    await page.waitForTimeout(61_000);
    await page.getByRole("button", { name: "Mandame un código" }).click();
  }
  await expect(sent).toBeVisible();
  await page.getByLabel("Código").fill(await entryCode(email));
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
}

/**
 * A full account (inbox proven, password chosen), as the old password signup
 * left it: the specs that use it can pay and aren't held to the email-only limits.
 */
export async function signUp(page: Page, email: string, next = "/app") {
  await enterWithCode(page, email, next);
  await choosePassword(page, next);
}

/** Right after entering with a code: the email-only account chooses its password at /app/cuenta. */
export async function choosePassword(page: Page, next = "/app") {
  await expect(page).not.toHaveURL(/\/login/);
  await page.goto(`/app/cuenta?next=${encodeURIComponent(next)}`);
  await expect(page.getByRole("heading", { name: "Elegí una contraseña" })).toBeVisible();
  await page.getByLabel("Contraseña", { exact: true }).fill(E2E_PASSWORD);
  await page.getByLabel("Repetí la contraseña").fill(E2E_PASSWORD);
  await page.getByRole("button", { name: "Guardar contraseña" }).click();
  await expect(page).toHaveURL((url) => url.pathname + url.search === next);
}
