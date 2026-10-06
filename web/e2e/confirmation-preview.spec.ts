import { createClient } from "@supabase/supabase-js";
import { expect, test } from "@playwright/test";
import { E2E_EMAIL_DOMAIN, SUPABASE_URL } from "./support/env";

test("una vista previa no consume el enlace y una cuenta confirmada puede ingresar", async ({ page, browser }, testInfo) => {
  if (!["localhost", "127.0.0.1", "::1"].includes(new URL(SUPABASE_URL).hostname)) throw new Error("Supabase local requerido");
  const admin = createClient(SUPABASE_URL, process.env.SUPABASE_SERVICE_ROLE_KEY!, { auth: { persistSession: false, autoRefreshToken: false } });
  const email = `preview-${testInfo.project.name}-${Date.now()}@${E2E_EMAIL_DOMAIN}`;
  const password = "preview-original-password-123";
  const replacement = "preview-new-password-456";
  const { data, error } = await admin.auth.admin.generateLink({ type: "signup", email, password });
  if (error || !data.user || !data.properties) throw new Error("No se pudo generar la cuenta local de prueba");
  const accountId = data.user.id;
  const base = testInfo.project.use.baseURL!;
  const confirmation = `${base}/auth/callback?token_hash=${data.properties.hashed_token}&type=signup&next=/app/settings`;
  try {
    const preview = await page.request.head(confirmation);
    expect(preview.status()).toBe(200);
    const other = await browser.newContext();
    try {
      const confirming = await other.newPage();
      await confirming.goto(confirmation);
      await expect(confirming.getByRole("button", { name: "Confirmar mi email" })).toBeVisible();
      const before = await admin.auth.admin.getUserById(accountId);
      expect(before.data.user?.email_confirmed_at).toBeFalsy();
      await confirming.getByRole("button", { name: "Confirmar mi email" }).click();
      await expect(confirming).toHaveURL(/\/app\/settings$/);
    } finally { await other.close(); }

    await page.goto(confirmation);
    await page.getByRole("button", { name: "Confirmar mi email" }).click();
    await expect(page).toHaveURL(/\/login\?error=link&mode=login/);
    await page.getByLabel("Email para reenviar la confirmación").fill(email);
    await page.getByRole("button", { name: "Reenviar confirmación" }).click();
    await expect(page.getByRole("status")).toContainText("Solicitud recibida");
    await page.getByLabel("Email", { exact: true }).fill(email);
    await page.getByLabel("Contraseña", { exact: true }).fill(password);
    await page.getByRole("button", { name: "Ingresar", exact: true }).click();
    await expect(page).toHaveURL(/\/app\/settings$/);
    await page.context().clearCookies();

    const recovery = await admin.auth.admin.generateLink({ type: "recovery", email });
    if (recovery.error || !recovery.data.properties) throw new Error("No se pudo generar la recuperación local");
    await page.goto(`${base}/auth/confirm?token_hash=${recovery.data.properties.hashed_token}&type=recovery`);
    await page.getByRole("button", { name: "Elegir nueva contraseña" }).click();
    await expect(page).toHaveURL(/\/auth\/reset-password$/);
    await page.getByLabel("Nueva contraseña", { exact: true }).fill(replacement);
    await page.getByLabel("Repetí la contraseña").fill(replacement);
    await page.getByRole("button", { name: "Guardar contraseña" }).click();
    await expect(page).toHaveURL(/\/login\?password=updated$/);
    await page.getByLabel("Email", { exact: true }).fill(email);
    await page.getByLabel("Contraseña", { exact: true }).fill(replacement);
    await page.getByRole("button", { name: "Ingresar", exact: true }).click();
    await expect(page).toHaveURL(/\/app$/);
  } finally {
    const cleanup = await admin.auth.admin.deleteUser(accountId);
    if (cleanup.error) throw new Error("No se pudo limpiar la cuenta local de prueba");
  }
});
