import { expect, type Page, test } from "@playwright/test";

import { query } from "./support/db";
import { E2E_EMAIL_DOMAIN } from "./support/env";
import { magicLink } from "./support/mail";
import { worker } from "./support/worker";

/**
 * F5 modo asistido (docs/TECHNICAL_PLAN.md, sección 8.4): text → llm_jobs →
 * worker (recorded `claude -p` answers: `tools.llm_jobs --replay`) → one
 * editable form per vehicle → the user saves each; and the fallback to the
 * empty structured form when the LLM fails.
 */

test.describe.configure({ mode: "serial" });

// A golden phrase with a recorded answer (worker/tests/fixtures/llm/).
const TWO_VEHICLES = "Fiesta Titanium o Polo Highline, 2017 en adelante, hasta 12 mil dólares";

/** The web only queues a job if the worker beat recently; `tools.llm_jobs --replay` doesn't beat. */
async function setHeartbeat(ago: string) {
  await query(
    `insert into public.worker_heartbeat (id, started_at, beat_at, host, pid)
     values (1, now() - $1::interval, now() - $1::interval, 'e2e', 0)
     on conflict (id) do update set beat_at = excluded.beat_at`,
    [ago],
  );
}

test.beforeEach(async () => {
  await setHeartbeat("0 seconds");
});

async function signIn(page: Page, email: string) {
  const since = new Date();
  await page.goto("/login?next=/app/searches/new");
  await page.getByLabel("Email").fill(email);
  await page.getByRole("button", { name: "Enviarme el link" }).click();
  await expect(page.getByText("Revisá tu email")).toBeVisible();
  await page.goto(await magicLink(email, since));
  await expect(page).toHaveURL(/\/app\/searches\/new$/);
}

/** Nothing sticks out sideways (the review screen at 375 px included). */
async function expectNoHorizontalScroll(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow, `horizontal overflow on ${page.url()}`).toBeLessThanOrEqual(0);
}

async function ask(page: Page, text: string) {
  await page.getByRole("tab", { name: "Asistido" }).click();
  await page.getByLabel("¿Qué auto buscás?").fill(text);
  await page.getByRole("button", { name: "Interpretar" }).click();
  // The job is in the table once the page waits for it.
  await expect(page.getByRole("status")).toContainText("Interpretando tu búsqueda");
  worker("llm_jobs", "--replay");
}

test("F5: dos vehículos en un pedido, revisados y guardados", async ({ page }, testInfo) => {
  const email = `assisted-${testInfo.project.name}-${Date.now()}@${E2E_EMAIL_DOMAIN}`;
  await signIn(page, email);
  await ask(page, TWO_VEHICLES);

  const vehicles = page.getByRole("navigation", { name: "Vehículos del pedido" });
  await expect(vehicles.getByRole("button", { name: /^\d\./ })).toHaveText(["1. Ford Fiesta Titanium", "2. Volkswagen Polo Highline"]);
  await expectNoHorizontalScroll(page);

  // The first proposal, pre-filled and editable: the user tightens the years.
  const fiesta = page.getByRole("region", { name: "Vehículo 1 de 2: Ford Fiesta Titanium" });
  await expect(fiesta.getByLabel("Marca")).toHaveValue("Ford");
  await expect(fiesta.getByLabel("Modelo")).toHaveValue("Fiesta");
  await expect(fiesta.getByLabel(/^Versión/)).toHaveValue("Titanium");
  await expect(fiesta.getByLabel("Año desde")).toHaveValue("2017");
  await expect(fiesta.getByLabel("Precio máximo")).toHaveValue("12.000");
  await fiesta.getByLabel("Año hasta").selectOption("2018");
  await fiesta.getByRole("button", { name: "Crear búsqueda" }).click();
  await expect(fiesta).toBeHidden();

  const polo = page.getByRole("region", { name: "Vehículo 2 de 2: Volkswagen Polo Highline" });
  await expect(polo.getByLabel("Modelo")).toHaveValue("Polo");
  await polo.getByRole("button", { name: "Crear búsqueda" }).click();
  await expect(page).toHaveURL(/\/app$/);

  const saved = await query<{ name: string; filters: Record<string, unknown>; raw_query: string }>(
    `select sp.name, sp.filters, sp.raw_query from public.search_profiles sp
       join public.profiles p on p.id = sp.user_id where p.email = $1 order by sp.id`,
    [email],
  );
  expect(saved.map((s) => s.name)).toEqual(["Ford Fiesta Titanium", "Volkswagen Polo Highline"]);
  expect(saved[0].filters).toMatchObject({ make: "Ford", model: "Fiesta", trims: ["Titanium"], year_min: 2017, year_max: 2018 });
  expect(saved[1].filters).toMatchObject({ make: "Volkswagen", model: "Polo", year_min: 2017, price_max: 12000 });
  expect(saved.every((s) => s.raw_query === TWO_VEHICLES)).toBe(true);

  const events = await query<{ props: { mode: string; edited: boolean } }>(
    `select e.props from public.events e join public.profiles p on p.id = e.user_id
      where p.email = $1 and e.name = 'search_profile_created' order by e.id`,
    [email],
  );
  expect(events.map((e) => [e.props.mode, e.props.edited])).toEqual([
    ["assisted", true],
    ["assisted", false],
  ]);
  const [job] = await query<{ status: string; latency_ms: number | null }>(
    `select j.status, j.latency_ms from public.llm_jobs j join public.profiles p on p.id = j.user_id where p.email = $1`,
    [email],
  );
  expect(job.status).toBe("done");
  expect(job.latency_ms).not.toBeNull();
});

test("F5: sumar a mano otro vehículo al pedido", async ({ page }, testInfo) => {
  const email = `assisted-add-${testInfo.project.name}-${Date.now()}@${E2E_EMAIL_DOMAIN}`;
  await signIn(page, email);
  await ask(page, "Busco Fiesta Titanium manual 2016 a 2018 hasta USD 11.500 y menos de 150.000 km");
  await page.getByRole("button", { name: "Agregar otro vehículo" }).click();

  const vehicles = page.getByRole("navigation", { name: "Vehículos del pedido" });
  await expect(vehicles.getByRole("button", { name: /^\d\./ })).toHaveText(["1. Ford Fiesta Titanium", "2. Vehículo 2"]);
  const added = page.getByRole("region", { name: "Vehículo 2 de 2: Vehículo 2" });
  await expect(added.getByLabel("Marca")).toHaveValue("");
  await expect(added.getByLabel("Año desde")).toHaveValue("2016");
  await expect(added.getByLabel("Precio máximo")).toHaveValue("11.500");
  await added.getByLabel("Marca").selectOption("Volkswagen");
  await added.getByLabel("Modelo").selectOption("Gol Trend");
  await added.getByRole("button", { name: "Crear búsqueda" }).click();
  await expect(added).toBeHidden();

  const fiesta = page.getByRole("region", { name: "Vehículo 1 de 2: Ford Fiesta Titanium" });
  await fiesta.getByRole("button", { name: "Crear búsqueda" }).click();
  await expect(page).toHaveURL(/\/app$/);

  const saved = await query<{ filters: Record<string, unknown> }>(
    `select sp.filters from public.search_profiles sp
       join public.profiles p on p.id = sp.user_id where p.email = $1 order by sp.id`,
    [email],
  );
  expect(saved.map((s) => s.filters)).toEqual([
    expect.objectContaining({ make: "Volkswagen", model: "Gol Trend", year_min: 2016, year_max: 2018, km_max: 150000 }),
    expect.objectContaining({ make: "Ford", model: "Fiesta", year_min: 2016, year_max: 2018 }),
  ]);
});

test("F5: si el LLM falla, el formulario estructurado vacío", async ({ page }, testInfo) => {
  const email = `assisted-fail-${testInfo.project.name}-${Date.now()}@${E2E_EMAIL_DOMAIN}`;
  await signIn(page, email);
  // No recorded answer for this text: the replayed provider fails like the CLI would.
  await ask(page, "Un texto que no tiene respuesta grabada");

  await expect(page.getByTestId("assisted-fallback")).toContainText("No pude interpretarlo, completá los filtros");
  await expect(page.getByLabel("Marca")).toHaveValue("");
  await page.getByLabel("Marca").selectOption("Ford");
  await page.getByLabel("Modelo").selectOption("Ka");
  await page.getByRole("button", { name: "Crear búsqueda" }).click();
  await expect(page).toHaveURL(/\/app\/searches\/\d+$/);

  const [created] = await query<{ props: { mode: string } }>(
    `select e.props from public.events e join public.profiles p on p.id = e.user_id
      where p.email = $1 and e.name = 'search_profile_created'`,
    [email],
  );
  expect(created.props.mode).toBe("assisted_fallback");
  const [job] = await query<{ status: string; error: string }>(
    `select j.status, j.error from public.llm_jobs j join public.profiles p on p.id = j.user_id where p.email = $1`,
    [email],
  );
  expect(job.status).toBe("failed");
});

test("F5: con el worker caído, el formulario sin encolar nada", async ({ page }, testInfo) => {
  const email = `assisted-down-${testInfo.project.name}-${Date.now()}@${E2E_EMAIL_DOMAIN}`;
  await signIn(page, email);
  await setHeartbeat("1 hour");
  await page.getByRole("tab", { name: "Asistido" }).click();
  await page.getByLabel("¿Qué auto buscás?").fill(TWO_VEHICLES);
  await page.getByRole("button", { name: "Interpretar" }).click();

  await expect(page.getByTestId("assisted-fallback")).toContainText("El intérprete no está disponible ahora");
  await expect(page.getByLabel("Marca")).toHaveValue("");
  const jobs = await query(
    `select j.id from public.llm_jobs j join public.profiles p on p.id = j.user_id where p.email = $1`,
    [email],
  );
  expect(jobs).toEqual([]);
});
