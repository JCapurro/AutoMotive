import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));
vi.mock("@/lib/supabase/public", () => ({ createPublicClient: vi.fn() }));

import { GET as fullGet, revalidate as fullRevalidate } from "@/app/llms-full.txt/route";
import { GET, revalidate } from "@/app/llms.txt/route";
import { copyProblem, hasMoney, type PublicGuideRow, sortGenerations, toPublicGuide } from "@/lib/guides";
import { guideMarkdown, LLMS_COPY, llmsFullTxt, llmsTxt } from "@/lib/llms";
import { createPublicClient } from "@/lib/supabase/public";

const BODY = {
  known_issues: [{ text: "Caja automática: tirones entre primera y segunda.", applies_to: "1.8 CVT" }],
  visit_checklist: [{ text: "Probar la caja en frío\ny en subida.", applies_to: null }],
  versions_equipment: [{ text: "XLi, XEi y SEG.", applies_to: null }],
  maintenance_costs: [{ text: "Services cada 10.000 km.", applies_to: null }],
  generations: [{ label: "E170", year_from: 2014, year_to: 2019, text: "Restyling en 2017." }],
};
const ROW: PublicGuideRow = {
  id: 7, make: "Toyota", model: "Corolla", generation_label: null, year_from: 2014, year_to: 2019,
  slug_make: "toyota", slug_model: "corolla", body: BODY,
  questions: [{ text: "¿La caja hace tirones en frío?", why: "" }, { text: "¿Tiene los services hechos?", why: "" }],
  sources: [{ title: "Manual del usuario", url: "https://example.test/manual", kind: "manual", verified: true }],
  published_at: "2026-11-05T12:00:00Z", content_updated_at: "2026-11-05T12:00:00Z",
};
const FORD: PublicGuideRow = { ...ROW, id: 8, make: "Ford", model: "Ka", slug_make: "ford", slug_model: "ka", year_from: null, year_to: null };
const SITE = "https://eseauto.com.ar";

function client(result: { data: unknown; error: unknown }) {
  const calls: unknown[][] = [];
  const builder: Record<string, unknown> = {};
  for (const m of ["from", "select", "eq", "order"]) builder[m] = (...args: unknown[]) => { calls.push([m, ...args]); return builder; };
  builder.then = (resolve: (v: unknown) => unknown) => Promise.resolve(result).then(resolve);
  return { client: builder as never, calls };
}

describe("llms.txt builder", () => {
  it("describes the site, links /guias and each published model with a one-line summary", () => {
    const text = llmsTxt([[toPublicGuide(ROW)], [toPublicGuide(FORD)]], SITE);
    expect(text.startsWith("# Ese Auto (eseauto.com.ar)\n\n> ")).toBe(true);
    expect(text).toContain(LLMS_COPY.about);
    expect(text).toContain(`- [Guías orientativas por modelo](${SITE}/guias): `);
    expect(text).toContain(`- [Toyota Corolla usado: guía orientativa para revisarlo](${SITE}/guias/toyota/corolla): Fallas conocidas, qué revisar en la visita y qué preguntarle al vendedor de un Toyota Corolla 2014 a 2019 usado.`);
    expect(text).toContain(`(${SITE}/guias/ford/ka): `);
    expect(text).toContain(`(${SITE}/llms-full.txt)`);
    expect(text.endsWith("\n")).toBe(true);
  });

  it("without guides it still links /guias and says there are none", () => {
    const text = llmsTxt([], SITE);
    expect(text).toContain(`${SITE}/guias`);
    expect(text).toContain(LLMS_COPY.noGuides);
    expect(text).not.toContain("llms-full.txt");
  });

  it("its fixed copy is clean (no promises, no amounts of money)", () => {
    for (const value of Object.values(LLMS_COPY)) {
      expect(copyProblem(value), value).toBeNull();
      expect(hasMoney(value), value).toBe(false);
    }
  });
});

describe("llms-full.txt builder", () => {
  it("has the full text of each guide: notice, sections, questions and checked sources, one line per item", () => {
    const md = guideMarkdown([toPublicGuide(ROW)], SITE);
    expect(md).toContain("## Toyota Corolla usado: guía orientativa para revisarlo");
    expect(md).toContain(`URL: ${SITE}/guias/toyota/corolla`);
    expect(md).toContain("Última actualización: 2026-11-05");
    expect(md).toContain("Guía orientativa. Resume información general del modelo");
    expect(md).toContain("### Fallas conocidas\n\n- Caja automática: tirones entre primera y segunda. (Aplica a: 1.8 CVT)");
    expect(md).toContain("- Probar la caja en frío y en subida.");
    expect(md).toContain("- E170 (2014 a 2019): Restyling en 2017.");
    expect(md).toContain("### Preguntas para hacerle al vendedor\n\n1. ¿La caja hace tirones en frío?\n2. ¿Tiene los services hechos?");
    expect(md).toContain("- [Manual del usuario](https://example.test/manual) (manual)");
  });

  it("several generations get a heading each, sections one level below", () => {
    const e210 = toPublicGuide({ ...ROW, id: 9, generation_label: "E210", year_from: 2020, year_to: 2024 });
    const md = guideMarkdown(sortGenerations([e210, toPublicGuide({ ...ROW, generation_label: "E170" })]), SITE);
    expect(md.indexOf("### E170 (2014 a 2019)")).toBeLessThan(md.indexOf("### E210 (2020 a 2024)"));
    expect(md).toContain("#### Fallas conocidas");
  });

  it("joins every model under the site's header", () => {
    const text = llmsFullTxt([[toPublicGuide(ROW)], [toPublicGuide(FORD)]], SITE);
    expect(text.startsWith("# Ese Auto (eseauto.com.ar)")).toBe(true);
    expect(text).toContain("## Toyota Corolla usado");
    expect(text).toContain("## Ford Ka usado");
    expect(text).not.toMatch(/\n{3,}/);
    expect(llmsFullTxt([], SITE)).toContain(LLMS_COPY.noGuides);
  });
});

describe("/llms.txt and /llms-full.txt", () => {
  beforeEach(() => vi.clearAllMocks());

  it("are ISR markdown read as anon, only the public columns, grouped by model", async () => {
    expect(revalidate).toBe(3600);
    expect(fullRevalidate).toBe(3600);
    const { client: c, calls } = client({ data: [FORD, ROW, { ...ROW, id: 9, generation_label: "E210", year_from: 2020, year_to: 2024 }], error: null });
    vi.mocked(createPublicClient).mockReturnValue(c);
    const res = await GET();
    expect(res.headers.get("Content-Type")).toBe("text/markdown; charset=utf-8");
    const text = await res.text();
    expect(text).toContain("/guias/toyota/corolla): ");
    expect(text).toContain("Toyota Corolla 2014 a 2024 usado");
    expect(text.match(/guias\/toyota\/corolla/g)).toHaveLength(1);
    const select = calls.find((call) => call[0] === "select")![1] as string;
    for (const internal of ["reviewed_by", "llm_version", "status", "*"]) expect(select).not.toContain(internal);
    const full = await (await fullGet()).text();
    expect(full).toContain("### E210 (2020 a 2024)");
  });

  it("a base without the table lists no guides; any other error throws (ISR keeps the file it had)", async () => {
    vi.mocked(createPublicClient).mockReturnValue(client({ data: null, error: { code: "PGRST205", message: "x" } }).client);
    expect(await (await GET()).text()).toContain(LLMS_COPY.noGuides);
    vi.mocked(createPublicClient).mockReturnValue(client({ data: null, error: { code: "57014", message: "timeout" } }).client);
    await expect(GET()).rejects.toThrow("model_guides: timeout");
  });
});
