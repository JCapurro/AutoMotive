import { expect, type Page, test } from "@playwright/test";

import { seedSellerListings } from "./support/db";
import { E2E_EMAIL_DOMAIN } from "./support/env";
import { magicLink } from "./support/mail";

/**
 * F-02 paso 2 (docs/superpowers/specs/2026-10-30-f02-vendedor-design.md): a
 * listing the worker marked «posible agencia» (dealer_inferred, seeded with
 * seller_listing_count = 7; the test does not expect N to change) says so in
 * «Vendedor», adds that the listing itself says «particular», and gets the
 * dealer fees notice; a plain private seller gets neither. Desktop and phone.
 */

async function signIn(page: Page, email: string) {
  const since = new Date();
  await page.goto("/login?mode=signup&next=/app");
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Contraseña", { exact: true }).fill("e2e-password-123");
  await page.getByLabel("Repetí la contraseña").fill("e2e-password-123");
  await page.getByRole("button", { name: "Crear cuenta", exact: true }).click();
  await expect(page.getByText("Revisá tu email")).toBeVisible();
  await page.goto(await magicLink(email, since));
  await page.getByRole("button", { name: "Confirmar mi email" }).click();
  await expect(page).toHaveURL(/\/app/);
}

async function expectNoHorizontalScroll(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow, `horizontal overflow on ${page.url()}`).toBeLessThanOrEqual(0);
}

test("la ficha marca «posible agencia» con el motivo y el aviso de gastos", async ({ page }, testInfo) => {
  const run = `${testInfo.project.name}-${Date.now()}`;
  const email = `seller-${run}@${E2E_EMAIL_DOMAIN}`;
  await signIn(page, email);
  const ids = await seedSellerListings(email, run);

  await page.goto(`/app/listings/${ids.inferred}`);
  await expect(
    page.getByText("Posible agencia (publica 7 autos); la publicación dice particular, Autos del Parque", { exact: true }),
  ).toBeVisible();
  await expect(page.getByTestId("dealer-fees-notice")).toBeVisible();
  await expectNoHorizontalScroll(page);

  await page.goto(`/app/listings/${ids.private}`);
  await expect(page.getByText("Particular, Juan Pérez", { exact: true })).toBeVisible();
  await expect(page.getByText(/Posible agencia/)).toHaveCount(0);
  await expect(page.getByTestId("dealer-fees-notice")).toHaveCount(0);
});

test("el formulario avisa que «Concesionaria» incluye las posibles agencias", async ({ page }, testInfo) => {
  const email = `seller-form-${testInfo.project.name}-${Date.now()}@${E2E_EMAIL_DOMAIN}`;
  await signIn(page, email);
  await page.goto("/app/searches/new");
  await page.getByRole("tab", { name: "Estructurado" }).click();
  const panel = page.getByRole("tabpanel", { name: "Estructurado" });
  const seller = panel.getByLabel(/^Vendedor/);
  await expect(panel.getByTestId("seller-type-hint")).toHaveCount(0);
  await seller.selectOption("dealer");
  await expect(panel.getByTestId("seller-type-hint")).toHaveText("Incluye posibles agencias.");
  await seller.selectOption("private");
  await expect(panel.getByTestId("seller-type-hint")).toHaveCount(0);
  await expectNoHorizontalScroll(page);
});
