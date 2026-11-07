import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));
vi.mock("@/lib/supabase/public", () => ({ createPublicClient: vi.fn() }));
vi.mock("next/navigation", async (original) => ({
  ...(await original<typeof import("next/navigation")>()),
  notFound: vi.fn(() => {
    throw new Error("NEXT_NOT_FOUND");
  }),
}));

import MakeGuides, { generateMetadata as makeMetadata } from "@/app/guias/[marca]/page";
import GuidesMethod, { metadata as methodMetadata } from "@/app/guias/como-las-hacemos/page";
import { GET as indexNowKeyFile } from "@/app/indexnow.txt/route";
import { copyProblem, faqJsonLd, makePath, METHOD_PATH, relatedGuides, sectionQuestion, toPublicGuide, type PublicGuideRow } from "@/lib/guides";
import { INDEXNOW_KEY, indexNowBody, indexNowEnabled } from "@/lib/indexnow";
import { llmsTxt } from "@/lib/llms";
import { HOME_FAQ, homeJsonLd } from "@/lib/site-jsonld";
import { createPublicClient } from "@/lib/supabase/public";

const BODY = {
  known_issues: [{ text: "Caja I-Motion: tirones en primera.", applies_to: null }],
  visit_checklist: [{ text: "Probar la caja en subida.", applies_to: null }],
  versions_equipment: [{ text: "Trendline y Highline.", applies_to: null }],
  maintenance_costs: [{ text: "Distribución por correa.", applies_to: null }],
  generations: [{ label: "Gol Trend", year_from: 2008, year_to: 2022, text: "Una generación con restyling." }],
};
const row = (over: Partial<PublicGuideRow>): PublicGuideRow => ({
  id: 1, make: "Volkswagen", model: "Gol Trend", generation_label: null, year_from: 2008, year_to: 2022,
  slug_make: "volkswagen", slug_model: "gol-trend", body: BODY,
  questions: [{ text: "¿Tiene los services al día?", why: "" }, { text: "¿La caja hace tirones?", why: "" }, { text: "¿Tiene GNC?", why: "" }],
  sources: [{ title: "Manual", url: "https://example.test/manual", kind: "manual", verified: true }],
  published_at: "2026-11-01T12:00:00Z", content_updated_at: "2026-11-04T12:00:00Z", ...over,
});

function client(result: { data: unknown; error: unknown }) {
  const calls: unknown[][] = [];
  const builder: Record<string, unknown> = {};
  for (const m of ["from", "select", "eq", "order"]) builder[m] = (...args: unknown[]) => { calls.push([m, ...args]); return builder; };
  builder.then = (resolve: (v: unknown) => unknown) => Promise.resolve(result).then(resolve);
  return { client: builder as never, calls };
}
const params = (marca: string) => ({ params: Promise.resolve({ marca }), searchParams: Promise.resolve({}) });
const lds = (html: string) => [...html.matchAll(/<script type="application\/ld\+json">(.*?)<\/script>/g)].map((m) => JSON.parse(m[1]) as Record<string, unknown>);

describe("/guias/<marca>", () => {
  beforeEach(() => vi.clearAllMocks());

  it("lists the make's models with their years and first known issue, a CollectionPage and the breadcrumb", async () => {
    const { client: c, calls } = client({ data: [row({}), row({ id: 2, model: "Polo", slug_model: "polo", year_from: 2018, year_to: 2024, content_updated_at: "2026-11-06T12:00:00Z" })], error: null });
    vi.mocked(createPublicClient).mockReturnValue(c);
    const html = renderToStaticMarkup(await MakeGuides(params("volkswagen")));
    expect(calls).toContainEqual(["eq", "slug_make", "volkswagen"]);
    expect(html).toContain("Guías de Volkswagen usados");
    expect(html).toContain('href="/guias/volkswagen/gol-trend"');
    expect(html).toContain('href="/guias/volkswagen/polo"');
    expect(html).toContain("2008 a 2022");
    expect(html).toContain("Falla conocida: Caja I-Motion: tirones en primera.");
    // The newest content of the make, as a machine-readable date.
    expect(html).toContain('<time dateTime="2026-11-06T12:00:00Z">6 de noviembre de 2026</time>');
    expect(html).toContain(`href="${METHOD_PATH}"`);
    const types = lds(html).map((ld) => ld["@type"]);
    expect(types).toEqual(["CollectionPage", "BreadcrumbList"]);
    const meta = await makeMetadata(params("volkswagen"));
    expect(meta.alternates?.canonical).toBe("/guias/volkswagen");
    expect(meta.title).toBe("Guías de Volkswagen usados");
  });

  it("is a 404 without published models, for a slug out of pattern (not even asked) and without the table", async () => {
    vi.mocked(createPublicClient).mockReturnValue(client({ data: [], error: null }).client);
    await expect(MakeGuides(params("nada"))).rejects.toThrow("NEXT_NOT_FOUND");
    vi.mocked(createPublicClient).mockReturnValue(client({ data: null, error: { code: "PGRST205", message: "x" } }).client);
    await expect(MakeGuides(params("volkswagen"))).rejects.toThrow("NEXT_NOT_FOUND");
    vi.mocked(createPublicClient).mockClear();
    await expect(MakeGuides(params("Volks Wagen"))).rejects.toThrow("NEXT_NOT_FOUND");
    expect(createPublicClient).not.toHaveBeenCalled();
    expect((await makeMetadata(params("Volks Wagen"))).robots).toEqual({ index: false });
  });
});

describe("«Otras guías»", () => {
  const e = (slugMake: string, slugModel: string) => ({ slugMake, slugModel });
  const index = [e("volkswagen", "gol-trend"), e("volkswagen", "polo"), e("volkswagen", "vento"), e("toyota", "corolla"), e("ford", "focus"), e("fiat", "argo"), e("renault", "clio"), e("peugeot", "208"), e("honda", "city")];

  it("the make's other models first, never the page itself, then a stable spread of the rest", () => {
    const related = relatedGuides(index, "volkswagen", "gol-trend");
    expect(related).toHaveLength(6);
    expect(related.slice(0, 2)).toEqual([e("volkswagen", "polo"), e("volkswagen", "vento")]);
    expect(related).not.toContainEqual(e("volkswagen", "gol-trend"));
    expect(relatedGuides(index, "volkswagen", "gol-trend")).toEqual(related);
    expect(relatedGuides([e("toyota", "corolla")], "toyota", "corolla")).toEqual([]);
  });

  it("spreads the links: different pages pick different others", () => {
    const picks = new Set(index.filter((x) => x.slugMake !== "volkswagen").map((x) => relatedGuides(index, x.slugMake, x.slugModel, 4).map((r) => r.slugModel).join()));
    expect(picks.size).toBeGreaterThan(1);
  });
});

describe("section questions", () => {
  it("are what the FAQ asks, for the model or one generation", () => {
    expect(sectionQuestion("known_issues", "Volkswagen Gol Trend")).toBe("¿Qué fallas conocidas tiene el Volkswagen Gol Trend?");
    expect(sectionQuestion("seller", "Toyota Corolla E170")).toBe("¿Qué preguntarle al vendedor de un Toyota Corolla E170?");
    const faq = faqJsonLd([toPublicGuide(row({}))], "https://x.test/guias/volkswagen/gol-trend")!;
    const names = (faq.mainEntity as { name: string }[]).map((q) => q.name);
    for (const key of ["known_issues", "visit_checklist", "versions_equipment", "maintenance_costs", "generations", "seller"] as const) {
      expect(names).toContain(sectionQuestion(key, "Volkswagen Gol Trend"));
    }
  });
});

describe("/guias/como-las-hacemos", () => {
  it("answers in questions, with its FAQPage, breadcrumb and canonical, in clean copy", () => {
    const html = renderToStaticMarkup(GuidesMethod());
    expect(html).toContain("¿De dónde sale la información?");
    expect(html).toContain("Actualizada el");
    const types = lds(html).map((ld) => ld["@type"]);
    expect(types).toEqual(["FAQPage", "BreadcrumbList"]);
    expect(methodMetadata.alternates?.canonical).toBe(METHOD_PATH);
    for (const word of ["IA", "LLM", "gpt", "borrador"]) expect(html).not.toContain(word);
  });
});

describe("the landing's structured data", () => {
  it("Organization, WebSite, Service and the FAQPage of the questions the landing shows", () => {
    const ld = homeJsonLd("https://www.eseauto.com.ar") as { "@graph": Record<string, unknown>[] };
    expect(ld["@graph"].map((n) => n["@type"])).toEqual(["Organization", "WebSite", "Service", "FAQPage"]);
    const faq = ld["@graph"][3] as { mainEntity: { name: string; acceptedAnswer: { text: string } }[] };
    expect(faq.mainEntity.map((q) => q.name)).toEqual(HOME_FAQ.map((q) => q.q));
    expect(faq.mainEntity.map((q) => q.acceptedAnswer.text)).toEqual(HOME_FAQ.map((q) => q.a));
  });

  it("names no price and promises nothing", () => {
    for (const { q, a } of HOME_FAQ) {
      expect(`${q} ${a}`).not.toMatch(/\$|USD|\d+\.\d{3}/);
      expect(copyProblem(a), a).toBeNull();
    }
  });
});

describe("llms.txt", () => {
  it("links each make's page and the method", () => {
    const text = llmsTxt([[toPublicGuide(row({}))]], "https://www.eseauto.com.ar");
    expect(text).toContain(`[Guías de Volkswagen usados](https://www.eseauto.com.ar${makePath("volkswagen")})`);
    expect(text).toContain(`https://www.eseauto.com.ar${METHOD_PATH}`);
  });
});

describe("IndexNow", () => {
  it("serves its key and builds a ping for the production site's pages", async () => {
    expect(await indexNowKeyFile().text()).toBe(INDEXNOW_KEY);
    expect(indexNowBody(["/guias/volkswagen/gol-trend", "/guias", "/guias"], "https://www.eseauto.com.ar")).toEqual({
      host: "www.eseauto.com.ar",
      key: INDEXNOW_KEY,
      keyLocation: "https://www.eseauto.com.ar/indexnow.txt",
      urlList: ["https://www.eseauto.com.ar/guias/volkswagen/gol-trend", "https://www.eseauto.com.ar/guias"],
    });
    expect(indexNowBody([], "https://www.eseauto.com.ar")).toBeNull();
  });

  it("pings only from production, never locally or from a preview", () => {
    expect(indexNowEnabled("production", "https://www.eseauto.com.ar")).toBe(true);
    expect(indexNowEnabled("preview", "https://www.eseauto.com.ar")).toBe(false);
    expect(indexNowEnabled(undefined, "https://www.eseauto.com.ar")).toBe(false);
    expect(indexNowEnabled("production", "http://127.0.0.1:3000")).toBe(false);
  });
});
