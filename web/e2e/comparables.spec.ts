import { expect, type Page, test } from "@playwright/test";

import { query, seedConfirmationComparables } from "./support/db";
import { E2E_EMAIL_DOMAIN, E2E_LISTING_PREFIX } from "./support/env";
import { magicLink } from "./support/mail";

/**
 * Comparables fase 1 (migration 20261105120000): the listing page's "autos
 * parecidos" come from public.comparable_pool, the pool comparables() counts.
 * A comparable a later complete read of its source no longer saw is left out;
 * a gone one still counts. On desktop and on a 375 px phone.
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

test("la ficha compara contra el mismo pool que comparables()", async ({ page }, testInfo) => {
  const run = `${testInfo.project.name}-${Date.now()}`;
  const email = `comparables-${run}@${E2E_EMAIL_DOMAIN}`;
  await signIn(page, email);

  // The seeded market's Fiesta Titanium 2017 (support/db.ts), matched by a search of this user.
  const [target] = await query<{ id: number }>(`select id from public.listings where external_id = $1`, [
    `${E2E_LISTING_PREFIX}target`,
  ]);
  const [profile] = await query<{ id: number }>(
    `insert into public.search_profiles (user_id, name, filters, notification_frequency, bootstrapped_at)
     select id, 'Fiesta comparables', '{"make": "Ford", "model": "Fiesta"}', 'daily', now()
       from public.profiles where email = $1
     returning id`,
    [email],
  );
  await query(
    `insert into public.matches (search_profile_id, listing_id, score, level, score_breakdown, match_reasons, price_ref,
                                 red_flags, scoring_version)
     values ($1, $2, 72, 'good', '{}', '{}',
       '{"n": 8, "level_used": "trim_transmission", "median": 11400, "p25": 10900, "p75": 12100,
         "median_km": 118000, "diff_pct": 9.6}', '[]', 'e2e')`,
    [profile.id, target.id],
  );
  await seedConfirmationComparables(run);

  await page.goto(`/app/listings/${target.id}`);
  const analysis = page.getByTestId("price-analysis");
  await expect(analysis.getByText("Algunos autos parecidos")).toBeVisible();
  // The cheapest and the dearest of the pool are always listed.
  await expect(analysis.getByText("USD 8.765").first()).toBeVisible(); // gone, still counts
  await expect(analysis.getByText("MercadoLibre").first()).toBeVisible(); // sources(name) through the rpc
  await expect(analysis.getByText("USD 13.579")).toHaveCount(0); // Autocity no longer saw it
  await expect(analysis.getByText("Autocity")).toHaveCount(0);
});
