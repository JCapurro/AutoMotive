import { expect, type Page, test } from "@playwright/test";

import { query, seedTotalCost } from "./support/db";
import { E2E_EMAIL_DOMAIN } from "./support/env";
import { magicLink } from "./support/mail";

/**
 * PAR-01 (docs/superpowers/specs/2026-10-30-par01-costo-total-design.md): the
 * total cost estimate. With the plan's total_cost flag (Particular; the free
 * plan during the pilot) the listing page shows the header and a closed
 * breakdown that logs total_cost_expanded, and the results card shows the
 * same header; Pro sees neither, and nobody sees the old fixed «8–10 %»
 * notice. An ARS listing of 20.000.000 at the dollar 1.300 of its price_usd,
 * a 2017 sedan of a private seller, from a search in «Palermo, CABA»:
 * golden case 1. Desktop and phone (375 px), without horizontal scroll.
 */

const LINE = "Costo total estimado: USD 16.290 – 16.560 (ARS 21.188.000 – 21.518.000)";

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

async function expandedEvents(email: string, listingId: number) {
  return query<{ props: { listing_id: number; jurisdiction: string[] | null; missing: number } }>(
    `select e.props from public.events e join public.profiles p on p.id = e.user_id
      where p.email = $1 and e.name = 'total_cost_expanded' and (e.props->>'listing_id')::bigint = $2`,
    [email, listingId],
  );
}

test("Particular: ficha con detalle, tarjeta y total_cost_expanded", async ({ page }, testInfo) => {
  const run = `${testInfo.project.name}-${Date.now()}`;
  const email = `total-cost-${run}@${E2E_EMAIL_DOMAIN}`;
  await signIn(page, email);
  const ids = await seedTotalCost(email, run, "pass");

  await test.step("la ficha muestra el costo total estimado", async () => {
    await page.goto(`/app/listings/${ids.private}`);
    const block = page.getByTestId("cost-estimate");
    await expect(block.getByTestId("cost-estimate-headline")).toHaveText(LINE);
    await expect(page.getByTestId("cost-estimate-details")).not.toHaveAttribute("open", "");
    await expect(page.getByText(/8\s*[–-]\s*10\s*%/)).toHaveCount(0);
    await expect(page.getByTestId("dealer-fees-notice")).toHaveCount(0);
    await expectNoHorizontalScroll(page);
  });

  await test.step("«Ver detalle» abre el desglose y registra total_cost_expanded una vez", async () => {
    await page.getByText("Ver detalle", { exact: true }).click();
    const details = page.getByTestId("cost-estimate-details");
    await expect(details.getByText("Sellos de CABA", { exact: true })).toBeVisible();
    await expect(details.getByText("Patente anual (valores 2026)", { exact: true })).toBeVisible();
    await expect(details.getByText("ARS 380.900 – 698.700", { exact: true })).toBeVisible();
    await expect(details.getByText("Patente y sellos de CABA, según tu búsqueda en «Palermo, CABA».", { exact: true })).toBeVisible();
    await expect(details.getByText("Fuera del total: informe de dominio ARS 4.000 – 4.400, recomendado antes de señar.", { exact: true })).toBeVisible();
    await expect(details.getByText("Parámetros al 30/10.", { exact: true })).toBeVisible();
    await expectNoHorizontalScroll(page);
    await expect.poll(async () => (await expandedEvents(email, ids.private)).length).toBe(1);
    // Closing and opening again does not log it twice.
    await page.getByText("Ver detalle", { exact: true }).click();
    await page.getByText("Ver detalle", { exact: true }).click();
    await page.waitForTimeout(500);
    const events = await expandedEvents(email, ids.private);
    expect(events.map((e) => e.props)).toEqual([{ listing_id: ids.private, jurisdiction: ["caba"], missing: 0 }]);
  });

  await test.step("la tarjeta de resultados muestra la misma línea", async () => {
    await page.goto(`/app/searches/${ids.profileId}`);
    const card = page.getByTestId("listing-card").filter({ has: page.getByRole("link", { name: /Corolla/ }) }).first();
    await expect(page.getByTestId("cost-estimate-line").first()).toHaveText(LINE);
    await expect(card).toBeVisible();
    // The km line stays under the price, in the text column, not under the photo.
    const price = await card.locator("p.type-figure").boundingBox();
    const cost = await card.getByTestId("cost-estimate-line").boundingBox();
    const meta = await card.getByTestId("card-meta").boundingBox();
    expect(price && cost && meta).toBeTruthy();
    expect(Math.abs(meta!.x - price!.x)).toBeLessThan(1);
    expect(Math.abs(cost!.x - price!.x)).toBeLessThan(1);
    expect(meta!.y).toBeGreaterThan(cost!.y);
    await expectNoHorizontalScroll(page);
  });

  await test.step("un aviso de agencia ya no muestra el aviso fijo de gastos", async () => {
    await page.goto(`/app/listings/${ids.dealer}`);
    await expect(page.getByTestId("dealer-fees-notice")).toHaveCount(0);
    await expect(page.getByTestId("cost-estimate-headline")).toHaveText(/^Costo total estimado: USD /);
    await page.getByText("Ver detalle", { exact: true }).click();
    await expect(page.getByText("Vendedor: concesionaria.", { exact: true })).toBeVisible();
  });
});

test("Pro no ve el costo total; Free sí durante el piloto", async ({ page }, testInfo) => {
  const run = `${testInfo.project.name}-${Date.now()}`;
  const pro = `total-cost-pro-${run}@${E2E_EMAIL_DOMAIN}`;
  await signIn(page, pro);
  const proIds = await seedTotalCost(pro, `${run}-pro`, "pro");
  await page.goto(`/app/listings/${proIds.private}`);
  await expect(page.getByTestId("price")).toBeVisible();
  await expect(page.getByTestId("cost-estimate")).toHaveCount(0);
  await expect(page.getByText(/8\s*[–-]\s*10\s*%/)).toHaveCount(0);
  await page.goto(`/app/searches/${proIds.profileId}`);
  await expect(page.getByTestId("listing-card").first()).toBeVisible();
  await expect(page.getByTestId("cost-estimate-line")).toHaveCount(0);

  await page.context().clearCookies();
  const free = `total-cost-free-${run}@${E2E_EMAIL_DOMAIN}`;
  await signIn(page, free);
  const freeIds = await seedTotalCost(free, `${run}-free`, "free");
  await page.goto(`/app/listings/${freeIds.private}`);
  await expect(page.getByTestId("cost-estimate-headline")).toHaveText(LINE);
  await expectNoHorizontalScroll(page);
});
