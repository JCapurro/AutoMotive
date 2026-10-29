import { expect, type Page, test } from "@playwright/test";

import { EXPECTED_BACKFILL, finishFirstCollection, insertFreshDeal, query } from "./support/db";
import { E2E_EMAIL_DOMAIN, E2E_LISTING_PREFIX } from "./support/env";
import { worker } from "./support/worker";

/**
 * F4 acceptance (docs/TECHNICAL_PLAN.md, sección 13):
 *   email en la landing (sin contraseña ni confirmación) → creación de
 *   búsqueda → ver el backfill → llega una alerta simulada → clic en la
 *   alerta → "Guardar" → comprado,
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

// AMBA as a user sets it: Ciudad de Buenos Aires (lib/argentina-locations.ts) with a 60 km radius.
const AMBA = { label: "Ciudad de Buenos Aires, CABA", lat: -34.6037, lon: -58.3816, radius_km: 60 };

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

test("F4: búsqueda gratis con el email, backfill, alerta, guardar y guardados", async ({ page }, testInfo) => {
  const run = `${testInfo.project.name}-${Date.now()}`;
  const email = `${run}@${E2E_EMAIL_DOMAIN}`;

  await test.step("landing (§50)", async () => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Decinos cuál. Te avisamos cuando aparezca." })).toBeVisible();
    await expect(page.getByText("pide USD 2.574 menos")).toBeVisible();
    await expectNoHorizontalScroll(page);
  });

  await test.step("1. búsqueda gratis solo con el email: sin contraseña ni confirmación", async () => {
    const form = page.locator("#landing-search");
    await form.getByLabel("¿Qué auto buscás?").fill("Ford Fiesta Titanium manual 2016 a 2018 hasta USD 11.500");
    await form.getByRole("button", { name: "Crear mi búsqueda" }).click();
    // The email comes in a pop-up, never the login page.
    const dialog = page.getByRole("dialog", { name: "¿A qué email te avisamos?" });
    await dialog.getByLabel("Tu email").fill(email);
    await dialog.getByRole("button", { name: "Seguir" }).click();
    await expect(page).toHaveURL(/\/app\/searches\/new/);
    await expect(page.getByText(`Te vamos a avisar a ${email}`)).toBeVisible();
    const [account] = await query<{ email_only: boolean; method: string }>(
      `select p.email_only, e.props->>'method' as method from public.events e join public.profiles p on p.id = e.user_id
        where p.email = $1 and e.name = 'signup_completed'`,
      [email],
    );
    expect(account).toEqual({ email_only: true, method: "email_only" });
  });

  let profileId = 0;
  await test.step("2. creación de la búsqueda estructurada con preview", async () => {
    await page.getByRole("tab", { name: "Estructurado" }).click();
    // The landing prompt also opened the assisted tab (its fallback form stays mounted, hidden).
    const panel = page.getByRole("tabpanel", { name: "Estructurado" });
    await expectNoHorizontalScroll(page);
    await panel.getByLabel("Marca").selectOption("Ford");
    await panel.getByLabel("Modelo").selectOption("Fiesta");
    await panel.getByLabel(/^Versiones/).selectOption("Titanium");
    await panel.getByLabel("Año desde").selectOption("2016");
    await panel.getByLabel("Año hasta").selectOption("2018");
    await panel.getByLabel("Precio máximo").fill("11500");
    await panel.getByLabel("Kilometraje máximo").fill("150000");
    await panel.getByText("Manual", { exact: true }).click();
    // A new search starts at "Mi ubicación actual", unknown here (no permission, no Vercel headers).
    await panel.getByText("Ubicación manual", { exact: true }).click();
    await panel.getByLabel("Provincia").selectOption({ label: "Ciudad Autónoma de Buenos Aires" });
    await panel.getByLabel("Localidad").selectOption({ label: "Ciudad de Buenos Aires" });
    await panel.getByLabel("Radio (km)").fill(String(AMBA.radius_km));
    // The form no longer counts listings: nothing to wait for before saving.
    await expect(panel.getByTestId("preview-count")).toHaveCount(0);
    await expect(panel.getByLabel("Nombre de la búsqueda")).toHaveValue("Ford Fiesta Titanium");
    await panel.getByRole("button", { name: "Crear búsqueda" }).click();
    await expect(page).toHaveURL(/\/app\/searches\/\d+$/);
    profileId = Number(page.url().split("/").pop());
    await expect(page.getByRole("status")).toContainText("Tu búsqueda ya está vigilando");

    const [profile] = await query<{
      filters: Record<string, unknown>;
      origin_lat: number;
      origin_lon: number;
      radius_km: number;
      channels: string[];
    }>(`select filters, origin_lat, origin_lon, radius_km, channels from public.search_profiles where id = $1`, [profileId]);
    expect(profile.filters).toEqual({ ...SEARCH_FILTERS, location_label: AMBA.label });
    expect([profile.origin_lat, profile.origin_lon, profile.radius_km]).toEqual([AMBA.lat, AMBA.lon, AMBA.radius_km]);
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
    // The page keeps "preparando" until every source finished a first pass for this search.
    await finishFirstCollection(profileId, SEARCH_FILTERS.make, SEARCH_FILTERS.model);
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
    // Disabled already while the action is pending: wait for it to be saved before leaving.
    await expect(page.getByText("Publicación descartada")).toBeVisible();
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

  await test.step("5. Guardar guarda el aviso", async () => {
    // X-01 brought the follow-up select back (tracking.spec.ts covers it); the raw score stays hidden.
    await expect(page.getByLabel("Estado", { exact: true })).toHaveCount(1);
    await expect(page.getByText("Ver el puntaje en números")).toHaveCount(0);
    await page.getByRole("button", { name: "Guardar", exact: true }).click();
    await expect(page.getByRole("button", { name: "Guardada", exact: true })).toHaveAttribute("aria-pressed", "true");
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
