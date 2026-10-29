import { expect, type Page, test } from "@playwright/test";

import { query, seedPriceTracks } from "./support/db";
import { E2E_EMAIL_DOMAIN } from "./support/env";
import { magicLink } from "./support/mail";

/**
 * PAR-03 (docs/superpowers/specs/2026-10-29-par03-dias-y-bajas-design.md):
 * the drop line on result cards, the listing page's summary, its notes and the
 * closed price history that logs price_history_expanded, on desktop and on a
 * 375 px phone.
 */

test.describe.configure({ mode: "serial" });

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

/** Nothing sticks out sideways: the page never scrolls horizontally. */
async function expectNoHorizontalScroll(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow, `horizontal overflow on ${page.url()}`).toBeLessThanOrEqual(0);
}

async function expandedEvents(email: string) {
  return query<{ props: Record<string, unknown> }>(
    `select e.props from public.events e join public.profiles p on p.id = e.user_id
      where p.email = $1 and e.name = 'price_history_expanded'`,
    [email],
  );
}

test("bajas de precio: tarjeta, ficha y price_history_expanded", async ({ page }, testInfo) => {
  const run = `${testInfo.project.name}-${Date.now()}`;
  const email = `tracks-${run}@${E2E_EMAIL_DOMAIN}`;
  await signIn(page, email);
  const seeded = await seedPriceTracks(email, run);
  const card = (id: number) => page.getByTestId("listing-card").filter({ has: page.locator(`a[href="/app/listings/${id}"]`) });

  await test.step("la tarjeta dice las bajas solo con baja neta", async () => {
    await page.goto(`/app/searches/${seeded.profileId}?f=all`);
    await expect(card(seeded.drops)).toBeVisible();
    await expect(card(seeded.drops).getByTestId("card-price-track")).toHaveText(
      "Bajó 2 veces desde que la vimos: -USD 1.000 (-9,1%).",
    );
    await expect(card(seeded.detected).getByTestId("card-price-track")).toHaveText(
      "Bajó 1 vez desde que la vimos: -USD 500 (-4,8%).",
    );
    await expect(card(seeded.rise)).toBeVisible();
    await expect(card(seeded.rise).getByTestId("card-price-track")).toHaveCount(0);
    await expect(card(seeded.flat).getByTestId("card-price-track")).toHaveCount(0);
    const line = await card(seeded.drops).getByTestId("card-price-track").boundingBox();
    const viewport = page.viewportSize();
    expect(line && viewport && line.x + line.width <= viewport.width).toBeTruthy();
    await expectNoHorizontalScroll(page);
  });

  await test.step("la ficha resume las bajas y el histórico queda cerrado", async () => {
    await page.goto(`/app/listings/${seeded.drops}`);
    await expect(page.getByRole("heading", { name: "Histórico de precios" })).toBeVisible();
    await expect(page.getByTestId("price-track-summary")).toContainText("2 bajas · -USD 1.000 (-9,1%) desde el ");
    await expect(page.getByTestId("price-track-note")).toContainText("Seguimos este aviso desde el ");
    await expect(page.getByTestId("price-track-note")).toContainText("no vemos los cambios anteriores.");
    // The summary replaces the old "Bajó … desde que la vimos por primera vez."
    await expect(page.getByText("desde que la vimos por primera vez")).toHaveCount(0);
    const details = page.getByTestId("price-history-details");
    await expect(details).not.toHaveAttribute("open", "");
    await expect(page.getByRole("list", { name: "Histórico de precios" })).toBeHidden();
    await expectNoHorizontalScroll(page);
  });

  await test.step("abrirlo registra price_history_expanded una sola vez", async () => {
    const toggle = page.getByTestId("price-history-details").locator("summary");
    await toggle.click();
    await expect(page.getByRole("list", { name: "Histórico de precios" })).toBeVisible();
    await expect(page.getByRole("list", { name: "Histórico de precios" }).getByRole("listitem")).toHaveCount(3);
    await expect.poll(async () => (await expandedEvents(email)).length).toBe(1);
    const [event] = await expandedEvents(email);
    expect(event.props).toEqual({ listing_id: seeded.drops, drops: 2, days: 12 });
    await toggle.click();
    await toggle.click();
    await expect(page.getByRole("list", { name: "Histórico de precios" })).toBeVisible();
    await page.waitForTimeout(1_500);
    expect((await expandedEvents(email)).length).toBe(1);
    await expectNoHorizontalScroll(page);
  });

  await test.step("sin fecha de publicación, la ficha avisa que contamos desde que la detectamos", async () => {
    await page.goto(`/app/listings/${seeded.detected}`);
    await expect(page.getByTestId("price-track-summary")).toContainText("1 baja · -USD 500 (-4,8%) desde el ");
    await expect(page.getByTestId("price-track-note")).toHaveText(
      "No sabemos cuándo se publicó; contamos desde que la detectamos.",
    );
  });

  await test.step("una suba conserva «Subió» y un solo precio no muestra la sección", async () => {
    await page.goto(`/app/listings/${seeded.rise}`);
    await expect(page.getByText("desde que la vimos por primera vez")).toBeVisible();
    await expect(page.getByText(/^Subió USD 500/)).toBeVisible();
    await expect(page.getByTestId("price-track-summary")).toHaveCount(0);
    await page.goto(`/app/listings/${seeded.flat}`);
    await expect(page.locator("h1")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Histórico de precios" })).toHaveCount(0);
    await expect(page.getByTestId("detected-note")).toHaveCount(0);
  });
});
