import { expect, type Page, test } from "@playwright/test";

import { finishFirstCollection, query, seedTracking } from "./support/db";
import { E2E_EMAIL_DOMAIN } from "./support/env";
import { signUp } from "./support/auth";

/**
 * X-01 (docs/superpowers/specs/2026-10-29-x01-seguimiento-design.md): the
 * follow-up status, on the listing page and in Guardados, on desktop and on
 * a 375 px phone. No private note since Juan's 02/11 request: the block has
 * no textarea and nothing writes user_listing_interactions.note.
 */

test.describe.configure({ mode: "serial" });

async function signIn(page: Page, email: string) {
  await signUp(page, email, "/app");
}

/** Nothing sticks out sideways: the page never scrolls horizontally. */
async function expectNoHorizontalScroll(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow, `horizontal overflow on ${page.url()}`).toBeLessThanOrEqual(0);
}

async function interaction(email: string, listingId: number) {
  const [row] = await query<{ status: string; saved: boolean; note: string | null }>(
    `select i.status, i.saved, i.note from public.user_listing_interactions i join public.profiles p on p.id = i.user_id
      where p.email = $1 and i.listing_id = $2`,
    [email, listingId],
  );
  return row;
}

test("seguimiento: estado, sin nota, Guardados con filtro y compra", async ({ page }, testInfo) => {
  const run = `${testInfo.project.name}-${Date.now()}`;
  const email = `tracking-${run}@${E2E_EMAIL_DOMAIN}`;
  await signIn(page, email);
  const seeded = await seedTracking(email, run);
  const tracking = page.getByTestId("listing-tracking");

  await test.step("Contactado desde la ficha, sin tocar saved", async () => {
    await page.goto(`/app/listings/${seeded.active}`);
    await expect(tracking.getByRole("heading", { name: "Seguimiento" })).toBeVisible();
    await tracking.getByLabel("Estado", { exact: true }).selectOption("contacted");
    await expect(page.getByText("Estado: Contactado")).toBeVisible();
    await expect.poll(() => interaction(email, seeded.active)).toMatchObject({ status: "contacted", saved: false });
  });

  await test.step("Guardar después de Contactado no baja el estado", async () => {
    await page.getByRole("button", { name: "Guardar", exact: true }).click();
    await expect(page.getByRole("button", { name: "Guardada", exact: true })).toHaveAttribute("aria-pressed", "true");
    await expect.poll(() => interaction(email, seeded.active)).toMatchObject({ status: "contacted", saved: true });
    await expect(tracking.getByLabel("Estado", { exact: true })).toHaveValue("contacted");
  });

  await test.step("sin nota privada (Juan 02/11)", async () => {
    await expect(tracking.locator("textarea")).toHaveCount(0);
    await expect(tracking).not.toContainText("nota");
    await expect(tracking.getByRole("button", { name: "Guardar nota" })).toHaveCount(0);
    expect((await interaction(email, seeded.active)).note).toBeNull();
    await expectNoHorizontalScroll(page);
  });

  await test.step("Guardados: tarjeta sin nota y filtro por estado", async () => {
    await page.goto("/app/saved");
    const card = page.getByTestId("listing-card").filter({ hasText: "Vicente López" });
    await expect(card).toBeVisible();
    await expect(card.getByTestId("card-note")).toHaveCount(0);
    await page.getByRole("link", { name: "Contactados", exact: true }).click();
    await expect(page).toHaveURL(/\/app\/saved\?e=contacted$/);
    await expect(page.getByTestId("listing-card")).toHaveCount(1);
    await page.getByRole("link", { name: "Comprados", exact: true }).click();
    await expect(page.getByText("No marcaste publicaciones como compradas.")).toBeVisible();
    await page.getByRole("link", { name: "Todos", exact: true }).click();
    await expectNoHorizontalScroll(page);
  });

  await test.step("cambiar el estado desde la tarjeta sin abrir la ficha", async () => {
    const card = page.getByTestId("listing-card").filter({ hasText: "Vicente López" });
    await card.getByLabel("Estado", { exact: true }).selectOption("visit_scheduled");
    await expect(page.getByText("Estado: Visita agendada")).toBeVisible();
    await expect(page).toHaveURL(/\/app\/saved$/);
    await expect.poll(async () => (await interaction(email, seeded.active)).status).toBe("visit_scheduled");
  });

  await test.step("Comprado desde el diálogo: owned_vehicles y select bloqueado", async () => {
    await page.goto(`/app/listings/${seeded.active}`);
    await tracking.getByLabel("Estado", { exact: true }).selectOption("purchased");
    const dialog = page.getByRole("dialog", { name: "¿La compraste?" });
    await dialog.getByLabel("Precio que pagaste").fill("9800");
    await dialog.getByRole("button", { name: "Marcar como comprada" }).click();
    await expect(page.getByText("Registramos la compra")).toBeVisible();
    await expect(tracking.getByLabel("Estado", { exact: true })).toBeDisabled();
    await expect(tracking).toContainText("la compra no se puede deshacer desde acá");
    const owned = await query<{ purchase_price: string; purchase_currency: string; search_profile_id: number }>(
      `select o.purchase_price, o.purchase_currency, o.search_profile_id from public.owned_vehicles o
        join public.profiles p on p.id = o.user_id where p.email = $1 and o.listing_id = $2`,
      [email, seeded.active],
    );
    expect(owned).toEqual([{ purchase_price: "9800", purchase_currency: "USD", search_profile_id: seeded.profileId }]);
    expect((await interaction(email, seeded.active)).status).toBe("purchased");
    await expectNoHorizontalScroll(page);
  });

  await test.step("una publicación que ya no está también tiene seguimiento", async () => {
    await page.goto(`/app/listings/${seeded.gone}`);
    await expect(page.getByText("Esta publicación ya no está disponible.")).toBeVisible();
    await tracking.getByLabel("Estado", { exact: true }).selectOption("contacted");
    await expect.poll(async () => (await interaction(email, seeded.gone))?.status).toBe("contacted");
    await page.goto("/app/saved?e=contacted");
    await expect(page.getByTestId("listing-card")).toHaveCount(1);
    await expect(page.getByTestId("listing-card")).toContainText("Ya no está disponible");
    await expectNoHorizontalScroll(page);
  });

  // Entrega (b): needs migration 20261119120000_x01_tracking.sql on the local database.
  await test.step("resultados: píldoras de seguimiento con conteo, la caída incluida", async () => {
    await finishFirstCollection(seeded.profileId, "Ford", "Fiesta");
    await page.goto(`/app/searches/${seeded.profileId}`);
    const pills = page.getByTestId("result-filters");
    await expect(pills.getByRole("link", { name: /^Contactados/ })).toContainText("1");
    await expect(pills.getByRole("link", { name: /^Visita agendada/ })).toContainText("0");
    await expect(pills.getByRole("link", { name: /^Comprados/ })).toContainText("1");
    await expectNoHorizontalScroll(page);

    await pills.getByRole("link", { name: /^Contactados/ }).click();
    await expect(page).toHaveURL(/f=contacted/);
    await expect(page.getByTestId("listing-card")).toHaveCount(1);
    await expect(page.getByTestId("listing-card")).toContainText("Ya no está disponible");

    await pills.getByRole("link", { name: /^Visita agendada/ }).click();
    await expect(page.getByText("No marcaste publicaciones con visita agendada.")).toBeVisible();

    await pills.getByRole("link", { name: /^Comprados/ }).click();
    await expect(page.getByTestId("listing-card")).toHaveCount(1);
    await expect(page.getByTestId("card-note")).toHaveCount(0);
    await expectNoHorizontalScroll(page);
  });
});
