import { expect, type Page, test } from "@playwright/test";

import { query } from "./support/db";
import { E2E_EMAIL_DOMAIN, E2E_LISTING_PREFIX } from "./support/env";
import { magicLink } from "./support/mail";

/**
 * PAR-02 tramo 1: the listing page's «Antes de señar» checklist. Closed by
 * default, open with an emphasis line for much_cheaper, without any link until
 * app_config.risk.links is loaded, hidden for a gone listing or when the switch
 * is off. On desktop and on a 375 px phone.
 */

const RISK_DEFAULT = {
  checklist_enabled: true,
  links: { dnrpa: null, patentes: [], infracciones: [], vtv: null, form_08: null },
};
let originalRisk: unknown = null;

test.beforeAll(async () => {
  const [row] = await query<{ value: unknown }>(`select value from public.app_config where key = 'risk'`);
  originalRisk = row?.value ?? null;
});

test.afterEach(async () => {
  await query(
    `insert into public.app_config (key, value) values ('risk', $1::jsonb)
     on conflict (key) do update set value = excluded.value`,
    [JSON.stringify(originalRisk ?? RISK_DEFAULT)],
  );
  await query(`update public.listings set status = 'active' where external_id = $1`, [`${E2E_LISTING_PREFIX}target`]);
});

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

/** A user with a match on the seeded Fiesta (support/db.ts); returns the listing id. */
async function seedMatch(
  page: Page,
  prefix: string,
  run: string,
  redFlags: unknown[] = [],
): Promise<{ email: string; listingId: number; profileId: string }> {
  const email = `${prefix}-${run}@${E2E_EMAIL_DOMAIN}`;
  await signIn(page, email);
  const [target] = await query<{ id: string }>(`select id from public.listings where external_id = $1`, [
    `${E2E_LISTING_PREFIX}target`,
  ]);
  const [profile] = await query<{ id: string }>(
    `insert into public.search_profiles (user_id, name, filters, notification_frequency, bootstrapped_at)
     select id, 'Fiesta antes de señar', '{"make": "Ford", "model": "Fiesta"}', 'daily', now()
       from public.profiles where email = $1
     returning id`,
    [email],
  );
  await query(
    `insert into public.matches (search_profile_id, listing_id, score, level, score_breakdown, match_reasons, red_flags, scoring_version)
     values ($1, $2, 72, 'good', '{}', '{}', $3::jsonb, 'e2e')`,
    [profile.id, target.id, JSON.stringify(redFlags)],
  );
  return { email, listingId: Number(target.id), profileId: profile.id };
}

const MUCH_CHEAPER = {
  id: "much_cheaper",
  text: "Publicación 40% más barata que publicaciones comparables: un precio tan por debajo es motivo para verificar todo antes de señar.",
  severity: "warning",
};

async function riskEvents(email: string, listingId: number): Promise<string[]> {
  const rows = await query<{ name: string }>(
    `select e.name from public.events e join public.profiles p on p.id = e.user_id
      where p.email = $1 and e.name like 'risk_checklist_%' and (e.props->>'listing_id')::bigint = $2`,
    [email, listingId],
  );
  return rows.map((row) => row.name).sort();
}

/** The open block is fully below the fold: it logs no view until it is scrolled into it. */
async function expectViewedOnlyOnScreen(page: Page, email: string, listingId: number) {
  const block = page.getByTestId("risk-checklist");
  await expect(block).toHaveAttribute("open", "");
  // The page streams in under app/app/loading.tsx: until React reveals the
  // segment, the block sits inside a hidden <div id="S:N"> and measures 0x0 at
  // top 0. toBeVisible ignores the viewport, so this only waits for the reveal.
  await expect(block).toBeVisible();
  const below = await block.evaluate((node) => node.getBoundingClientRect().top - window.innerHeight);
  expect(below, "the block has to start below the fold for this check").toBeGreaterThan(0);
  // What fired on mount would have been recorded by now.
  await page.waitForTimeout(2_500);
  expect(await riskEvents(email, listingId)).toEqual([]);

  await block.scrollIntoViewIfNeeded();
  await expect.poll(() => riskEvents(email, listingId)).toEqual(["risk_checklist_viewed"]);
}

async function expectNoHorizontalScroll(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow, `horizontal overflow on ${page.url()}`).toBeLessThanOrEqual(0);
}

test("la ficha muestra «Antes de señar» y copia la checklist sin links", async ({ page, context, baseURL }, testInfo) => {
  const run = `${testInfo.project.name}-${Date.now()}`;
  const { email, listingId } = await seedMatch(page, "risk", run);
  await context.grantPermissions(["clipboard-read", "clipboard-write"], { origin: baseURL });

  await page.goto(`/app/listings/${listingId}`);
  await expect(page.getByRole("heading", { name: "Antes de señar" })).toBeVisible();
  const block = page.getByTestId("risk-checklist");
  await expect(block).not.toHaveAttribute("open", "");
  await expect(page.getByTestId("risk-emphasis")).toHaveCount(0);

  await block.locator("summary").click();
  await expect(block.getByText("Son controles que conviene hacer vos. Ese Auto no verificó nada de esta publicación.")).toBeVisible();
  await expect(block.locator("[data-risk-item]")).toHaveCount(7);
  await expect(block.locator("a")).toHaveCount(0);
  await expectNoHorizontalScroll(page);

  await block.getByRole("button", { name: "Copiar checklist" }).click();
  await expect(page.getByText("Copiado. Tenelo a mano antes de señar.")).toBeVisible();
  const copied = await page.evaluate(() => navigator.clipboard.readText());
  expect(copied.toLowerCase()).toContain("conviene verificar");
  expect(copied).toContain("Antes de señar: ");
  expect(copied).not.toContain("http");
  expect(copied).not.toContain(email);

  await expect.poll(() => riskEvents(email, listingId)).toEqual(["risk_checklist_copied", "risk_checklist_viewed"]);
});

test("una copia que falla no se registra como copiada", async ({ page }, testInfo) => {
  const run = `${testInfo.project.name}-${Date.now()}`;
  const { email, listingId } = await seedMatch(page, "risk-copy-fail", run);
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: () => Promise.reject(new DOMException("denied", "NotAllowedError")) },
    });
  });

  await page.goto(`/app/listings/${listingId}`);
  const block = page.getByTestId("risk-checklist");
  await block.locator("summary").click();
  await expect.poll(() => riskEvents(email, listingId)).toEqual(["risk_checklist_viewed"]);

  await block.getByRole("button", { name: "Copiar checklist" }).click();
  await expect(page.getByText("No pudimos copiar. Seleccioná el texto y copialo a mano.")).toBeVisible();
  await page.waitForTimeout(2_500);
  expect(await riskEvents(email, listingId)).toEqual(["risk_checklist_viewed"]);
});

test("expandida por much_cheaper, la vista cuenta recién cuando el bloque entra en pantalla", async ({ page }, testInfo) => {
  const run = `${testInfo.project.name}-${Date.now()}`;
  const viewport = page.viewportSize() ?? { width: 1280, height: 720 };
  await page.setViewportSize({ width: viewport.width, height: 240 });

  // Server-rendered load.
  const first = await seedMatch(page, "risk-fold-ssr", run, [MUCH_CHEAPER]);
  await page.goto(`/app/listings/${first.listingId}`);
  await expectViewedOnlyOnScreen(page, first.email, first.listingId);

  // Client-side navigation from the search's results, where React creates the block.
  await page.context().clearCookies();
  const second = await seedMatch(page, "risk-fold-nav", run, [MUCH_CHEAPER]);
  await page.goto(`/app/searches/${second.profileId}`);
  await page.locator(`a[href="/app/listings/${second.listingId}"]`).first().click();
  await expect(page).toHaveURL(new RegExp(`/app/listings/${second.listingId}$`));
  await expectViewedOnlyOnScreen(page, second.email, second.listingId);
});

test("los links oficiales cargados abren en otra pestaña", async ({ page }, testInfo) => {
  const run = `${testInfo.project.name}-${Date.now()}`;
  const { listingId } = await seedMatch(page, "risk-links", run);
  await query(`update public.app_config set value = $1::jsonb where key = 'risk'`, [
    JSON.stringify({
      checklist_enabled: true,
      links: {
        dnrpa: { label: "Informe de prueba", url: "https://example.test/dnrpa" },
        patentes: [{ label: "Jurisdicción A", url: "https://example.test/patentes-a" }],
        infracciones: [],
        vtv: { label: "Link sin https", url: "http://example.test/vtv" },
        form_08: null,
      },
    }),
  ]);

  await page.goto(`/app/listings/${listingId}`);
  const block = page.getByTestId("risk-checklist");
  await block.locator("summary").click();
  const links = block.locator("a");
  await expect(links).toHaveCount(2);
  for (const link of await links.all()) {
    await expect(link).toHaveAttribute("target", "_blank");
    await expect(link).toHaveAttribute("rel", "noopener noreferrer");
    await expect(link).toHaveAttribute("href", /^https:\/\/example\.test\//);
  }
  await expect(block.getByRole("link", { name: /Ver sitio oficial/ })).toHaveCount(1);
  await expect(block.getByRole("link", { name: "Jurisdicción A" })).toBeVisible();
  await expectNoHorizontalScroll(page);
});

test("con much_cheaper abre expandida; apagada o con el aviso dado de baja no está", async ({ page }, testInfo) => {
  const run = `${testInfo.project.name}-${Date.now()}`;
  const { listingId } = await seedMatch(page, "risk-flags", run, [MUCH_CHEAPER]);

  await page.goto(`/app/listings/${listingId}`);
  const block = page.getByTestId("risk-checklist");
  await expect(block).toHaveAttribute("open", "");
  await expect(page.getByTestId("risk-emphasis")).toBeVisible();
  await expectNoHorizontalScroll(page);

  await query(`update public.app_config set value = jsonb_set(value, '{checklist_enabled}', 'false') where key = 'risk'`);
  await page.reload();
  await expect(page.getByTestId("price")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Antes de señar" })).toHaveCount(0);

  await query(`update public.app_config set value = jsonb_set(value, '{checklist_enabled}', 'true') where key = 'risk'`);
  await query(`update public.listings set status = 'gone' where id = $1`, [listingId]);
  await page.reload();
  await expect(page.getByText("Esta publicación ya no está disponible.", { exact: false })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Antes de señar" })).toHaveCount(0);
});
