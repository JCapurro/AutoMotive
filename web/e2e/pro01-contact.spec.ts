import { expect, type Page, test } from "@playwright/test";

import { query } from "./support/db";
import { E2E_EMAIL_DOMAIN } from "./support/env";
import { magicLink } from "./support/mail";

/**
 * PRO-01 (docs/superpowers/specs/2026-10-31-pro01-contacto-design.md).
 * Paso 1: Pro creates «solo particulares», sees the explanation, edits it and
 * the summary changes; an account without the feature with a stored strict
 * filter (a downgrade) sees «solo Pro», clears it and the summary says it is
 * a preference no more. Desktop and phone (375 px), without horizontal scroll.
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

async function setPlan(email: string, plan: "free" | "pass" | "pro") {
  await query(
    `update public.profiles
        set plan = $2::public.user_plan, plan_expires_at = case when $2 = 'free' then null else now() + interval '20 days' end
      where email = $1`,
    [email, plan],
  );
}

async function stored(id: number) {
  const [row] = await query<{ filters: Record<string, unknown>; preferences: Record<string, unknown> }>(
    `select filters, preferences from public.search_profiles where id = $1`, [id]);
  return row;
}

async function sellerEvents(email: string) {
  return query<{ props: { seller_types: string[]; mode: string } }>(
    `select e.props from public.events e join public.profiles p on p.id = e.user_id
      where p.email = $1 and e.name = 'seller_filter_set' order by e.id`, [email]);
}

test("Pro: solo particulares, con la explicación, y el resumen sigue la edición", async ({ page }, testInfo) => {
  const email = `pro01-pro-${testInfo.project.name}-${Date.now()}@${E2E_EMAIL_DOMAIN}`;
  await signIn(page, email);
  await setPlan(email, "pro");
  let id = 0;

  await test.step("crear la búsqueda con el filtro estricto", async () => {
    await page.goto("/app/searches/new");
    await page.getByRole("tab", { name: "Estructurado" }).click();
    const panel = page.getByRole("tabpanel", { name: "Estructurado" });
    await panel.getByLabel("Marca").selectOption("Ford");
    // Pro also searches by body type: «Modelo» is a mode too, so the select by its role.
    await panel.getByRole("combobox", { name: "Modelo" }).selectOption("Fiesta");
    const seller = panel.getByLabel(/^Vendedor/);
    await expect(seller.locator("option")).toHaveText(["Cualquiera", "Particulares", "Agencias (incluye posibles agencias)"]);
    await seller.selectOption("private");
    await panel.getByText("Solo este tipo de vendedor", { exact: true }).click();
    await expect(panel.getByTestId("seller-strict-hint")).toHaveText(
      "Descartamos los otros. Si la publicación no dice quién vende, el aviso pasa con menos puntaje.");
    await expectNoHorizontalScroll(page);
    await panel.getByText("Todo el país", { exact: true }).click();
    await panel.getByRole("button", { name: "Crear búsqueda" }).click();
    await expect(page).toHaveURL(/\/app\/searches\/\d+$/);
    id = Number(page.url().split("/").pop());
    expect((await stored(id)).filters.seller_types).toEqual(["private"]);
    expect((await stored(id)).preferences).not.toHaveProperty("seller_type");
    await expect(page.getByTestId("search-criteria")).toContainText("Solo particulares");
    await expectNoHorizontalScroll(page);
  });

  await test.step("editar a agencias cambia el resumen", async () => {
    await page.goto(`/app/searches/${id}/edit`);
    await page.getByLabel(/^Vendedor/).selectOption("dealer");
    await expect(page.getByTestId("seller-strict-hint")).toBeVisible();
    await page.getByRole("button", { name: "Guardar cambios" }).click();
    await expect(page).toHaveURL(new RegExp(`/app/searches/${id}$`));
    await expect(page.getByTestId("search-criteria")).toContainText("Solo agencias (incluye posibles agencias)");
    expect((await stored(id)).filters.seller_types).toEqual(["dealer"]);
    expect((await sellerEvents(email)).map((e) => [e.props.seller_types, e.props.mode]))
      .toEqual([[["private"], "structured"], [["dealer"], "edit"]]);
  });
});

test("sin Pro: el filtro guardado avisa «solo Pro» y se puede quitar", async ({ page }, testInfo) => {
  const email = `pro01-pass-${testInfo.project.name}-${Date.now()}@${E2E_EMAIL_DOMAIN}`;
  await signIn(page, email);
  await setPlan(email, "pass");
  // A downgrade: the strict filter was saved while the account was Pro.
  const [{ id }] = await query<{ id: number }>(
    `insert into public.search_profiles (user_id, name, filters, bootstrapped_at)
     select id, 'Ford Fiesta', '{"make": "Ford", "model": "Fiesta", "trims": [], "trim_strict": false, "seller_types": ["private"]}', now()
       from public.profiles where email = $1 returning id`, [email]);

  await page.goto(`/app/searches/${id}`);
  await expect(page.getByTestId("search-criteria")).toContainText("Particulares (preferido; filtro estricto solo Pro)");

  await page.goto(`/app/searches/${id}/edit`);
  await expect(page.getByText("Solo este tipo de vendedor")).toHaveCount(0);
  const notice = page.getByTestId("seller-strict-pro-only");
  await expect(notice).toContainText("Filtro estricto: solo Pro. En tu plan se usa como preferencia.");
  await expect(page.getByLabel(/^Vendedor/)).toHaveValue("private");
  await expectNoHorizontalScroll(page);
  await notice.getByRole("button", { name: "Quitar filtro estricto" }).click();
  await expect(notice).toHaveCount(0);
  await page.getByRole("button", { name: "Guardar cambios" }).click();
  await expect(page).toHaveURL(new RegExp(`/app/searches/${id}$`));
  await expect(page.getByTestId("search-criteria")).not.toContainText("solo Pro");
  const row = await stored(Number(id));
  expect(row.filters).not.toHaveProperty("seller_types");
  expect(row.preferences).toMatchObject({ seller_type: "private" });
  expect((await sellerEvents(email)).map((e) => e.props.seller_types)).toEqual([[]]);
});
