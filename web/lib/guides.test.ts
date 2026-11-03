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
import GuidesIndex from "@/app/guias/page";
import sitemap from "@/app/sitemap";
import { GUIDE_COPY } from "@/lib/guides";
import {
  copyProblem,
  ctaPrompt,
  emptyBody,
  faqJsonLd,
  GuideValuesInput,
  hasMoney,
  isSlug,
  jsonLdScript,
  lintGuide,
  publishProblem,
  readBody,
  slugify,
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
  published_at: "2026-11-05T12:00:00Z", updated_at: "2026-11-05T12:00:00Z",
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

  it("publishing needs the five sections, 3 to 8 questions and every source checked", () => {
    expect(publishProblem({ body: BODY, questions: QUESTIONS, sources: [] })).toBeNull();
    expect(publishProblem({ body: { ...BODY, generations: [] }, questions: QUESTIONS, sources: [] })).toContain("Generaciones");
    expect(publishProblem({ body: BODY, questions: QUESTIONS.slice(0, 2), sources: [] })).toContain("de 3 a 8");
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

  it("the CTA's text names the model and the years", () => {
    expect(ctaPrompt("Toyota", "Corolla", 2014, 2019)).toBe("Busco un Toyota Corolla 2014 a 2019");
    expect(ctaPrompt("Ford", "Ka")).toBe("Busco un Ford Ka");
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
    expect(String(meta.description)).toContain("2014 a 2019");
  });

  it("a database error is not a 404 (ISR keeps the page it had)", async () => {
    vi.mocked(createPublicClient).mockReturnValue(client({ data: null, error: { code: "57014", message: "timeout" } }).client);
    await expect(GuidePage(params("toyota", "corolla"))).rejects.toThrow("model_guides: timeout");
  });
});

describe("/guias and the sitemap", () => {
  beforeEach(() => vi.clearAllMocks());

  it("the index lists the published models by make, and says so when there are none", async () => {
    vi.mocked(createPublicClient).mockReturnValue(client({ data: [{ make: "Toyota", model: "Corolla", slug_make: "toyota", slug_model: "corolla", updated_at: ROW.updated_at }], error: null }).client);
    const html = renderToStaticMarkup(await GuidesIndex());
    expect(html).toContain('href="/guias/toyota/corolla"');
    vi.mocked(createPublicClient).mockReturnValue(client({ data: null, error: { code: "PGRST205", message: "x" } }).client);
    expect(renderToStaticMarkup(await GuidesIndex())).toContain(GUIDE_COPY.indexEmpty);
  });

  it("the sitemap adds /guias and each published model; without the table or on an error it keeps the static entries", async () => {
    vi.mocked(createPublicClient).mockReturnValue(client({ data: [{ make: "Toyota", model: "Corolla", slug_make: "toyota", slug_model: "corolla", updated_at: ROW.updated_at }], error: null }).client);
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
