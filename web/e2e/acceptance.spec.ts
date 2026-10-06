import { expect, type Page, test } from "@playwright/test";

import { EXPECTED_BACKFILL, insertFreshDeal, query } from "./support/db";
import { E2E_EMAIL_DOMAIN, E2E_LISTING_PREFIX } from "./support/env";
import { magicLink } from "./support/mail";
import { worker } from "./support/worker";

/**
 * F4 acceptance (docs/TECHNICAL_PLAN.md, sección 13):
 *   registro → creación de búsqueda → ver el backfill → llega una alerta
 *   simulada → clic en la alerta → "Me interesa" → comprado,
 * on desktop and on a 375 px phone (the `mobile` project).
 */

test.describe.configure({ mode: "serial" });

// The search the test creates through the form, as search_profiles.filters stores it.
const SEARCH_FILTERS = {
  make: "Ford",
  model: "Fiesta",
  trims: ["Titanium"],
  trim_strict: false,
  year_min: 2016,
  year_max: 2018,
  price_max: 11500,
  currency: "USD",
  km_max: 150000,
  transmission: "manual",
};

const mobile = (page: Page) => (page.viewportSize()?.width ?? 1280) < 768;

/** Nothing sticks out sideways: the page never scrolls horizontally. */
async function expectNoHorizontalScroll(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow, `horizontal overflow on ${page.url()}`).toBeLessThanOrEqual(0);
}

/** Main navigation: the bottom tab bar on a phone, the header on desktop. */
async function navigate(page: Page, name: "Inicio" | "Guardados" | "Ajustes") {
  const nav = page.getByRole("navigation", { name: "Principal" }).filter({ visible: true });
  await nav.getByRole("link", { name, exact: false }).first().click();
}

test("F4: registro, búsqueda, backfill, alerta, Me interesa y guardados", async ({ page }, testInfo) => {
  const run = `${testInfo.project.name}-${Date.now()}`;
  const email = `${run}@${E2E_EMAIL_DOMAIN}`;

  await test.step("landing (§50)", async () => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Decinos cuál. Te avisamos cuando aparezca." })).toBeVisible();
    await expect(page.getByText("pide USD 2.574 menos")).toBeVisible();
    await expectNoHorizontalScroll(page);
    await page.getByRole("link", { name: "Crear mi búsqueda" }).first().click();
    await expect(page).toHaveURL(/\/login\?next=\/app\/searches\/new$/);
  });

  await test.step("1. registro con contraseña y confirmación", async () => {
    const since = new Date();
    await page.getByLabel("Email").fill(email);
    await page.getByRole("link", { name: "Crear cuenta", exact: true }).click();
    await page.getByLabel("Email", { exact: true }).fill(email);
    await page.getByLabel("Contraseña", { exact: true }).fill("e2e-password-123");
    await page.getByLabel("Repetí la contraseña").fill("e2e-password-123");
    await page.getByRole("button", { name: "Crear cuenta", exact: true }).click();
    await expect(page.getByText("Revisá tu email")).toBeVisible();
    await page.goto(await magicLink(email, since));
    await page.getByRole("button", { name: "Confirmar mi email" }).click();
    await expect(page).toHaveURL(/\/app\/searches\/new$/);
    const [signup] = await query(
      `select e.name from public.events e join public.profiles p on p.id = e.user_id
        where p.email = $1 and e.name = 'signup_completed'`,
      [email],
    );
    expect(signup).toBeTruthy();
  });

  let profileId = 0;
  await test.step("2. creación de la búsqueda estructurada con preview", async () => {
    await page.getByRole("tab", { name: "Estructurado" }).click();
    await expectNoHorizontalScroll(page);
    await page.getByLabel("Marca").selectOption("Ford");
    await page.getByLabel("Modelo").selectOption("Fiesta");
    await page.getByLabel(/^Versión/).selectOption("Titanium");
    await page.getByLabel("Año desde").selectOption("2016");
    await page.getByLabel("Año hasta").selectOption("2018");
    await page.getByLabel("Precio máximo").fill("11500");
    await page.getByLabel("Kilometraje máximo").fill("150000");
    await page.getByText("Manual", { exact: true }).click();
    await page.getByLabel("Zona").selectOption("amba");
    // What preview_search counts over the whole local database (the seeded market, at least).
    const [{ count }] = await query<{ count: number }>(
      `select (public.preview_search($1::jsonb, -34.6037, -58.3816, 60)->>'count')::int as count`,
      [JSON.stringify(SEARCH_FILTERS)],
    );
    expect(count).toBeGreaterThanOrEqual(EXPECTED_BACKFILL.length);
    await expect(page.getByTestId("preview-count")).toContainText(`${count} publicaciones actuales coinciden`);
    await expect(page.getByLabel("Nombre de la búsqueda")).toHaveValue("Ford Fiesta Titanium");
    await page.getByRole("button", { name: "Crear búsqueda" }).click();
    await expect(page).toHaveURL(/\/app\/searches\/\d+$/);
    profileId = Number(page.url().split("/").pop());
    await expect(page.getByRole("status")).toContainText("Estamos buscando coincidencias");

    const [profile] = await query<{ filters: Record<string, unknown>; radius_km: number; channels: string[] }>(
      `select filters, radius_km, channels from public.search_profiles where id = $1`,
      [profileId],
    );
    expect(profile.filters).toEqual({ ...SEARCH_FILTERS, location_label: "AMBA" });
    expect(profile.radius_km).toBe(60);
    expect(profile.channels).toEqual(["email"]);
  });

  await test.step("3. el worker hace el backfill y se ve en los resultados", async () => {
    worker("rematch");
    const matched = await query<{ external_id: string; is_backfill: boolean }>(
      `select l.external_id, m.is_backfill from public.matches m join public.listings l on l.id = m.listing_id
        where m.search_profile_id = $1`,
      [profileId],
    );
    expect(matched.map((m) => m.external_id)).toEqual(
      expect.arrayContaining(EXPECTED_BACKFILL.map((key) => `${E2E_LISTING_PREFIX}${key}`)),
    );
    expect(matched.every((m) => m.is_backfill)).toBe(true);
    await expect(page.getByTestId("listing-card")).toHaveCount(matched.length, { timeout: 20_000 });
    await expect(page.getByRole("status")).toHaveCount(0);
    await expectNoHorizontalScroll(page);

    await expect(page.getByLabel("Ordenar")).toHaveValue("score");
    // Filters and sort (§29).
    await page.getByRole("link", { name: /^Oportunidades/ }).click();
    await expect(page).toHaveURL(/f=opportunities/);
    await page.getByRole("link", { name: /^Todos/ }).click();
    await expect(page).toHaveURL(/f=all/);
    await expect(page.getByRole("link", { name: /^Todos/ })).toHaveAttribute("aria-current", "page");
    await page.getByLabel("Ordenar").selectOption("price");
    await expect(page).toHaveURL(/f=all&s=price/);
    await expect(page.getByLabel("Ordenar")).toHaveValue("price");
    const prices = (await page.getByTestId("listing-card").getByText(/^USD /).allInnerTexts()).map((t) =>
      Number(t.replace(/\D/g, "")),
    );
    expect(prices).toEqual([...prices].sort((a, b) => a - b));

    // The full detail (§23) of a backfilled listing, with its price history (§31).
    await page.getByTestId("listing-card").filter({ hasText: "Vicente López" }).getByRole("link").click();
    await expect(page).toHaveURL(/\/app\/listings\/\d+/);
    await expect(page.getByRole("heading", { name: "¿Por qué apareció?" })).toBeVisible();
    await expect(page.getByTestId("match-reasons")).toContainText("Dentro del presupuesto");
    await expect(page.getByTestId("match-reasons")).toContainText("Caja manual");
    await expect(page.getByTestId("price-analysis")).toContainText("debajo del mercado observado");
    await expect(page.getByRole("heading", { name: "Histórico de precios" })).toBeVisible();
    await expect(page.getByRole("list", { name: "Histórico de precios" })).toContainText("USD 11.800");
    await expect(page.getByTestId("red-flags")).toContainText("conviene verificar");
    await page.getByRole("button", { name: "¿Qué le pregunto al vendedor?" }).click();
    await expect(page.getByTestId("seller-questions")).toContainText("¿Lo seguís teniendo?");
    await expectNoHorizontalScroll(page);

    // Discarding asks for the §27 reason, and the listing moves to "Descartados".
    await page.getByRole("button", { name: "Descartar" }).click();
    await page.getByRole("radio", { name: "Demasiado caro" }).check();
    await page.getByRole("button", { name: "Descartar", exact: true }).last().click();
    await expect(page.getByRole("button", { name: "Descartar", exact: true })).toBeDisabled();
    await page.goto(`/app/searches/${profileId}?f=discarded`);
    await expect(page.getByTestId("listing-card")).toHaveCount(1);
  });

  let dealId = 0;
  await test.step("4. alerta de email simulada sin notificaciones web", async () => {
    dealId = await insertFreshDeal(run);
    const sent = JSON.parse(worker("simulate_alert", String(dealId), "--json")) as { id: number; kind: string; channel: string; status: string }[];
    const alert = sent.find((n) => n.kind === "opportunity" && n.channel === "email");
    expect(alert?.status).toBe("sent");
    expect(sent.some((n) => n.channel === "web" || n.channel === "telegram")).toBe(false);
    await expect(page.getByTestId("inbox-badge")).toHaveCount(0);
    await page.goto(`/r/${alert!.id}?to=detail`);
    await expect(page).toHaveURL(new RegExp(`/app/listings/${dealId}\\?n=\\d+`));
  });

  await test.step("5. Me interesa guarda el aviso", async () => {
    await expect(page.getByLabel("Estado", { exact: true })).toHaveCount(0);
    await expect(page.getByText("Ver el puntaje en números")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Guardar", exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Compré este vehículo" })).toHaveCount(0);
    await page.getByRole("button", { name: "Me interesa", exact: true }).click();
    await expect(page.getByRole("button", { name: "Me interesa", exact: true })).toHaveAttribute("aria-pressed", "true");
    const [interaction] = await query<{ status: string; saved: boolean }>(
      `select i.status, i.saved from public.user_listing_interactions i join public.profiles p on p.id=i.user_id where p.email=$1 and i.listing_id=$2`, [email, dealId]);
    expect(interaction).toEqual({ status: "interested", saved: true });
    await expectNoHorizontalScroll(page);
  });

  await test.step("watchlist y ajustes", async () => {
    await navigate(page, "Guardados");
    await expect(page).toHaveURL(/\/app\/saved$/);
    await expect(page.getByTestId("listing-card")).toHaveCount(1);
    await expectNoHorizontalScroll(page);

    await navigate(page, "Ajustes");
    await expect(page).toHaveURL(/\/app\/settings$/);
    await expect(page.getByRole("link", { name: /Vincular Telegram/ })).toHaveCount(0);
    await expect(page.getByText("Email", { exact: true })).toBeVisible();
    await expectNoHorizontalScroll(page);
  });

  if (mobile(page)) {
    await test.step("mobile: navegación inferior a 375 px", async () => {
      expect(page.viewportSize()?.width).toBe(375);
      const tabs = page.getByRole("navigation", { name: "Principal" }).filter({ visible: true });
      await expect(tabs.getByRole("link")).toHaveCount(3);
      for (const name of ["Inicio", "Guardados", "Ajustes"] as const) {
        await navigate(page, name);
        await expect(tabs.getByRole("link", { name }).first()).toHaveAttribute("aria-current", "page");
        await expectNoHorizontalScroll(page);
      }
    });
  }
});
