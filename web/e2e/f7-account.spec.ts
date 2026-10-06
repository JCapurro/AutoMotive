import { expect, test } from "@playwright/test";

import { query } from "./support/db";
import { E2E_EMAIL_DOMAIN } from "./support/env";
import { magicLink } from "./support/mail";

/**
 * F7, punto 7 (docs/TECHNICAL_PLAN.md): the legal pages, unsubscribing from
 * the link in an email (without signing in) and deleting the account.
 */

test("F7: privacidad, baja del email y borrar la cuenta", async ({ page, request }, testInfo) => {
  const email = `${testInfo.project.name}-f7-${Date.now()}@${E2E_EMAIL_DOMAIN}`;

  await test.step("las páginas legales, desde la landing y el login", async () => {
    await page.goto("/");
    await page.getByRole("link", { name: "Privacidad" }).click();
    await expect(page.getByRole("heading", { name: "Política de privacidad" })).toBeVisible();
    await page.goto("/login");
    await page.getByRole("link", { name: "Términos de uso" }).click();
    await expect(page.getByRole("heading", { name: "Términos de uso" })).toBeVisible();
  });

  await test.step("registro con email como canal", async () => {
    const since = new Date();
    await page.goto("/login");
    await page.getByLabel("Email").fill(email);
    await page.getByRole("link", { name: "Crear cuenta", exact: true }).click();
    await page.getByLabel("Email", { exact: true }).fill(email);
    await page.getByLabel("Contraseña", { exact: true }).fill("e2e-password-123");
    await page.getByLabel("Repetí la contraseña").fill("e2e-password-123");
    await page.getByRole("button", { name: "Crear cuenta", exact: true }).click();
    await expect(page.getByText("Revisá tu email")).toBeVisible();
    await page.goto(await magicLink(email, since));
    await page.getByRole("button", { name: "Confirmar mi email" }).click();
    await expect(page).toHaveURL(/\/app/);
    await query(`update public.profiles set default_channels = '{telegram,email,web}' where email = $1`, [email]);
  });

  const [{ token }] = await query<{ token: string }>(
    `select email_unsubscribe_token::text as token from public.profiles where email = $1`,
    [email],
  );
  const channels = async () =>
    (await query<{ c: string[] }>(`select default_channels as c from public.profiles where email = $1`, [email]))[0].c;

  await test.step("baja desde el link del email: abrirlo no cambia nada, el botón sí", async () => {
    const other = await page.context().browser()!.newPage(); // not signed in
    await other.goto(`/baja?t=${token}`);
    await expect(other.getByText("¿Dejar de recibir emails?")).toBeVisible();
    expect(await channels()).toContain("email");
    await other.getByRole("button", { name: "Dejar de recibir emails" }).click();
    await expect(other.getByText("Listo, no te mandamos más emails")).toBeVisible();
    expect(await channels()).toEqual(["telegram", "web"]);
    await other.close();
  });

  await test.step("baja en un clic (List-Unsubscribe-Post)", async () => {
    await query(`update public.profiles set default_channels = '{email,web}' where email = $1`, [email]);
    expect((await request.post(`/api/baja?t=${token}`)).status()).toBe(200);
    expect(await channels()).toEqual(["web"]);
    expect((await request.post(`/api/baja?t=00000000-0000-4000-8000-000000000000`)).status()).toBe(404);
  });

  await test.step("borrar la cuenta desde Ajustes", async () => {
    const since = new Date();
    await page.goto("/app/settings");
    await page.getByRole("button", { name: "Borrar mi cuenta" }).click();
    const confirm = page.getByRole("button", { name: "Borrar definitivamente" });
    await expect(confirm).toBeDisabled();
    await page.getByLabel(/para confirmar/).fill("BORRAR");
    await confirm.click();
    await expect(page).toHaveURL(/\/\?cuenta=borrada$/);
    await expect(page.getByText("Borramos tu cuenta y todos tus datos.")).toBeVisible();
    expect(await query(`select 1 from auth.users where email = $1`, [email])).toHaveLength(0);
    await page.goto("/app");
    await expect(page).toHaveURL(/\/login/);
    // The anonymous account_deleted event can't carry the e2e prefix: drop it here.
    await query(`delete from public.events where name = 'account_deleted' and user_id is null and created_at >= $1`, [
      since,
    ]);
  });
});
