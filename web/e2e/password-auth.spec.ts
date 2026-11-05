import { expect, type Page, test } from "@playwright/test";
import { E2E_EMAIL_DOMAIN, SUPABASE_URL } from "./support/env";
import { choosePassword, E2E_PASSWORD, enterWithCode, entryCode, resetAuthBrakes } from "./support/auth";
import { closeDb, query } from "./support/db";

let testEmail: string | undefined;
test.afterEach(async () => {
  try { if (testEmail) await query("delete from auth.users where email = $1", [testEmail]); }
  finally { testEmail = undefined; await closeDb(); }
});

async function signOutFromMenu(page: Page) {
  await page.getByRole("button", { name: "Tu cuenta" }).click();
  await page.getByRole("menuitem", { name: "Cerrar sesión" }).click();
  await expect(page).toHaveURL(/\/$/);
}

async function withPassword(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByRole("button", { name: "Tengo contraseña" }).click();
  await page.getByLabel("Contraseña", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Ingresar", exact: true }).click();
}

test("entrar con código, elegir contraseña, el menú de la cuenta y cambiar la contraseña", async ({ page }, testInfo) => {
  if (!["localhost", "127.0.0.1", "::1"].includes(new URL(SUPABASE_URL).hostname)) {
    throw new Error("La prueba de emails requiere Supabase local.");
  }
  // Enters by code twice with the same email: Auth may make the second wait its minute.
  test.setTimeout(300_000);
  const email = `auth-${testInfo.project.name}-${Date.now()}@${E2E_EMAIL_DOMAIN}`;
  testEmail = email;
  const replacement = "e2e-replacement-password-456";

  await test.step("un código equivocado no entra; el correcto, sí", async () => {
    await resetAuthBrakes();
    await page.goto("/login?mode=signup&next=%2Fapp%2Fsettings");
    // Old signup links land on the same single screen.
    await expect(page.getByRole("button", { name: "Mandame un código" })).toBeVisible();
    await page.getByLabel("Email", { exact: true }).fill(email);
    await page.getByRole("button", { name: "Mandame un código" }).click();
    await expect(page.getByText("Revisá tu email")).toBeVisible();
    const code = await entryCode(email);
    await page.getByLabel("Código").fill(code === "000000" ? "111111" : "000000");
    await page.getByRole("button", { name: "Entrar", exact: true }).click();
    await expect(page.getByRole("alert").filter({ hasText: "no es correcto" })).toBeVisible();
    await expect(page).toHaveURL(/\/login/);
    await page.getByLabel("Código").fill(code);
    await page.getByRole("button", { name: "Entrar", exact: true }).click();
    await expect(page).toHaveURL(/\/app\/settings$/);
  });

  await test.step("el email nuevo es una cuenta y elige contraseña", async () => {
    await choosePassword(page, "/app/settings");
    const [{ method }] = await query(`select e.props->>'method' as method from public.events e join auth.users u on u.id = e.user_id where u.email = $1 and e.name = 'signup_completed'`, [email]);
    expect(method).toBe("email_code");
  });

  await test.step("el menú de la cuenta: email, Mis datos, el celular y cerrar sesión", async () => {
    await page.getByRole("button", { name: "Tu cuenta" }).click();
    await expect(page.getByRole("menu")).toContainText(email);
    await page.getByRole("menuitem", { name: "Mis datos" }).click();
    await expect(page).toHaveURL(/\/app\/datos$/);
    await page.getByLabel("Celular").fill("12");
    await page.getByRole("button", { name: "Guardar" }).click();
    await expect(page.getByRole("alert").filter({ hasText: "no parece válido" })).toBeVisible();
    await page.getByLabel("Celular").fill("011 15 2345-6789");
    await page.getByRole("button", { name: "Guardar" }).click();
    await expect(page.getByRole("status").filter({ hasText: "guardamos tu celular" })).toBeVisible();
    const [{ phone }] = await query("select phone from public.profiles where email = $1", [email]);
    expect(phone).toBe("+5491123456789");
    await signOutFromMenu(page);
  });

  await test.step("con contraseña, y con código sin que pida otra", async () => {
    await withPassword(page, email, E2E_PASSWORD);
    await expect(page).toHaveURL(/\/app$/);
    await page.context().clearCookies();
    await enterWithCode(page, email, "/app/saved");
    await expect(page).toHaveURL(/\/app\/saved$/);
  });

  await test.step("cambiar la contraseña desde Mis datos", async () => {
    await page.goto("/app/datos");
    await page.getByRole("link", { name: "Cambiar contraseña" }).click();
    await expect(page).toHaveURL(/\/auth\/reset-password\?next=%2Fapp%2Fdatos$/);
    await page.getByLabel("Nueva contraseña", { exact: true }).fill(replacement);
    await page.getByLabel("Repetí la contraseña").fill(replacement);
    await page.getByRole("button", { name: "Guardar contraseña" }).click();
    await expect(page).toHaveURL(/\/login\?password=updated&next=%2Fapp%2Fdatos$/);
    await withPassword(page, email, E2E_PASSWORD);
    await expect(page.getByRole("alert").filter({ hasText: "No pudimos ingresar" })).toBeVisible();
    await withPassword(page, email, replacement);
    await expect(page).toHaveURL(/\/app$/);
  });
});
