import { expect, type Page, test } from "@playwright/test";

import { insertFreshDeal, query } from "./support/db";
import { E2E_EMAIL_DOMAIN } from "./support/env";
import { magicLink } from "./support/mail";

/**
 * F6 acceptance (docs/TECHNICAL_PLAN.md, sección 13):
 *   * from the admin, "¿por qué se envió esta alerta?" in one click;
 *   * v_validation_criteria shows the six §53 criteria;
 *   * /admin is closed to non-admins;
 *   * "Ver planes" → Particular → waitlist, with its events.
 * On desktop and on a 375 px phone (the `mobile` project).
 */

test.describe.configure({ mode: "serial" });

async function signIn(page: Page, email: string, next = "/app") {
  const since = new Date();
  await page.goto(`/login?next=${encodeURIComponent(next)}`);
  await page.getByLabel("Email").fill(email);
  await page.getByRole("link", { name: "Crear cuenta", exact: true }).click();
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Contraseña", { exact: true }).fill("e2e-password-123");
  await page.getByLabel("Repetí la contraseña").fill("e2e-password-123");
  await page.getByRole("button", { name: "Crear cuenta", exact: true }).click();
  await expect(page.getByText("Revisá tu email")).toBeVisible();
  await page.goto(await magicLink(email, since));
}

async function expectNoHorizontalScroll(page: Page) {
  const { overflow, culprits } = await page.evaluate(() => {
    const width = document.documentElement.clientWidth;
    // Elements past the right edge that aren't clipped by a scroll container.
    const culprits = [...document.body.querySelectorAll<HTMLElement>("*")]
      .filter((el) => el.getBoundingClientRect().right > width + 1)
      .filter((el) => !el.parentElement?.closest(".overflow-x-auto") || getComputedStyle(el).position === "absolute")
      .slice(0, 5)
      .map((el) => `${el.tagName.toLowerCase()}.${el.className}`.slice(0, 120));
    return { overflow: document.documentElement.scrollWidth - width, culprits };
  });
  expect(overflow, `horizontal overflow on ${page.url()}: ${culprits.join(" | ")}`).toBeLessThanOrEqual(0);
}

/** A user with a search, a 🔥 match and the Telegram alert the engine sent for it. */
async function alertedUser(run: string) {
  const email = `alerted-${run}@${E2E_EMAIL_DOMAIN}`;
  const [user] = await query<{ id: string }>(
    `insert into auth.users (instance_id, id, aud, role, email, created_at, updated_at)
     values ('00000000-0000-0000-0000-000000000000', gen_random_uuid(), 'authenticated', 'authenticated', $1, now(), now())
     returning id`,
    [email],
  );
  const [profile] = await query<{ id: number }>(
    `insert into public.search_profiles (user_id, name, filters, notification_frequency, bootstrapped_at)
     values ($1, 'Fiesta e2e', '{"make": "Ford", "model": "Fiesta", "year_min": 2016, "year_max": 2018}', 'daily', now())
     returning id`,
    [user.id],
  );
  const listingId = await insertFreshDeal(`admin-${run}`);
  const [match] = await query<{ id: number }>(
    `insert into public.matches (search_profile_id, listing_id, score, level, score_breakdown, match_reasons, price_ref,
                                 red_flags, scoring_version)
     values ($1, $2, 88, 'high',
       '{"price": {"c": 0.9, "w": 35, "contribution": 31.5, "explanation": "18% debajo de la mediana"},
         "km": {"c": 0.8, "w": 15, "contribution": 12, "explanation": "105.000 km"}}',
       '{"model": {"result": "ok", "detail": "Ford Fiesta", "kind": "hard"},
         "year": {"result": "ok", "detail": "2017", "kind": "hard"},
         "transmission": {"result": "unknown", "detail": "", "kind": "hard"},
         "price": {"result": "ok", "detail": "USD 9.900", "kind": "hard"}}',
       '{"n": 7, "level_used": "transmission", "median": 12100, "p25": 11500, "p75": 12600, "median_km": 98000, "diff_pct": 18.2}',
       '[{"id": "no_description", "text": "La publicación no tiene descripción.", "severity": "info"}]', 'e2e')
     returning id`,
    [profile.id, listingId],
  );
  const [notification] = await query<{ id: number }>(
    `insert into public.notifications (user_id, match_id, listing_id, search_profile_id, kind, channel, status,
                                       dedupe_key, payload, sent_at)
     values ($1, $2, $3, $4, 'opportunity', 'telegram', 'sent', $5,
             '{"match": {"level": "high", "score": 88}}', now())
     returning id`,
    [user.id, match.id, listingId, profile.id, `match:${listingId}`],
  );
  return { listingId, profileId: profile.id, notificationId: notification.id };
}

test("F6: el admin responde «¿por qué se envió esta alerta?» en un clic", async ({ page }, testInfo) => {
  const run = `${testInfo.project.name}-${Date.now()}`;
  const email = `admin-${run}@${E2E_EMAIL_DOMAIN}`;
  const alert = await alertedUser(run);

  await test.step("/admin está cerrado para quien no es admin", async () => {
    await signIn(page, email);
    await expect(page).toHaveURL(/\/app/);
    await page.goto("/admin");
    await expect(page).toHaveURL(/\/app$/);
  });

  await query(`update public.profiles set role = 'admin' where email = $1`, [email]);

  await test.step("Resumen: los 6 criterios del §53", async () => {
    await page.goto("/admin");
    await expect(page.getByRole("heading", { name: "Criterios de validación (§53)" })).toBeVisible();
    const criteria = page.getByTestId("validation-criteria").getByRole("listitem");
    await expect(criteria).toHaveCount(6);
    for (const label of ["Uso", "Relevancia", "Engagement", "Retención", "Outcome", "Monetización"]) {
      await expect(page.getByTestId("validation-criteria").getByText(label, { exact: true })).toBeVisible();
    }
    await expectNoHorizontalScroll(page);
  });

  await test.step("Notificaciones → ¿Por qué? (un clic)", async () => {
    await page.goto("/admin/notifications");
    const row = page.getByRole("row").filter({ has: page.getByRole("cell", { name: String(alert.notificationId), exact: true }) });
    await row.getByRole("link", { name: "¿Por qué?" }).click();
    await expect(page).toHaveURL(new RegExp(`/admin/notifications/${alert.notificationId}$`));
    const why = page.getByTestId("why-block");
    await expect(why).toContainText(`Listing #${alert.listingId}`);
    await expect(why).toContainText(`matched Search #${alert.profileId}`);
    await expect(why).toContainText("model = true");
    await expect(why).toContainText("transmission = unknown");
    await expect(why).toContainText("score = 88");
    await expect(page.getByText("misma caja · usado")).toBeVisible();
    await expect(page.getByText("La publicación no tiene descripción.")).toBeVisible();
    await expectNoHorizontalScroll(page);
  });
});

test("F6: «Ver planes» → Particular → lista de espera", async ({ page }, testInfo) => {
  const run = `${testInfo.project.name}-${Date.now()}`;
  const email = `pro-${run}@${E2E_EMAIL_DOMAIN}`;
  await signIn(page, email);

  // Real activity (§52): a search and three alerts clicked.
  const [user] = await query<{ id: string }>(`select id from public.profiles where email = $1`, [email]);
  await query(
    `insert into public.search_profiles (user_id, name, filters, notification_frequency, bootstrapped_at)
     values ($1, 'Fiesta', '{"make": "Ford", "model": "Fiesta"}', 'daily', now())`,
    [user.id],
  );
  await query(
    `insert into public.events (user_id, name, props)
     select $1, 'alert_clicked', jsonb_build_object('notification_id', n) from generate_series(1, 3) n`,
    [user.id],
  );
  const events = async (name: string) =>
    query<{ props: Record<string, string> }>(`select props from public.events where user_id = $1 and name = $2 order by id`, [
      user.id,
      name,
    ]);

  await test.step("el banner aparece en el dashboard", async () => {
    await page.goto("/app");
    const banner = page.getByTestId("pro-banner");
    await expect(banner).toContainText("Seguí buscando con Ese Auto");
    await expect.poll(async () => (await events("pro_cta_viewed")).map((e) => e.props.placement)).toEqual(["dashboard"]);
    await expectNoHorizontalScroll(page);
    await banner.getByRole("button", { name: "Ver planes" }).click();
    await expect(page).toHaveURL(/\/app\/pro\?from=dashboard$/);
    expect((await events("pro_cta_clicked")).map((e) => e.props.placement)).toEqual(["dashboard"]);
  });

  await test.step("elige Particular y se suma a la lista", async () => {
    await expect(page.getByRole("heading", { name: "Elegí cuánto querés buscar" })).toBeVisible();
    await expectNoHorizontalScroll(page);
    await page.getByRole("radio", { name: /Particular/ }).check();
    await page.getByRole("button", { name: "Sumarme a la lista de espera" }).click();
    await expect(page.getByTestId("waitlist-joined")).toContainText("Particular");
    const [row] = await query<{ plan: string; placement: string }>(`select plan, placement from public.pro_waitlist where user_id = $1`, [
      user.id,
    ]);
    expect(row).toEqual({ plan: "pass_30", placement: "dashboard" });
    expect((await events("waitlist_joined")).map((e) => e.props.plan)).toEqual(["pass_30"]);
  });

  await test.step("ya en la lista, el banner no vuelve", async () => {
    await page.goto("/app");
    await expect(page.getByRole("heading", { name: "Mis búsquedas" })).toBeVisible();
    await expect(page.getByTestId("pro-banner")).toHaveCount(0);
  });
});
