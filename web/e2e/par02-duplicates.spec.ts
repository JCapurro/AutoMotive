import { expect, type Page, test } from "@playwright/test";

import { query } from "./support/db";
import { E2E_EMAIL_DOMAIN, E2E_LISTING_PREFIX } from "./support/env";
import { signUp } from "./support/auth";

/**
 * PAR-02 resto: the duplicate flags of «Conviene verificar». A
 * cross_source_duplicate whose other listing is in the base links to its page
 * and records duplicate_link_clicked; one whose other listing is not links to
 * its URL in a new tab; private_many_listings is a plain row. On desktop and on
 * a 375 px phone, without horizontal scroll.
 */

// An id no listing has: the page falls back to the stored URL.
const MISSING_ID = 2_000_000_001;

async function signIn(page: Page, email: string) {
  await signUp(page, email, "/app");
}

async function listingId(key: string): Promise<number> {
  const [row] = await query<{ id: string }>(`select id from public.listings where external_id = $1`, [`${E2E_LISTING_PREFIX}${key}`]);
  return Number(row.id);
}

async function duplicateEvents(email: string): Promise<Record<string, unknown>[]> {
  const rows = await query<{ props: Record<string, unknown> }>(
    `select e.props from public.events e join public.profiles p on p.id = e.user_id
      where p.email = $1 and e.name = 'duplicate_link_clicked' order by e.created_at`,
    [email],
  );
  return rows.map((row) => row.props);
}

async function expectNoHorizontalScroll(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow, `horizontal overflow on ${page.url()}`).toBeLessThanOrEqual(0);
}

test("la ficha enlaza la otra publicación de un duplicado y registra el click", async ({ page }, testInfo) => {
  const run = `${testInfo.project.name}-${Date.now()}`;
  const email = `par02dup-${run}@${E2E_EMAIL_DOMAIN}`;
  await signIn(page, email);
  const target = await listingId("target");
  const other = await listingId("c1");

  const flags = [
    {
      id: "cross_source_duplicate",
      severity: "info",
      text: "Parece el mismo auto publicado también en Autocity (mismas fotos): conviene comparar las dos publicaciones.",
      link: { listing_id: other, url: "https://example.test/autocity/1", source_name: "Autocity", kind: "cross_source_photos" },
    },
    {
      id: "duplicate_photos",
      severity: "warning",
      text: "Las fotos de esta publicación aparecen también en otra publicación (Rosario Garage) con otros datos: conviene pedir fotos actuales y ver el auto antes de señar.",
      link: { listing_id: MISSING_ID, url: "https://example.test/rosariogarage/9", source_name: "Rosario Garage", kind: "duplicate_photos" },
    },
    { id: "private_many_listings", severity: "info", text: "El vendedor tiene 7 publicaciones activas: conviene preguntar si es titular." },
  ];
  const [profile] = await query<{ id: string }>(
    `insert into public.search_profiles (user_id, name, filters, notification_frequency, bootstrapped_at)
     select id, 'Fiesta duplicados', '{"make": "Ford", "model": "Fiesta"}', 'daily', now()
       from public.profiles where email = $1
     returning id`,
    [email],
  );
  await query(
    `insert into public.matches (search_profile_id, listing_id, score, level, score_breakdown, match_reasons, red_flags, scoring_version)
     values ($1, $2, 72, 'good', '{}', '{}', $3::jsonb, 'e2e')`,
    [profile.id, target, JSON.stringify(flags)],
  );

  await page.goto(`/app/listings/${target}`);
  const list = page.getByTestId("red-flags");
  await expect(list).toBeVisible();
  await expect(list.locator('[data-flag="private_many_listings"]')).toContainText("7 publicaciones activas");
  await expect(list.locator('[data-flag="private_many_listings"]').getByTestId("duplicate-link")).toHaveCount(0);

  const external = list.locator('[data-flag="duplicate_photos"]').getByTestId("duplicate-link");
  await expect(external).toHaveText("Ver la otra publicación");
  await expect(external).toHaveAttribute("href", "https://example.test/rosariogarage/9");
  await expect(external).toHaveAttribute("target", "_blank");
  await expect(external).toHaveAttribute("rel", "noopener noreferrer");

  const internal = list.locator('[data-flag="cross_source_duplicate"]').getByTestId("duplicate-link");
  await expect(internal).toHaveAttribute("href", `/app/listings/${other}`);
  await expectNoHorizontalScroll(page);

  await internal.click();
  await expect(page).toHaveURL(new RegExp(`/app/listings/${other}$`));
  await expect
    .poll(() => duplicateEvents(email))
    .toEqual([{ listing_id: target, other_listing_id: other, kind: "cross_source_photos", target: "internal" }]);
});
