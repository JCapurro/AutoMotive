import { expect, test } from "@playwright/test";
import { E2E_EMAIL_DOMAIN, SUPABASE_URL } from "./support/env";
import { magicLink } from "./support/mail";
import { closeDb, query } from "./support/db";

let testEmail: string | undefined;
test.afterEach(async () => {
  try { if (testEmail) await query("delete from auth.users where email = $1", [testEmail]); }
  finally { testEmail = undefined; await closeDb(); }
});

test("registro confirmado, ingreso y recuperación de contraseña", async ({ page, browser }, testInfo) => {
  if (!["localhost", "127.0.0.1", "::1"].includes(new URL(SUPABASE_URL).hostname)) {
    throw new Error("La prueba de emails requiere Supabase local.");
  }
  const email = `auth-${testInfo.project.name}-${Date.now()}@${E2E_EMAIL_DOMAIN}`;
  testEmail = email;
  const password = "e2e-original-password-123";
  const replacement = "e2e-replacement-password-456";
  const since = new Date();
  await page.goto("/login?mode=signup&next=/app/settings");
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Contraseña", { exact: true }).fill(password);
  await page.getByLabel("Repetí la contraseña").fill(password);
  await page.getByRole("button", { name: "Crear cuenta", exact: true }).click();
  await expect(page.getByText("Revisá tu email")).toBeVisible();

  const login = async (value: string) => {
    await page.goto("/login");
    await page.getByLabel("Email", { exact: true }).fill(email);
    await page.getByLabel("Contraseña", { exact: true }).fill(value);
    await page.getByRole("button", { name: "Ingresar", exact: true }).click();
  };
  await login(password);
  await expect(page.getByRole("alert")).toContainText("Confirmá tu email");
  const confirmation = await magicLink(email, since);
  const preview = await page.request.head(confirmation);
  expect(preview.status()).toBe(200);
  // Confirm in a different browser context: token-hash links need no PKCE cookie.
  const other = await browser.newContext();
  try {
    const confirming = await other.newPage();
    await confirming.goto(confirmation);
    await expect(confirming).toHaveURL(/\/auth\/confirm-email\?/);
    const [account] = await query("select email_confirmed_at from auth.users where email = $1", [email]);
    expect(account.email_confirmed_at).toBeNull();
    await confirming.getByRole("button", { name: "Confirmar mi email" }).click();
    await expect(confirming).toHaveURL(/\/app\/settings$/);
  } finally { await other.close(); }

  // Reusing the link must offer login and resend, rather than another registration.
  await page.goto(confirmation);
  await page.getByRole("button", { name: "Confirmar mi email" }).click();
  await expect(page).toHaveURL(/\/login\?error=link&mode=login/);
  await expect(page.getByRole("button", { name: "Ingresar", exact: true })).toBeVisible();
  await expect(page.getByLabel("Email para reenviar la confirmación")).toBeEditable();
  await page.getByLabel("Email para reenviar la confirmación").fill(email);
  await page.getByRole("button", { name: "Reenviar confirmación" }).click();
  await expect(page.getByRole("status")).toContainText("Solicitud recibida");

  await login(password);
  await expect(page).toHaveURL(/\/app$/);
  await page.context().clearCookies();
  const recoverySince = new Date();
  await page.goto("/login?mode=recover");
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByRole("button", { name: "Enviar recuperación" }).click();
  await expect(page.getByText("Revisá tu email")).toBeVisible();
  await page.goto(await magicLink(email, recoverySince));
  await page.getByRole("button", { name: "Elegir nueva contraseña" }).click();
  await expect(page).toHaveURL(/\/auth\/reset-password$/);
  await page.getByLabel("Nueva contraseña", { exact: true }).fill(replacement);
  await page.getByLabel("Repetí la contraseña").fill(replacement);
  await page.getByRole("button", { name: "Guardar contraseña" }).click();
  await expect(page).toHaveURL(/\/login\?password=updated$/);
  await login(password);
  await expect(page.getByRole("alert")).toContainText("No pudimos ingresar");
  await login(replacement);
  await expect(page).toHaveURL(/\/app$/);
});
