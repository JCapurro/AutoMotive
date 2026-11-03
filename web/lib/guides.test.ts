import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));
vi.mock("@/lib/supabase/public", () => ({ createPublicClient: vi.fn() }));
// The CTA pulls the signup's server actions; the page test only needs its prompt.
vi.mock("@/components/guides/guide-cta", () => ({
  GuideCta: ({ prompt }: { prompt: string }) => createElement("div", { "data-testid": "guide-cta", "data-prompt": prompt }, "Crear mi búsqueda"),
}));
vi.mock("next/navigation", async (original) => ({
  ...(await original<typeof import("next/navigation")>()),
  notFound: vi.fn(() => {
    throw new Error("NEXT_NOT_FOUND");
  }),
}));

import GuidePage, { generateMetadata, generateStaticParams, revalidate } from "@/app/guias/[marca]/[modelo]/page";
import GuidesIndex, { metadata as indexMetadata } from "@/app/guias/page";
import robots from "@/app/robots";
import sitemap from "@/app/sitemap";
import { GUIDE_COPY } from "@/lib/guides";
import {
  articleJsonLd,
  breadcrumbJsonLd,
  copyProblem,
  ctaPrompt,
  emptyBody,
  faqJsonLd,
  generationAnchor,
  guideBreadcrumb,
  guideDates,
  guideIndexJsonLd,
  guideSummary,
  GuideValuesInput,
  hasMoney,
  isSlug,
  jsonLdScript,
  lintGuide,
  modelYears,
  publishProblem,
  questionsText,
  readBody,
  slugify,
  sortGenerations,
  toPublicGuide,
  type PublicGuideRow,
} from "@/lib/guides";
import { createPublicClient } from "@/lib/supabase/public";

const BODY = {
  known_issues: [{ text: "Caja automática: tirones entre primera y segunda.", applies_to: "1.8 CVT, 2014–2016" }],
  visit_checklist: [{ text: "Probar la caja en frío y en subida.", applies_to: null }],
  versions_equipment: [{ text: "XLi, XEi y SEG.", applies_to: null }],
  maintenance_costs: [{ text: "Services cada 10.000 km; la distribución es por cadena.", applies_to: null }],
  generations: [{ label: "E170", year_from: 2014, year_to: 2019, text: "Restyling en 2017." }],
};
const QUESTIONS = [
  { text: "¿Tiene los services hechos en concesionario?", why: "Historial" },
  { text: "¿La caja hace tirones en frío?", why: "" },
  { text: "¿Cambió alguna vez el líquido de la caja?", why: "" },
];
const ROW: PublicGuideRow = {
  id: 7, make: "Toyota", model: "Corolla", generation_label: null, year_from: 2014, year_to: 2019,
  slug_make: "toyota", slug_model: "corolla", body: BODY, questions: QUESTIONS,
  sources: [{ title: "Manual del usuario", url: "https://example.test/manual", kind: "manual", verified: true }],
  published_at: "2026-11-05T12:00:00Z", content_updated_at: "2026-11-05T12:00:00Z",
};

/** A PostgREST builder whose every call chains and that resolves to `result`. */
function client(result: { data: unknown; error: unknown }) {
  const calls: unknown[][] = [];
  const builder: Record<string, unknown> = {};
  for (const m of ["from", "select", "eq", "order"]) builder[m] = (...args: unknown[]) => { calls.push([m, ...args]); return builder; };
  builder.then = (resolve: (v: unknown) => unknown) => Promise.resolve(result).then(resolve);
  return { client: builder as never, calls };
}

const params = (marca: string, modelo: string) => ({ params: Promise.resolve({ marca, modelo }), searchParams: Promise.resolve({}) });

describe("slugs", () => {
  it("lowercases, drops accents and joins with dashes", () => {
    expect(slugify("Volkswagen")).toBe("volkswagen");
    expect(slugify("Gol Trend")).toBe("gol-trend");
    expect(slugify("Citroën C4 Picasso")).toBe("citroen-c4-picasso");
    expect(slugify("  Mercedes-Benz  Clase A ")).toBe("mercedes-benz-clase-a");
    expect(isSlug("gol-trend")).toBe(true);
    expect(isSlug("Gol Trend")).toBe(false);
    expect(isSlug("../etc")).toBe(false);
  });
});

describe("shape (zod)", () => {
  it("accepts a complete guide and reads a stored body leniently", () => {
    const parsed = GuideValuesInput.safeParse({ make: "Toyota", model: "Corolla", generation_label: "", year_from: 2014, year_to: 2019, body: BODY, questions: QUESTIONS, sources: ROW.sources });
    expect(parsed.success).toBe(true);
    expect(parsed.data?.generation_label).toBeNull();
    expect(readBody({ known_issues: [{ text: "x" }, { nope: 1 }], other: [] }).known_issues).toEqual([{ text: "x", applies_to: null }]);
    expect(readBody(null)).toEqual(emptyBody());
  });

  it("refuses questions without «?» or too short, years backwards and non-https sources", () => {
    const base = { make: "Toyota", model: "Corolla", generation_label: null, year_from: 2014, year_to: 2019, body: BODY, questions: QUESTIONS, sources: [] };
    expect(GuideValuesInput.safeParse({ ...base, questions: [{ text: "¿Corta?", why: "" }] }).success).toBe(false);
    expect(GuideValuesInput.safeParse({ ...base, questions: [{ text: "Tiene los services hechos.", why: "" }] }).success).toBe(false);
    expect(GuideValuesInput.safeParse({ ...base, year_from: 2019, year_to: 2014 }).success).toBe(false);
    expect(GuideValuesInput.safeParse({ ...base, sources: [{ title: "x", url: "http://example.test", kind: "otra", verified: true }] }).success).toBe(false);
  });

  it("publishing needs the five sections, 3 to 8 questions and at least one source, every one checked", () => {
    const checked = ROW.sources as never;
    expect(publishProblem({ body: BODY, questions: QUESTIONS, sources: checked })).toBeNull();
    // No source is not «every source checked».
    expect(publishProblem({ body: BODY, questions: QUESTIONS, sources: [] })).toContain("al menos una fuente");
    expect(publishProblem({ body: { ...BODY, generations: [] }, questions: QUESTIONS, sources: checked })).toContain("Generaciones");
    expect(publishProblem({ body: BODY, questions: QUESTIONS.slice(0, 2), sources: checked })).toContain("de 3 a 8");
    expect(publishProblem({ body: BODY, questions: QUESTIONS, sources: [{ title: "x", url: "https://x.test", kind: "otra", verified: false }] })).toContain("La revisé");
  });
});

describe("copy lint", () => {
  it("catches promises, «vale» and amounts of money, saying where", () => {
    expect(copyProblem("Motor garantizado por años.")).toBe("garantiz");
    expect(copyProblem("Vale la pena revisarlo.")).toBeNull();
    expect(copyProblem("No vale lo que piden.")).toBe("vale");
    expect(copyProblem("Verificado por Ese Auto")).toBe("verificado por ese auto");
    expect(hasMoney("El service sale USD 1.500")).toBe(true);
    expect(hasMoney("unos $ 300.000")).toBe(true);
    expect(hasMoney("300 mil pesos")).toBe(true);
    expect(hasMoney("Services cada 10.000 km")).toBe(false);
    const issues = lintGuide({ body: { ...BODY, maintenance_costs: [{ text: "El kit de distribución cuesta USD 400.", applies_to: null }] }, questions: [{ text: "¿Está certificado el kilometraje?", why: "" }], sources: [] });
    expect(issues).toEqual([
      { where: "Mantenimiento y costos típicos, renglón 1", message: "tiene una cifra de dinero" },
      { where: "Pregunta 1", message: "usa «certificad», que el copy no permite" },
    ]);
  });

  it("the fixed copy of the pages and the admin is clean", () => {
    for (const text of Object.values(GUIDE_COPY)) expect(copyProblem(text), text).toBeNull();
    expect(GUIDE_COPY.notice).toContain("Guía orientativa");
    expect(GUIDE_COPY.notice).toContain("mecánico");
    const root = path.resolve(__dirname, "..");
    const files = (dir: string): string[] => readdirSync(dir).flatMap((name) => {
      const full = path.join(dir, name);
      return statSync(full).isDirectory() ? files(full) : /\.tsx?$/.test(name) && !name.endsWith(".test.ts") ? [full] : [];
    });
    const sources = [
      ...files(path.join(root, "app", "guias")), ...files(path.join(root, "components", "guides")), ...files(path.join(root, "app", "admin", "guides")),
      path.join(root, "components", "admin", "guide-editor.tsx"), path.join(root, "components", "admin", "guide-buttons.tsx"),
    ];
    const offenders = sources.flatMap((file) => {
      const text = readFileSync(file, "utf-8");
      const term = copyProblem(text);
      return term ? [`${path.relative(root, file)}: ${term}`] : [];
    });
    expect(offenders).toEqual([]);
  });
});

describe("FAQ JSON-LD", () => {
  it("is built from the sections, deterministically, and escapes «<»", () => {
    const guide = toPublicGuide({ ...ROW, body: { ...BODY, known_issues: [{ text: "Ruido </script><b>x</b>", applies_to: null }] } });
    const faq = faqJsonLd([guide], "https://eseauto.com.ar/guias/toyota/corolla")!;
    expect(faq["@type"]).toBe("FAQPage");
    const entries = faq.mainEntity as { name: string; acceptedAnswer: { text: string } }[];
    expect(entries.map((e) => e.name)).toEqual([
      "¿Qué fallas conocidas tiene el Toyota Corolla?",
      "¿Qué revisar al ver un Toyota Corolla usado?",
      "¿Qué preguntarle al vendedor de un Toyota Corolla?",
    ]);
    expect(entries[0].acceptedAnswer.text.startsWith("Guía orientativa.")).toBe(true);
    const script = jsonLdScript(faq);
    expect(script).not.toContain("<");
    expect(JSON.parse(script)).toEqual(faq);
  });

  it("Article: headline, dates of publishing and content, the site as author and the car with its years", () => {
    const guide = toPublicGuide({ ...ROW, published_at: "2026-11-01T12:00:00Z", content_updated_at: "2026-11-05T12:00:00Z" });
    const later = toPublicGuide({ ...ROW, id: 9, year_from: 2020, year_to: 2024, published_at: "2026-11-10T12:00:00Z", content_updated_at: "2026-11-20T12:00:00Z" });
    const ld = articleJsonLd([guide, later], "https://eseauto.com.ar")!;
    expect(ld).toMatchObject({
      "@context": "https://schema.org",
      "@type": "Article",
      headline: "Toyota Corolla usado: guía orientativa para revisarlo",
      url: "https://eseauto.com.ar/guias/toyota/corolla",
      inLanguage: "es-AR",
      datePublished: "2026-11-01T12:00:00Z",
      dateModified: "2026-11-20T12:00:00Z",
      author: { "@type": "Organization", name: "Ese Auto", url: "https://eseauto.com.ar/" },
      publisher: { "@type": "Organization", name: "Ese Auto" },
      about: { "@type": "Car", name: "Toyota Corolla 2014 a 2024", brand: { "@type": "Brand", name: "Toyota" }, model: "Corolla" },
    });
    // A span of years is not a schema.org Date: it goes in the name, never in vehicleModelDate.
    expect(ld.about).not.toHaveProperty("vehicleModelDate");
    expect(String(ld.description)).toContain("2014 a 2024");
    // Without published_at (never published) there is no datePublished; without years no vehicleModelDate.
    const bare = articleJsonLd([toPublicGuide({ ...ROW, published_at: null, year_from: null, year_to: null })], "https://x.test")!;
    expect(bare).not.toHaveProperty("datePublished");
    expect(bare.about).not.toHaveProperty("vehicleModelDate");
    expect(articleJsonLd([], "https://x.test")).toBeNull();
    const about = (from: number | null, to: number | null) =>
      articleJsonLd([toPublicGuide({ ...ROW, year_from: from, year_to: to })], "https://x.test")!.about as Record<string, unknown>;
    expect(about(2020, 2020)).toMatchObject({ name: "Toyota Corolla 2020", vehicleModelDate: "2020" });
    expect(about(2020, null)).toMatchObject({ name: "Toyota Corolla desde 2020" });
    expect(about(2020, null)).not.toHaveProperty("vehicleModelDate");
    expect(about(null, 2019)).toMatchObject({ name: "Toyota Corolla hasta 2019" });
    expect(about(null, 2019)).not.toHaveProperty("vehicleModelDate");
    expect(about(null, null).name).toBe("Toyota Corolla");
  });

  it("dateModified is never before datePublished (publishing moves published_at, not content_updated_at)", () => {
    // Written on 05/11, first published on 20/11: modified is the publishing date.
    const fresh = toPublicGuide({ ...ROW, published_at: "2026-11-20T12:00:00+00:00", content_updated_at: "2026-11-05T12:00:00+00:00" });
    expect(guideDates([fresh])).toEqual({ published: "2026-11-20T12:00:00+00:00", modified: "2026-11-20T12:00:00+00:00" });
    const ld = articleJsonLd([fresh], "https://x.test")!;
    expect(Date.parse(String(ld.dateModified))).toBeGreaterThanOrEqual(Date.parse(String(ld.datePublished)));
    // Edited after publishing: the content's date.
    const edited = toPublicGuide({ ...ROW, published_at: "2026-11-01T12:00:00Z", content_updated_at: "2026-11-05T12:00:00Z" });
    expect(guideDates([edited])).toEqual({ published: "2026-11-01T12:00:00Z", modified: "2026-11-05T12:00:00Z" });
    // Compared as times, not as strings with different offsets.
    const offsets = toPublicGuide({ ...ROW, published_at: "2026-11-05T10:00:00-03:00", content_updated_at: "2026-11-05T12:30:00Z" });
    expect(guideDates([offsets]).modified).toBe("2026-11-05T10:00:00-03:00");
    expect(guideDates([toPublicGuide({ ...ROW, published_at: null })])).toEqual({ published: null, modified: ROW.content_updated_at });
  });

  it("BreadcrumbList: Inicio › Guías › the model, with positions", () => {
    const ld = guideBreadcrumb("Toyota", "Corolla", "toyota", "corolla", "https://eseauto.com.ar");
    expect(ld["@type"]).toBe("BreadcrumbList");
    expect(ld.itemListElement).toEqual([
      { "@type": "ListItem", position: 1, name: "Inicio", item: "https://eseauto.com.ar/" },
      { "@type": "ListItem", position: 2, name: GUIDE_COPY.indexTitle, item: "https://eseauto.com.ar/guias" },
      { "@type": "ListItem", position: 3, name: "Toyota Corolla", item: "https://eseauto.com.ar/guias/toyota/corolla" },
    ]);
    expect(breadcrumbJsonLd([]).itemListElement).toEqual([]);
  });

  it("CollectionPage of /guias lists every model in an ItemList, and «<» is escaped", () => {
    const ld = guideIndexJsonLd([
      { make: "Toyota", model: "Corolla", slugMake: "toyota", slugModel: "corolla" },
      { make: "Ford", model: "Ka <b>", slugMake: "ford", slugModel: "ka" },
    ], "https://eseauto.com.ar");
    expect(ld).toMatchObject({ "@type": "CollectionPage", url: "https://eseauto.com.ar/guias", inLanguage: "es-AR" });
    expect(ld.mainEntity).toEqual({
      "@type": "ItemList",
      numberOfItems: 2,
      itemListElement: [
        { "@type": "ListItem", position: 1, name: "Toyota Corolla", url: "https://eseauto.com.ar/guias/toyota/corolla" },
        { "@type": "ListItem", position: 2, name: "Ford Ka <b>", url: "https://eseauto.com.ar/guias/ford/ka" },
      ],
    });
    expect(jsonLdScript(ld)).not.toContain("<");
  });

  it("«En resumen» quotes the first known issue and the first thing to check, with the notice's caveat", () => {
    const summary = guideSummary([toPublicGuide(ROW)])!;
    expect(summary).toBe(
      "Una falla conocida del Toyota Corolla (2014 a 2019): Caja automática: tirones entre primera y segunda (Aplica a: 1.8 CVT, 2014–2016). " +
      "En la visita, revisá primero esto: Probar la caja en frío y en subida. " +
      "Es información general del modelo: no reemplaza la revisión de un mecánico de confianza.",
    );
    expect(copyProblem(summary)).toBeNull();
    expect(hasMoney(summary)).toBe(false);
    const noYears = guideSummary([toPublicGuide({ ...ROW, year_from: null, year_to: null, body: { ...BODY, known_issues: [] } })])!;
    expect(noYears.startsWith("En la visita, revisá primero esto: Probar la caja")).toBe(true);
    expect(guideSummary([toPublicGuide({ ...ROW, body: { ...BODY, known_issues: [], visit_checklist: [] } })])).toBeNull();
    expect(guideSummary([])).toBeNull();
  });

  it("«En resumen» with several generations labels each line with its own guide, not the page's years", () => {
    // The whole model has no known issues; E170 has the first one; E210 is later.
    const whole = toPublicGuide({ ...ROW, id: 1, generation_label: null, year_from: null, year_to: null,
      body: { ...BODY, known_issues: [], visit_checklist: [{ text: "Mirar el historial de services.", applies_to: "todas las versiones" }] } });
    const e170 = toPublicGuide({ ...ROW, id: 2, generation_label: "E170", year_from: 2014, year_to: 2019 });
    const e210 = toPublicGuide({ ...ROW, id: 3, generation_label: "E210", year_from: 2020, year_to: null,
      body: { ...BODY, known_issues: [{ text: "Híbrido: revisar la batería.", applies_to: null }] } });
    const summary = guideSummary([whole, e170, e210])!;
    expect(summary).toBe(
      "Una falla conocida del Toyota Corolla (E170, 2014 a 2019): Caja automática: tirones entre primera y segunda (Aplica a: 1.8 CVT, 2014–2016). " +
      "En la visita, revisá primero esto: Mirar el historial de services (Aplica a: todas las versiones). " +
      "Es información general del modelo: no reemplaza la revisión de un mecánico de confianza.",
    );
    expect(summary).not.toContain("2014 a 2020");
    // Only E210 has an issue: its own label and open range.
    const only = guideSummary([toPublicGuide({ ...ROW, body: { ...BODY, known_issues: [] } }), e210])!;
    expect(only.startsWith("Una falla conocida del Toyota Corolla (E210, desde 2020): Híbrido: revisar la batería.")).toBe(true);
  });

  it("the CTA's text names the model and the years", () => {
    expect(ctaPrompt("Toyota", "Corolla", 2014, 2019)).toBe("Busco un Toyota Corolla 2014 a 2019");
    expect(ctaPrompt("Ford", "Ka")).toBe("Busco un Ford Ka");
    // Accents and spaces stay as the catalog spells them; only the slug folds them.
    expect(ctaPrompt("Citroën", "C4 Lounge", 2013, 2022)).toBe("Busco un Citroën C4 Lounge 2013 a 2022");
    expect(ctaPrompt("Peugeot", "208", 2020, 2020)).toBe("Busco un Peugeot 208 2020");
    expect(ctaPrompt("Renault", "Sandero Stepway", 2015)).toBe("Busco un Renault Sandero Stepway desde 2015");
    expect(ctaPrompt("Fiat", "Palio", null, 2017)).toBe("Busco un Fiat Palio hasta 2017");
    expect(slugify("Citroën") + "/" + slugify("C4 Lounge")).toBe("citroen/c4-lounge");
  });
});

describe("/guias/<marca>/<modelo>", () => {
  beforeEach(() => vi.clearAllMocks());

  it("is ISR with nothing built at deploy time", async () => {
    expect(revalidate).toBe(3600);
    expect(await generateStaticParams()).toEqual([]);
  });

  it("is a 404 for an unknown model, a model with only drafts (RLS: none read) and a base without the table", async () => {
    vi.mocked(createPublicClient).mockReturnValue(client({ data: [], error: null }).client);
    await expect(GuidePage(params("toyota", "nada"))).rejects.toThrow("NEXT_NOT_FOUND");
    vi.mocked(createPublicClient).mockReturnValue(client({ data: null, error: { code: "PGRST205", message: "Could not find the table 'public.model_guides'" } }).client);
    await expect(GuidePage(params("toyota", "corolla"))).rejects.toThrow("NEXT_NOT_FOUND");
    vi.mocked(createPublicClient).mockReturnValue(client({ data: null, error: { code: "42P01", message: "relation \"model_guides\" does not exist" } }).client);
    await expect(GuidePage(params("toyota", "corolla"))).rejects.toThrow("NEXT_NOT_FOUND");
  });

  it("does not even ask for a slug out of pattern", async () => {
    await expect(GuidePage(params("Toyota", "corolla"))).rejects.toThrow("NEXT_NOT_FOUND");
    expect(createPublicClient).not.toHaveBeenCalled();
  });

  it("asks anon only for the public columns of the model", async () => {
    const { client: c, calls } = client({ data: [ROW], error: null });
    vi.mocked(createPublicClient).mockReturnValue(c);
    await GuidePage(params("toyota", "corolla"));
    const select = calls.find((call) => call[0] === "select")![1] as string;
    for (const internal of ["reviewed_by", "llm_version", "llm_job_id", "origin", "status", "*"]) expect(select).not.toContain(internal);
    expect(calls).toContainEqual(["eq", "slug_make", "toyota"]);
  });

  it("renders the notice, the sections, the questions, the FAQ and the prefilled CTA, without prices or internal fields", async () => {
    vi.mocked(createPublicClient).mockReturnValue(client({ data: [ROW], error: null }).client);
    const html = renderToStaticMarkup(await GuidePage(params("toyota", "corolla")));
    expect(html).toContain(GUIDE_COPY.notice);
    expect(html).toContain("Toyota Corolla usado: guía orientativa para revisarlo");
    for (const name of ["Fallas conocidas", "Qué revisar en la visita", "Versiones y equipamiento", "Mantenimiento y costos típicos", "Generaciones", "Preguntas para hacerle al vendedor"]) {
      expect(html).toContain(name);
    }
    expect(html).toContain("¿La caja hace tirones en frío?");
    expect(html).toContain('type="application/ld+json"');
    expect(html).toContain('data-prompt="Busco un Toyota Corolla 2014 a 2019"');
    expect(html).toContain("Última actualización: 5 de noviembre de 2026");
    for (const forbidden of ["USD", "$", "reviewed_by", "llm_version", "llm_job", "borrador", "IA", "gpt", "openai"]) {
      expect(html, forbidden).not.toContain(forbidden);
    }
  });

  it("puts «En resumen» and a «Crear mi búsqueda» link before the sections, and the FAQ, Article and breadcrumb JSON-LD", async () => {
    vi.mocked(createPublicClient).mockReturnValue(client({ data: [ROW], error: null }).client);
    const html = renderToStaticMarkup(await GuidePage(params("toyota", "corolla")));
    const summary = html.indexOf('data-testid="guide-summary"');
    const top = html.indexOf('data-testid="guide-cta-top"');
    const sections = html.indexOf("Fallas conocidas</h2>");
    expect(summary).toBeGreaterThan(-1);
    expect(summary).toBeLessThan(sections);
    expect(top).toBeLessThan(sections);
    expect(html).toMatch(/<a href="#crear-busqueda"[^>]*>Crear mi búsqueda<\/a>/);
    expect(html).toContain('id="crear-busqueda"');
    const scripts = [...html.matchAll(/<script type="application\/ld\+json">(.*?)<\/script>/g)].map((m) => JSON.parse(m[1]) as { "@type": string });
    expect(scripts.map((ld) => ld["@type"])).toEqual(["FAQPage", "Article", "BreadcrumbList"]);
    expect(scripts[1]).toMatchObject({ datePublished: ROW.published_at, dateModified: ROW.content_updated_at });
  });

  it("asks for content_updated_at, never updated_at", async () => {
    const { client: c, calls } = client({ data: [ROW], error: null });
    vi.mocked(createPublicClient).mockReturnValue(c);
    await GuidePage(params("toyota", "corolla"));
    const select = calls.find((call) => call[0] === "select")![1] as string;
    expect(select.split(", ")).toContain("content_updated_at");
    expect(select.split(", ")).not.toContain("updated_at");
  });

  it("an unchecked source never reaches the page", async () => {
    vi.mocked(createPublicClient).mockReturnValue(client({ data: [{ ...ROW, sources: [{ title: "Foro dudoso", url: "https://foro.test", kind: "foro", verified: false }] }], error: null }).client);
    const html = renderToStaticMarkup(await GuidePage(params("toyota", "corolla")));
    expect(html).not.toContain("Foro dudoso");
  });

  it("has a title, a description and the canonical URL", async () => {
    vi.mocked(createPublicClient).mockReturnValue(client({ data: [ROW], error: null }).client);
    const meta = await generateMetadata(params("toyota", "corolla"));
    expect(meta.title).toBe("Toyota Corolla usado: guía orientativa para revisarlo");
    expect(meta.alternates?.canonical).toBe("/guias/toyota/corolla");
    expect(meta.openGraph).toMatchObject({ type: "article", url: "/guias/toyota/corolla", modifiedTime: ROW.content_updated_at, publishedTime: ROW.published_at });
    expect(String(meta.description)).toContain("2014 a 2019");
  });

  it("«Última actualización» is the content's date, not the last publish", async () => {
    // Republished on 20/12 without touching the text of 05/11: updated_at is not even read.
    vi.mocked(createPublicClient).mockReturnValue(client({ data: [{ ...ROW, updated_at: "2026-12-20T12:00:00Z" }], error: null }).client);
    const html = renderToStaticMarkup(await GuidePage(params("toyota", "corolla")));
    expect(html).toContain("Última actualización: 5 de noviembre de 2026");
    expect(html).not.toContain("diciembre");
  });

  it("a database error is not a 404 (ISR keeps the page it had)", async () => {
    vi.mocked(createPublicClient).mockReturnValue(client({ data: null, error: { code: "57014", message: "timeout" } }).client);
    await expect(GuidePage(params("toyota", "corolla"))).rejects.toThrow("model_guides: timeout");
  });
});

describe("/guias and the sitemap", () => {
  beforeEach(() => vi.clearAllMocks());

  it("the index lists the published models by make, and says so when there are none", async () => {
    vi.mocked(createPublicClient).mockReturnValue(client({ data: [{ make: "Toyota", model: "Corolla", slug_make: "toyota", slug_model: "corolla", content_updated_at: ROW.content_updated_at }], error: null }).client);
    const html = renderToStaticMarkup(await GuidesIndex());
    expect(html).toContain('href="/guias/toyota/corolla"');
    const ld = JSON.parse(/<script type="application\/ld\+json">(.*?)<\/script>/.exec(html)![1]) as { "@type": string; mainEntity: { itemListElement: { url: string }[] } };
    expect(ld["@type"]).toBe("CollectionPage");
    expect(ld.mainEntity.itemListElement.map((i) => i.url)).toEqual([expect.stringMatching(/\/guias\/toyota\/corolla$/)]);
    vi.mocked(createPublicClient).mockReturnValue(client({ data: null, error: { code: "PGRST205", message: "x" } }).client);
    expect(renderToStaticMarkup(await GuidesIndex())).toContain(GUIDE_COPY.indexEmpty);
  });

  it("the sitemap adds /guias and each published model; without the table or on an error it keeps the static entries", async () => {
    vi.mocked(createPublicClient).mockReturnValue(client({ data: [{ make: "Toyota", model: "Corolla", slug_make: "toyota", slug_model: "corolla", content_updated_at: ROW.content_updated_at }], error: null }).client);
    const urls = (await sitemap()).map((e) => e.url);
    expect(urls.some((u) => u.endsWith("/guias"))).toBe(true);
    expect(urls.some((u) => u.endsWith("/guias/toyota/corolla"))).toBe(true);
    vi.mocked(createPublicClient).mockReturnValue(client({ data: null, error: { code: "PGRST205", message: "x" } }).client);
    const noTable = (await sitemap()).map((e) => e.url);
    expect(noTable.some((u) => u.endsWith("/guias"))).toBe(true);
    expect(noTable.some((u) => u.includes("/guias/"))).toBe(false);
    vi.mocked(createPublicClient).mockReturnValue(client({ data: null, error: { code: "57014", message: "timeout" } }).client);
    const failed = (await sitemap()).map((e) => e.url);
    expect(failed.some((u) => u.endsWith("/planes"))).toBe(true);
    expect(failed.some((u) => u.includes("/guias"))).toBe(false);
  });
});

describe("a model with several generations", () => {
  beforeEach(() => vi.clearAllMocks());

  // Whole model (no label, no years), E170 and E210, read out of order.
  const E210: PublicGuideRow = {
    ...ROW, id: 9, generation_label: "E210", year_from: 2020, year_to: 2024,
    body: { ...BODY, known_issues: [{ text: "Híbrido: revisar el estado de la batería.", applies_to: null }] },
    // The same question as the E170 one, spelled otherwise: copied once.
    questions: [{ text: "¿La caja hace tirones en FRÍO?", why: "" }, { text: "¿Le cambiaron la batería híbrida?", why: "" }, { text: "¿Tiene la garantía de fábrica vigente?", why: "" }],
    sources: [{ title: "Ficha E210", url: "https://example.test/e210", kind: "ficha técnica", verified: true }],
    content_updated_at: "2026-11-20T12:00:00Z",
  };
  const E170: PublicGuideRow = { ...ROW, id: 8, generation_label: "E170", year_from: 2014, year_to: 2019 };
  const WHOLE: PublicGuideRow = {
    ...ROW, id: 7, generation_label: null, year_from: null, year_to: null,
    questions: [{ text: "¿Cuántos dueños tuvo el auto?", why: "" }, ...QUESTIONS.slice(0, 2)],
  };
  const rows = [E210, E170, WHOLE];

  it("sorts the whole model first, then by year, and spans every year", () => {
    const guides = sortGenerations(rows.map(toPublicGuide));
    expect(guides.map((g) => g.id)).toEqual([7, 8, 9]);
    expect(modelYears(guides)).toEqual({ from: 2014, to: 2024 });
    expect(modelYears([toPublicGuide(WHOLE)])).toEqual({ from: null, to: null });
    expect(guides.map(generationAnchor)).toEqual(["guia", "generacion-e170", "generacion-e210"]);
    expect(generationAnchor(toPublicGuide({ ...ROW, generation_label: "Mk 7 (restyling)" }))).toBe("generacion-mk-7-restyling");
  });

  it("copies each question once across the generations, in page order", () => {
    const text = questionsText(sortGenerations(rows.map(toPublicGuide)));
    expect(text.split("\n")).toEqual([
      "¿Cuántos dueños tuvo el auto?",
      "¿Tiene los services hechos en concesionario?",
      "¿La caja hace tirones en frío?",
      "¿Cambió alguna vez el líquido de la caja?",
      "¿Le cambiaron la batería híbrida?",
      "¿Tiene la garantía de fábrica vigente?",
    ]);
  });

  it("renders a nav to each generation, one h2 per generation with h3 sections, and the CTA with every year", async () => {
    vi.mocked(createPublicClient).mockReturnValue(client({ data: rows, error: null }).client);
    const html = renderToStaticMarkup(await GuidePage(params("toyota", "corolla")));
    expect(html).toContain('aria-label="Generaciones"');
    for (const anchor of ["guia", "generacion-e170", "generacion-e210"]) {
      expect(html).toContain(`href="#${anchor}"`);
      expect(html).toContain(`id="${anchor}"`);
    }
    expect(html.indexOf('id="guia"')).toBeLessThan(html.indexOf('id="generacion-e170"'));
    expect(html.indexOf('id="generacion-e170"')).toBeLessThan(html.indexOf('id="generacion-e210"'));
    expect(html).toMatch(/<h2[^>]*>Todo el modelo/);
    expect(html).toMatch(/<h2[^>]*>E210 <span[^>]*>2020 a 2024<\/span><\/h2>/);
    expect(html).toMatch(/<h3 id="generacion-e210-known_issues"[^>]*>Fallas conocidas<\/h3>/);
    expect(html).not.toMatch(/<h2 id="[^"]*-known_issues"/);
    const list = /<ol[^>]*data-testid="guide-questions"[^>]*>(.*?)<\/ol>/.exec(html)![1];
    expect(list.match(/<li>/g)).toHaveLength(6);
    expect(list.match(/tirones en frío/gi)).toHaveLength(1);
    expect(html).toContain('data-prompt="Busco un Toyota Corolla 2014 a 2024"');
    expect(html).toContain("Ficha E210");
    // The newest content of the page.
    expect(html).toContain("Última actualización: 20 de noviembre de 2026");
    const ld = JSON.parse(/<script type="application\/ld\+json">(.*?)<\/script>/.exec(html)![1]) as { mainEntity: { name: string; acceptedAnswer: { text: string } }[] };
    expect(ld.mainEntity[0].acceptedAnswer.text).toContain("Híbrido: revisar el estado de la batería.");
    expect(ld.mainEntity[0].acceptedAnswer.text).toContain("Caja automática: tirones");
    expect(ld.mainEntity[2].acceptedAnswer.text.match(/tirones/gi)).toHaveLength(1);
    const meta = await generateMetadata(params("toyota", "corolla"));
    expect(String(meta.description)).toContain("2014 a 2024");
  });

  it("one guide without a label is the whole page, without the generations nav", async () => {
    vi.mocked(createPublicClient).mockReturnValue(client({ data: [WHOLE], error: null }).client);
    const html = renderToStaticMarkup(await GuidePage(params("toyota", "corolla")));
    expect(html).not.toContain('aria-label="Generaciones"');
    expect(html).toMatch(/<h2 id="guia-known_issues"[^>]*>Fallas conocidas<\/h2>/);
    expect(html).toContain('data-prompt="Busco un Toyota Corolla"');
  });
});

describe("robots", () => {
  it("allows /guias to every crawler and names the AI crawlers, keeping the private areas out for all", () => {
    const { rules, sitemap: map } = robots();
    const list = Array.isArray(rules) ? rules : [rules];
    const agents = list.flatMap((r) => (Array.isArray(r.userAgent) ? r.userAgent : [r.userAgent]));
    for (const bot of ["*", "GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot", "Claude-SearchBot", "Claude-User", "PerplexityBot", "Perplexity-User", "Google-Extended", "Applebot-Extended", "CCBot", "Bingbot"]) {
      expect(agents, bot).toContain(bot);
    }
    for (const rule of list) {
      expect(rule.allow).toEqual(expect.arrayContaining(["/guias", "/llms.txt"]));
      expect(rule.disallow).toEqual(expect.arrayContaining(["/app", "/admin", "/api/", "/auth/", "/r/", "/m/", "/baja"]));
      expect(rule.disallow).not.toContain("/guias");
    }
    expect(map).toMatch(/\/sitemap\.xml$/);
  });
});

describe("/guias metadata", () => {
  it("has its own Open Graph title, description and URL (not the landing's)", () => {
    expect(indexMetadata.title).toBe(GUIDE_COPY.indexTitle);
    expect(indexMetadata.openGraph).toMatchObject({ title: GUIDE_COPY.indexTitle, description: GUIDE_COPY.indexIntro, url: "/guias", locale: "es_AR" });
  });

  it("the sitemap's lastModified is the content's date", async () => {
    vi.mocked(createPublicClient).mockReturnValue(client({ data: [
      { make: "Toyota", model: "Corolla", slug_make: "toyota", slug_model: "corolla", content_updated_at: "2026-11-05T12:00:00Z", updated_at: "2026-12-20T12:00:00Z" },
      { make: "Toyota", model: "Corolla", slug_make: "toyota", slug_model: "corolla", content_updated_at: "2026-11-07T12:00:00Z", updated_at: "2026-11-07T12:00:00Z" },
    ], error: null }).client);
    const entry = (await sitemap()).find((e) => e.url.endsWith("/guias/toyota/corolla"));
    expect(entry?.lastModified).toBe("2026-11-07T12:00:00Z");
  });
});
