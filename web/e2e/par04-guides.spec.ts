import { expect, type Page, test } from "@playwright/test";

import { query } from "./support/db";
import { E2E_EMAIL_DOMAIN } from "./support/env";
import { signUp, resetAuthBrakes } from "./support/auth";

/**
 * PAR-04 · Guías por modelo (docs/superpowers/specs/2026-11-03-par04-guias-design.md):
 *   * a published guide is seen with the «Guía orientativa» notice, its
 *     sections, the questions and no price;
 *   * its «Crear mi búsqueda» opens the email-only signup with the model
 *     prefilled (signed out) and goes to /app/searches/new?prompt=… (signed in);
 *   * a draft is a 404 and /guias lists only the published one;
 *   * /admin/guides creates, edits and publishes a guide by hand with the
 *     generation switched off; «Publicar» on a page older than the guide
 *     publishes nothing.
 * On desktop and on a 375 px phone (the `mobile` project).
 */

test.describe.configure({ mode: "serial" });

const SECTIONS = {
  known_issues: [{ text: "Embrague: suele endurecerse con los años.", applies_to: "1.6 nafta" }],
  visit_checklist: [{ text: "Probar el embrague en una subida con carga." }],
  versions_equipment: [{ text: "Versiones furgón y con ventanas." }],
  maintenance_costs: [{ text: "Distribución por correa: preguntar cuándo se cambió." }],
  generations: [{ label: "Fiesta Courier", year_from: 2003, year_to: 2013, text: "Una sola generación en el país." }],
};
const QUESTIONS = [
  { text: "¿Cuándo se cambió la correa de distribución?", why: "" },
  { text: "¿Llevó carga pesada todo el tiempo?", why: "" },
  { text: "¿El embrague es el original?", why: "" },
];

async function expectNoHorizontalScroll(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow, `horizontal overflow on ${page.url()}`).toBeLessThanOrEqual(0);
}

async function events(name: string, model: string): Promise<{ user_id: string | null }[]> {
  return query(`select user_id from public.events where name = $1 and props->>'model' = $2 and created_at > now() - interval '10 minutes'`, [name, model]);
}

test.beforeAll(async () => {
  // Only the models this spec owns: Courier (published), S-Max (draft), Maverick and Territory (made in /admin).
  await query(`delete from public.model_guides where make = 'Ford' and model in ('Courier', 'S-Max', 'Maverick', 'Territory')`);
  await query(
    `insert into public.model_guides (make, model, year_from, year_to, slug_make, slug_model, body, questions, sources,
                                      status, reviewed_at, published_at)
     values ('Ford', 'Courier', 2003, 2013, 'ford', 'courier', $1, $2,
             '[{"title": "Manual del usuario", "url": "https://example.test/courier", "kind": "manual", "verified": true}]',
             'published', now(), now()),
            ('Ford', 'S-Max', 2008, 2015, 'ford', 's-max', $1, $2, '[]', 'draft', null, null)`,
    [JSON.stringify(SECTIONS), JSON.stringify(QUESTIONS)],
  );
});

test.afterAll(async () => {
  await query(`delete from public.model_guides where make = 'Ford' and model in ('Courier', 'S-Max', 'Maverick', 'Territory')`);
  await query(`delete from public.events where name like 'guide\\_%' and props->>'make' = 'Ford' and props->>'model' in ('Courier', 'S-Max', 'Maverick', 'Territory')`);
});

// The landing's sign-ups go through the real brakes: start each test below them.
test.beforeEach(async () => { await resetAuthBrakes(); });

test("PAR-04: la guía publicada se ve con el aviso y su CTA abre el alta con el modelo", async ({ page }, testInfo) => {
  const email = `guide-${testInfo.project.name}-${Date.now()}@${E2E_EMAIL_DOMAIN}`;

  await test.step("la página: aviso, secciones, preguntas, JSON-LD y sin precios", async () => {
    const response = await page.goto("/guias/ford/courier");
    expect(response?.status()).toBe(200);
    await expect(page.getByRole("heading", { level: 1, name: "Ford Courier usado: guía orientativa para revisarlo" })).toBeVisible();
    await expect(page.getByTestId("guide-notice")).toContainText("Guía orientativa");
    await expect(page.getByTestId("guide-notice")).toContainText("reemplaza la revisión de un mecánico");
    for (const name of ["Fallas conocidas", "Qué revisar en la visita", "Versiones y equipamiento", "Mantenimiento y costos típicos", "Generaciones"]) {
      await expect(page.getByRole("heading", { name })).toBeVisible();
    }
    await expect(page.getByTestId("guide-questions").getByRole("listitem")).toHaveCount(3);
    const html = await page.content();
    expect(html).toContain('"@type":"FAQPage"');
    expect(html).toMatch(/<link rel="canonical" href="[^"]*\/guias\/ford\/courier"/);
    expect(html).not.toMatch(/reviewed_by|llm_version|llm_job/);
    // No price anywhere the visitor reads (the search box's placeholder is the landing's example).
    expect(await page.locator("main").innerText()).not.toMatch(/USD|\$\s?\d/);
    await expectNoHorizontalScroll(page);
    await expect.poll(async () => (await events("guide_viewed", "Courier")).length).toBeGreaterThan(0);
  });

  await test.step("deslogueado: «Crear mi búsqueda» abre el alta con el texto prellenado", async () => {
    const form = page.locator("#landing-search");
    await expect(form.getByLabel("¿Qué auto buscás?")).toHaveValue("Busco un Ford Courier 2003 a 2013");
    await form.getByRole("button", { name: "Crear mi búsqueda" }).click();
    const dialog = page.getByRole("dialog", { name: "¿A qué email te avisamos?" });
    await expect(dialog).toBeVisible();
    await expect.poll(async () => (await events("guide_cta_clicked", "Courier")).length).toBeGreaterThan(0);
    await dialog.getByLabel("Tu email").fill(email);
    await dialog.getByRole("button", { name: "Seguir" }).click();
    await expect(page).toHaveURL(/\/app\/searches\/new/);
  });

  await test.step("logueado: va a /app/searches/new con el prompt", async () => {
    await page.goto("/guias/ford/courier");
    const form = page.locator("#landing-search");
    await expect(form.getByRole("button", { name: "Crear mi búsqueda" })).toBeEnabled();
    await form.getByRole("button", { name: "Crear mi búsqueda" }).click();
    await expect(page).toHaveURL(/\/app\/searches\/new\?.*prompt=Busco(\+|%20)un(\+|%20)Ford(\+|%20)Courier/);
    await expect.poll(async () => (await events("guide_cta_clicked", "Courier")).filter((e) => e.user_id).length).toBeGreaterThan(0);
  });
});

test("PAR-04: /admin/guides crea, edita y publica una guía a mano con la generación apagada", async ({ page }, testInfo) => {
  const model = testInfo.project.name === "mobile" ? "Territory" : "Maverick";
  const slug = model.toLowerCase();
  const email = `guides-admin-${testInfo.project.name}-${Date.now()}@${E2E_EMAIL_DOMAIN}`;
  await signUp(page, email, "/app");
  await query(`update public.profiles set role = 'admin' where email = $1`, [email]);

  await page.goto("/admin/guides");
  await expect(page.getByText("La generación con IA está apagada", { exact: false }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Generar borrador" })).toHaveCount(0);
  await page.getByLabel("Marca").fill("Ford");
  await page.getByLabel("Modelo").fill(model);
  await page.getByRole("button", { name: "Crear guía" }).click();
  await expect(page).toHaveURL(/\/admin\/guides\/\d+$/);

  const editor = page.getByRole("form", { name: "Editor de la guía" });
  const sections: [string, string][] = [
    ["known_issues", "Fallas conocidas"], ["visit_checklist", "Qué revisar en la visita"], ["versions_equipment", "Versiones y equipamiento"],
    ["maintenance_costs", "Mantenimiento y costos típicos"],
  ];
  for (const [key, name] of sections) {
    const fieldset = editor.locator(`fieldset[data-section="${key}"]`);
    await fieldset.getByRole("button", { name: "Agregar renglón" }).click();
    await fieldset.getByLabel(`${name}, renglón 1`, { exact: true }).fill(`${name}: un renglón de prueba.`);
  }
  const generations = editor.locator('fieldset[data-section="generations"]');
  await generations.getByRole("button", { name: "Agregar generación" }).click();
  await generations.getByLabel("Generaciones, renglón 1").fill("Una generación de prueba.");
  const questions = editor.locator('fieldset[data-section="questions"]');
  for (const [n, q] of ["¿Tiene los services al día?", "¿Cuántos dueños tuvo?", "¿Tuvo algún choque?"].entries()) {
    await questions.getByRole("button", { name: "Agregar pregunta" }).click();
    await questions.getByLabel(`Pregunta ${n + 1}`, { exact: true }).fill(q);
  }
  // Publishing needs at least one source, checked.
  const sources = editor.locator('fieldset[data-section="sources"]');
  await sources.getByRole("button", { name: "Agregar fuente" }).click();
  await sources.getByLabel("Fuente 1: título").fill("Manual del usuario");
  await sources.getByLabel("Fuente 1: URL").fill("https://example.test/manual");
  await sources.getByLabel("La revisé").check();
  // The money rule says which row fails before saving.
  await editor.getByLabel("Mantenimiento y costos típicos, renglón 1", { exact: true }).fill("El service sale USD 300.");
  await expect(editor.getByLabel("Problemas de copy")).toContainText("Mantenimiento y costos típicos, renglón 1: tiene una cifra de dinero");
  await editor.getByLabel("Mantenimiento y costos típicos, renglón 1", { exact: true }).fill("Services cada 10.000 km.");
  await editor.getByRole("button", { name: "Guardar" }).click();
  await expect(editor.getByText("Guardada.")).toBeVisible();
  await expectNoHorizontalScroll(page);

  // A draft is not public yet.
  expect((await page.request.get(`/guias/ford/${slug}`)).status()).toBe(404);

  // The guide changes behind this page (a draft the worker wrote after «Regenerar»):
  // «Publicar» on the stale page publishes nothing.
  await query(`update public.model_guides set questions = questions || '[{"text": "¿Le hicieron el service de los 60.000 km?", "why": ""}]'::jsonb where make = 'Ford' and model = $1`, [model]);
  await page.getByRole("button", { name: "Publicar" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "cambió desde que abriste esta página" })).toBeVisible();
  expect((await query<{ status: string }>(`select status from public.model_guides where make = 'Ford' and model = $1`, [model]))[0].status).toBe("draft");
  await page.reload();
  await page.getByRole("button", { name: "Publicar" }).click();
  await expect(page.getByText("publicada", { exact: true })).toBeVisible();
  const [row] = await query<{ status: string; reviewed: boolean }>(
    `select g.status, g.reviewed_by = p.id as reviewed from public.model_guides g, public.profiles p where g.make = 'Ford' and g.model = $1 and p.email = $2`,
    [model, email],
  );
  expect(row).toEqual({ status: "published", reviewed: true });

  await page.goto(`/guias/ford/${slug}`);
  await expect(page.getByTestId("guide-notice")).toBeVisible();
  await expect(page.getByText("Services cada 10.000 km.")).toBeVisible();
});

// After the admin's publish: the index and the sitemap are static (ISR) and a
// guide seeded by SQL reaches them on the next invalidation, which publishing
// from /admin/guides does (revalidatePath).
test("PAR-04: un borrador da 404 y el índice lista solo las publicadas", async ({ page }, testInfo) => {
  const model = testInfo.project.name === "mobile" ? "Territory" : "Maverick";
  const draft = await page.goto("/guias/ford/s-max");
  expect(draft?.status()).toBe(404);
  const missing = await page.goto("/guias/ford/no-existe");
  expect(missing?.status()).toBe(404);
  await page.goto("/guias");
  await expect(page.getByRole("link", { name: "Ford Courier" })).toHaveAttribute("href", "/guias/ford/courier");
  await expect(page.getByRole("link", { name: `Ford ${model}` })).toHaveAttribute("href", `/guias/ford/${model.toLowerCase()}`);
  await expect(page.getByRole("link", { name: "Ford S-Max" })).toHaveCount(0);
  await expectNoHorizontalScroll(page);
  const sitemap = await (await page.request.get("/sitemap.xml")).text();
  expect(sitemap).toContain("/guias/ford/courier");
  expect(sitemap).not.toContain("/guias/ford/s-max");
});
