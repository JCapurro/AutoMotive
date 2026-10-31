import { expect, type Page, test } from "@playwright/test";

import { query } from "./support/db";
import { E2E_EMAIL_DOMAIN, E2E_LISTING_PREFIX } from "./support/env";
import { magicLink } from "./support/mail";

/**
 * PRO-01 (docs/superpowers/specs/2026-10-31-pro01-contacto-design.md).
 * Paso 1: Pro creates «solo particulares», sees the explanation, edits it and
 * the summary changes; an account without the feature with a stored strict
 * filter (a downgrade) sees «solo Pro», clears it and the summary says it is
 * a preference no more.
 * Paso 2: the listing page shows the ready-to-send message, copies it
 * (contact_message_copied) and opens it in the email without a recipient,
 * with CRLF line breaks; Ajustes saves a template and refuses one with a
 * forbidden term or a phone number. Desktop and phone (375 px), without
 * horizontal scroll.
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

/** A Ford Fiesta 2017 listing matched by a search of `email`, with one specific question. */
async function seedContactListing(email: string, run: string): Promise<number> {
  const externalId = `${E2E_LISTING_PREFIX}pro01-contact-${run}`;
  const [listing] = await query<{ id: number }>(
    `insert into public.listings (source, external_id, url, title, make, model, trim, year, price, currency, price_usd,
                                  mileage_km, seller_type, published_at, first_seen_at, last_seen_at, fingerprint, status)
     values ('mercadolibre', $1, $2, 'FORD FIESTA 2017 llamá al 11 5555-5555', 'Ford', 'Fiesta', 'Titanium', 2017, 10300, 'USD',
             10300, 112000, 'private', now() - interval '1 day', now() - interval '1 day', now(), $1, 'active')
     returning id`,
    [externalId, `https://example.test/${externalId}`],
  );
  const [profile] = await query<{ id: number }>(
    `insert into public.search_profiles (user_id, name, filters, bootstrapped_at)
     select id, 'Ford Fiesta', '{"make": "Ford", "model": "Fiesta"}', now() from public.profiles where email = $1
     returning id`,
    [email],
  );
  await query(
    `insert into public.matches (search_profile_id, listing_id, score, level, score_breakdown, match_reasons, red_flags,
                                 seller_questions, contact_questions, scoring_version)
     values ($1, $2, 80, 'good', '{}', '{}', '[]', 'Hola, ¿cómo estás? ¿Lo seguís teniendo? ¿Sos titular? ¿Tenés historial de services?',
             '{"¿Tenés historial de services?"}', 'e2e')`,
    [profile.id, listing.id],
  );
  return Number(listing.id);
}

async function copiedEvents(email: string) {
  return query<{ props: { listing_id: number; via: string; custom_template: boolean } }>(
    `select e.props from public.events e join public.profiles p on p.id = e.user_id
      where p.email = $1 and e.name = 'contact_message_copied' order by e.id`, [email]);
}

const DEFAULT_MESSAGE = "Hola, vi tu Fiesta 2017 publicado.\n¿Lo seguís teniendo?\n¿Tenés historial de services?\n¿Cuándo se puede ver?";

test("mensaje listo: ficha, copiar, correo sin destinatario y plantilla en Ajustes", async ({ page, context }, testInfo) => {
  const run = `${testInfo.project.name}-${Date.now()}`;
  const email = `pro01-msg-${run}@${E2E_EMAIL_DOMAIN}`;
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await signIn(page, email);
  const listingId = await seedContactListing(email, run);

  await test.step("la ficha muestra el mensaje y lo copia", async () => {
    await page.goto(`/app/listings/${listingId}`);
    const block = page.getByTestId("contact-message-block");
    await expect(block.getByTestId("contact-message")).toHaveText(DEFAULT_MESSAGE);
    await expect(block).not.toContainText("5555");                       // never the title
    await block.getByRole("button", { name: "Copiar", exact: true }).click();
    await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).toBe(DEFAULT_MESSAGE);
    await expect.poll(async () => (await copiedEvents(email)).map((e) => e.props))
      .toEqual([{ listing_id: listingId, via: "clipboard", custom_template: false }]);
    const href = await block.getByTestId("contact-message-mailto").getAttribute("href");
    expect(href).toMatch(/^mailto:\?subject=Consulta%20por%20tu%20Fiesta%202017&body=/);
    expect(href).toContain("publicado.%0D%0A%C2%BFLo%20segu%C3%ADs%20teniendo%3F%0D%0A");
    expect(href).not.toContain("+");
    await expect(block.getByRole("link", { name: "Mandalo desde la publicación" })).toHaveAttribute("href", `/app/listings/${listingId}/out`);
    await expectNoHorizontalScroll(page);
  });

  await test.step("Ajustes rechaza un término prohibido y un teléfono, y guarda una plantilla", async () => {
    await page.goto("/app/settings");
    const field = page.getByLabel("Tu plantilla");
    const save = page.getByRole("button", { name: "Guardar", exact: true });
    await field.fill("¿Cuánto vale tu {auto}?");
    await expect(page.getByTestId("contact-template-error")).toHaveText("Evitá frases sobre cuánto debería costar el auto: no las podemos verificar.");
    await expect(save).toBeDisabled();
    await field.fill("Llamame al 11 5555-5555");
    await expect(page.getByTestId("contact-template-error")).toHaveText("Sacá los teléfonos: el mensaje se manda desde la publicación.");
    await expect(save).toBeDisabled();
    await field.fill("Buenas, me interesa tu {auto}.\n{preguntas}");
    await expect(page.getByTestId("contact-template-error")).toHaveCount(0);
    await expect(page.getByTestId("contact-template-preview")).toHaveText("Buenas, me interesa tu Fiesta 2017.\n¿Lo seguís teniendo?\n¿Tenés historial de services?");
    await expectNoHorizontalScroll(page);
    await save.click();
    await expect(page.getByText("Mensaje guardado.")).toBeVisible();
    const [row] = await query<{ contact_template: string | null }>(`select contact_template from public.profiles where email = $1`, [email]);
    expect(row.contact_template).toBe("Buenas, me interesa tu {auto}.\n{preguntas}");
  });

  await test.step("la ficha usa la plantilla y el correo la lleva", async () => {
    await page.goto(`/app/listings/${listingId}`);
    const block = page.getByTestId("contact-message-block");
    await expect(block.getByTestId("contact-message")).toHaveText("Buenas, me interesa tu Fiesta 2017.\n¿Lo seguís teniendo?\n¿Tenés historial de services?");
    const mail = block.getByTestId("contact-message-mailto");
    await mail.evaluate((a) => a.addEventListener("click", (e) => e.preventDefault()));   // no mail client here
    await mail.click();
    await expect.poll(async () => (await copiedEvents(email)).map((e) => e.props.via)).toEqual(["clipboard", "mailto"]);
    expect((await copiedEvents(email))[1].props.custom_template).toBe(true);
  });
});
