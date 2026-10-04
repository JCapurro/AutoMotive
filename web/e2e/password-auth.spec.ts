import { expect, test } from "@playwright/test";
import { E2E_EMAIL_DOMAIN, SUPABASE_URL } from "./support/env";
import { magicLink } from "./support/mail";

test("registro confirmado, ingreso y recuperación de contraseña", async ({ page, browser }, testInfo) => {
  if (!["localhost", "127.0.0.1", "::1"].includes(new URL(SUPABASE_URL).hostname)) {
    throw new Error("La prueba de emails requiere Supabase local.");
  }
  const email = `auth-${testInfo.project.name}-${Date.now()}@${E2E_EMAIL_DOMAIN}`;
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
  // Confirm in a different browser context: token-hash links need no PKCE cookie.
  const other = await browser.newContext();
  try {
    const confirming = await other.newPage();
    await confirming.goto(confirmation);
    await expect(confirming).toHaveURL(/\/app\/settings$/);
  } finally { await other.close(); }

  await login(password);
  await expect(page).toHaveURL(/\/app$/);
  await page.context().clearCookies();
  const recoverySince = new Date();
  await page.goto("/login?mode=recover");
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByRole("button", { name: "Enviar recuperación" }).click();
  await expect(page.getByText("Revisá tu email")).toBeVisible();
  await page.goto(await magicLink(email, recoverySince));
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
