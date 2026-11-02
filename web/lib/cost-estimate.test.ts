import { readFileSync } from "node:fs";
import path from "node:path";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  config: { costEstimator: null as unknown },
  fx: [] as { rate: number; kind: string; date: string }[],
  requireUser: vi.fn(async () => ({ id: "u1" })),
  track: vi.fn(async () => {}),
  supabase: null as unknown,
}));
vi.mock("server-only", () => ({}));
vi.mock("@/app/app/listings/actions", () => ({ trackTotalCostExpanded: vi.fn() }));
vi.mock("@/lib/config", () => ({ webConfig: async () => mocks.config }));
vi.mock("@/lib/supabase/admin", () => ({
  createAdminClient: () => ({
    from: () => {
      let kind = "";
      const q = {
        select: () => q,
        eq: (_c: string, v: string) => ((kind = v), q),
        order: () => q,
        limit: () => q,
        maybeSingle: async () => ({ data: mocks.fx.find((f) => f.kind === kind) ?? null }),
      };
      return q;
    },
  }),
}));

import { CostEstimate } from "@/components/app/cost-estimate";
import { type CostView, costLinesFor } from "@/lib/cost-estimate-data";
import { costLine, estimateCost, parseCostEstimator, type Jurisdiction, type Seller } from "@/lib/cost-estimator";
import type { SellerKind } from "@/lib/cost-estimate-view";

const GOLDEN = JSON.parse(
  readFileSync(path.resolve(__dirname, "../../worker/tests/fixtures/cost_estimator/golden.json"), "utf-8"),
) as { config: Record<string, unknown> };
const cfg = parseCostEstimator(GOLDEN.config)!;
const PALERMO = { lat: -34.5875, lon: -58.42, label: "Palermo, CABA" };
const CORDOBA = { lat: -31.4201, lon: -64.1888, label: "Córdoba" };

type Opts = {
  price?: number; currency?: "ARS" | "USD"; fx_rate?: number | null; cash?: boolean; year?: number | null; body_type?: string | null;
  jurisdiction?: Jurisdiction[] | null; seller?: Seller; fx?: { rate: number; kind: string; date: string } | null;
  zones?: typeof PALERMO[]; from?: "search" | "profile"; sellerKind?: SellerKind;
};
function view(o: Opts = {}): CostView {
  const listing = {
    price: o.price ?? 20000000, currency: o.currency ?? "ARS", fx_rate: o.fx_rate === undefined ? 1300 : o.fx_rate,
    cash: o.cash ?? false, year: o.year === undefined ? 2017 : o.year, body_type: o.body_type === undefined ? "sedan" : o.body_type,
  } as const;
  const jurisdiction = o.jurisdiction === undefined ? (["caba"] as Jurisdiction[]) : o.jurisdiction;
  const seller = o.seller === undefined ? "private" : o.seller;
  const estimate = estimateCost(listing, jurisdiction, seller, o.fx ?? null, cfg)!;
  return {
    estimate, line: costLine(estimate), zones: o.zones ?? [PALERMO], from: o.from ?? "search", sellerKind: o.sellerKind ?? (seller ?? "none"), cfg,
    searchProfileId: (o.from ?? "search") === "search" ? 9 : null,
  };
}
const html = (v: CostView | null) => renderToStaticMarkup(createElement(CostEstimate, { listingId: 7, view: v }));
const text = (markup: string) => markup.replace(/<[^>]+>/g, "\n").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#x27;/g, "'");

describe("CostEstimate (the listing page)", () => {
  // Juan 02/11: the breakdown is a compact summary of at most four lines.
  const rows = (markup: string) =>
    [...markup.matchAll(/<dt[^>]*>([^<]*)<\/dt><dd[^>]*>([^<]*)<\/dd>/g)].map((m) => [m[1], m[2]]);
  const footnote = (markup: string) => text(markup.match(/<p[^>]*data-testid="cost-estimate-footnote"[^>]*>[\s\S]*?<\/p>/)?.[0] ?? "").trim();

  it("shows the header and a closed, compact breakdown: transfer, patente, total and one footnote", () => {
    const markup = html(view());
    expect(markup).toContain('data-testid="cost-estimate"');
    expect(markup).toContain(">Costo total estimado: USD 16.290 – 16.560 (ARS 21.188.000 – 21.518.000)<");
    expect(markup).toMatch(/<details[^>]*data-testid="cost-estimate-details"[^>]*>/);
    expect(markup).not.toMatch(/<details[^>]* open/);
    expect(text(markup)).toContain("Ver detalle");
    expect(rows(markup)).toEqual([
      ["Transferencia", "ARS 808.000 – 818.900"],
      ["Patente anual (valores 2026)", "ARS 380.900 – 698.700"],
      ["Total estimado", "ARS 21.188.000 – 21.518.000"],
    ]);
    expect(footnote(markup)).toBe("Valores oficiales al 30/10 para CABA. No incluye gestoría ni informe de dominio (ARS 4.000 – 4.400).");
    // Nothing else inline: no per-term rows, no notes list, no sources outside their toggle.
    const t = text(markup.replace(/<details[^>]*data-testid="cost-estimate-sources"[\s\S]*?<\/details>/, ""));
    for (const gone of ["Arancel de transferencia DNRPA", "Sellos de", "Formularios 08 y 12", "Precio publicado", "Vendedor:", "valuación fiscal",
      "Dólar del aviso", "Montos redondeados", "Parámetros al", "Res. MJ 412/2026"]) {
      expect(t, gone).not.toContain(gone);
    }
    expect(markup).not.toContain("<ul");
  });

  it("names the jurisdiction once (the sources, behind their toggle, aside)", () => {
    const t = text(html(view()).replace(/<details[^>]*data-testid="cost-estimate-sources"[\s\S]*?<\/details>/, ""));
    expect(t.match(/CABA/g)).toHaveLength(1);
  });

  it("keeps the sources behind a single «Ver fuentes» toggle, each with its date", () => {
    const markup = html(view());
    const sources = markup.match(/<details[^>]*data-testid="cost-estimate-sources"[^>]*>([\s\S]*?)<\/details>/);
    expect(sources).not.toBeNull();
    expect(sources![0]).not.toMatch(/<details[^>]* open/);
    expect(markup.match(/data-testid="cost-estimate-sources"/g)).toHaveLength(1);
    const t = text(sources![1]);
    expect(t).toContain("Ver fuentes");
    expect(t).toContain("Arancel: Res. MJ 412/2026, Anexo I, arancel 2A (https://www.cira.org.ar/wp-content/uploads/anexo_7754131_1.pdf) (01/09)");
    expect(t).toMatch(/Sellos \(CABA\): Ley 6927 Anexo art\. 32 .* \(01\/01\)/);
    expect(t).toMatch(/Formularios \(08\): IF-2026-06520679-APN-SSGA#MJ .* \(19\/01\)/);
    expect(t).toMatch(/Patente \(CABA\): Ley 6927 Anexo art\. 50 .* \(01\/01\)/);
    expect(t).toMatch(/Valuación fiscal: Supuesto propio, no oficial\..* \(30\/10\)/);
    expect(t).toMatch(/Informe de dominio: Res\. MJ 412\/2026, Anexo I, arancel 5A \(01\/09\)/);
    expect(t).toContain("Dólar del aviso: $1.300");
  });

  it("other missing pieces keep their explicit message", () => {
    let markup = html(view({ year: null }));
    expect(text(markup)).toContain("Costo total estimado (sin patente): USD 16.000 – 16.020 (ARS 20.808.000 – 20.819.000)");
    expect(rows(markup)[1]).toEqual(["Patente anual (valores 2026)", "falta el año del modelo"]);
    markup = html(view({ jurisdiction: ["ba"], year: 1985, zones: [{ lat: -34.92, lon: -57.95, label: "La Plata" }] }));
    expect(rows(markup)[1]).toEqual(["Patente anual (valores 2026)", "modelo anterior a 1990 en Buenos Aires: sin dato"]);
    const noForm12 = parseCostEstimator({ ...GOLDEN.config, fixed_ars: { ...(GOLDEN.config.fixed_ars as object), form_12: { min: 1 } } })!;
    const est = estimateCost({ price: 20000000, currency: "ARS", fx_rate: 1300, cash: false, year: 2017, body_type: "sedan" }, ["caba"], "private", null, noForm12)!;
    markup = html({ ...view(), estimate: est, line: costLine(est), cfg: noForm12 });
    expect(rows(markup)[0]).toEqual(["Transferencia (sin formularios)", "ARS 800.000"]);
    const t = text(html(view({ fx_rate: null })));
    expect(t).toContain("Costo total estimado: ARS 21.188.000 – 21.518.000 (sin dólar del día)");
  });

  it("AMBA and several zones: the range across real jurisdictions, named with «o»", () => {
    let markup = html(view({ jurisdiction: ["caba", "ba"], zones: [{ lat: -34.6037, lon: -58.3816, label: "AMBA" }] }));
    expect(text(markup)).toContain("Costo total estimado: USD 16.110 – 16.560 (ARS 20.948.000 – 21.518.000)");
    expect(footnote(markup)).toBe("Valores oficiales al 30/10 para CABA o Provincia de Buenos Aires. No incluye gestoría ni informe de dominio (ARS 4.000 – 4.400).");
    markup = html(view({ jurisdiction: ["caba", "rest"], zones: [PALERMO, CORDOBA] }));
    expect(footnote(markup)).toContain("para CABA o resto del país.");
    markup = html(view({ jurisdiction: ["caba", "ba", "rest"], zones: [PALERMO, CORDOBA] }));
    expect(footnote(markup)).toContain("para CABA, Provincia de Buenos Aires o resto del país.");
  });

  it("without the buyer's locality: one clear line, no total nor partial total, no breakdown (Juan 02/11)", () => {
    const NO_ZONE = "Costo total: no sabemos tu localidad. Cargala en la búsqueda para estimarlo";
    for (const o of [{ jurisdiction: null, zones: [] }, { jurisdiction: [] as Jurisdiction[], zones: [] },
      { jurisdiction: null, zones: [], price: 15000, currency: "USD" as const, fx_rate: null, fx: { rate: 1300, kind: "blue", date: "2026-10-29" } }]) {
      const markup = html({ ...view(o), searchProfileId: 9 });
      const headline = markup.match(/<p[^>]*data-testid="cost-estimate-headline"[^>]*>([\s\S]*?)<\/p>/)![1];
      expect(text(headline).replace(/\n/g, "")).toBe(NO_ZONE);
      expect(headline).toMatch(/<a[^>]*href="\/app\/searches\/9\/edit"[^>]*>Cargala en la búsqueda<\/a>/);
      expect(text(markup)).not.toMatch(/ARS|USD|\d/);
      expect(markup).not.toContain("cost-estimate-details");
    }
    // No search (the account's default place, missing): the same words, nothing to link.
    const markup = html({ ...view({ jurisdiction: null, zones: [], from: "profile" }), searchProfileId: null });
    expect(text(markup).replace(/\n/g, "")).toBe(NO_ZONE);
    expect(markup).not.toContain("<a");
  });

  it("a USD listing without a current quote: the header only, no breakdown", () => {
    const markup = html(view({ price: 15000, currency: "USD", fx_rate: null, fx: null }));
    expect(text(markup)).toContain("Costo total estimado: sin dólar del día, no se puede estimar");
    expect(markup).not.toContain("cost-estimate-details");
  });

  it("a USD listing with the blue quote says which one, in the sources", () => {
    const t = text(html(view({ price: 15000, currency: "USD", fx_rate: null, fx: { rate: 1300, kind: "blue", date: "2026-10-29" } })));
    expect(t).toContain("Dólar blue del 29/10: $1.300");
  });

  it("renders nothing without an estimate", () => {
    expect(html(null)).toBe("");
  });

  it("never says «8–10 %» nor «precio real»", () => {
    for (const v of [view(), view({ year: null }), view({ seller: "dealer", sellerKind: "inferred" }), view({ fx_rate: null }), view({ jurisdiction: null, zones: [] })]) {
      const t = text(html(v)).toLowerCase();
      expect(t).not.toMatch(/8\s*[–-]\s*10\s*%/);
      expect(t).not.toContain("precio real");
      expect(t).toMatch(/estimado|estimarlo/);
    }
  });
});

// ---------------------------------------------------------------------------
// costLinesFor: the cards of a page
// ---------------------------------------------------------------------------

type Call = { table: string; columns?: string; filter?: [string, unknown] };
function fakeSupabase(opts: { feature: boolean; listings: Record<string, unknown>[]; searches?: Record<string, unknown>[]; profile?: Record<string, unknown> | null }) {
  const calls: Call[] = [];
  const rpc = vi.fn(async () => ({ data: opts.feature }));
  const from = (table: string) => {
    const call: Call = { table };
    calls.push(call);
    const rows = table === "listings" ? opts.listings : table === "search_profiles" ? (opts.searches ?? []) : [opts.profile ?? null];
    const q = {
      select: (columns: string) => ((call.columns = columns), q),
      in: async (column: string, values: unknown[]) => ((call.filter = [column, values]), { data: rows }),
      eq: (column: string, value: unknown) => ((call.filter = [column, value]), q),
      maybeSingle: async () => ({ data: rows[0] ?? null }),
    };
    return q;
  };
  return { client: { rpc, from } as never, calls, rpc };
}

const ROW = {
  id: 501, price: 20000000, currency: "ARS", price_usd: 15384.62, price_partial: false, description_facts: null,
  seller_type: "private", dealer_inferred: false, year: 2017, body_type: "sedan",
};
const SEARCH = { id: 9, origin_lat: -34.5875, origin_lon: -58.42, filters: { location_label: "Palermo, CABA" } };

describe("costLinesFor", () => {
  beforeEach(() => {
    mocks.config = { costEstimator: cfg };
    mocks.fx = [];
  });

  it("one listings query for the page with the estimate's columns, one for the distinct searches", async () => {
    const { client, calls } = fakeSupabase({ feature: true, listings: [ROW, { ...ROW, id: 502 }], searches: [SEARCH] });
    const lines = await costLinesFor(client, "u1", [
      { listing_id: 501, search_profile_id: 9 },
      { listing_id: 502, search_profile_id: 9 },
    ]);
    expect(lines.get(501)).toBe("Costo total estimado: USD 16.290 – 16.560 (ARS 21.188.000 – 21.518.000)");
    expect(lines.get(502)).toBe(lines.get(501));
    expect(calls.map((c) => c.table)).toEqual(["listings", "search_profiles"]);
    expect(calls[0].columns).toBe("id, price, currency, price_usd, price_partial, description_facts, seller_type, dealer_inferred, year, body_type");
    expect(calls[0].filter).toEqual(["id", [501, 502]]);
    expect(calls[1].filter).toEqual(["id", [9]]);
  });

  it("without the flag, no query past the flag check", async () => {
    const { client, calls, rpc } = fakeSupabase({ feature: false, listings: [ROW] });
    expect((await costLinesFor(client, "u1", [{ listing_id: 501, search_profile_id: 9 }])).size).toBe(0);
    expect(rpc).toHaveBeenCalledWith("my_plan_feature", { p_feature: "total_cost" });
    expect(calls).toEqual([]);
  });

  it("without cost_estimator, no line", async () => {
    mocks.config = { costEstimator: null };
    const { client, calls } = fakeSupabase({ feature: true, listings: [ROW] });
    expect((await costLinesFor(client, "u1", [{ listing_id: 501, search_profile_id: 9 }])).size).toBe(0);
    expect(calls).toEqual([]);
  });

  it("no line for a partial price, as on the listing page", async () => {
    const { client } = fakeSupabase({
      feature: true,
      listings: [{ ...ROW, price_partial: true }, { ...ROW, id: 502, description_facts: { price_check: { published_partial: true } } }],
      searches: [SEARCH],
    });
    const lines = await costLinesFor(client, "u1", [{ listing_id: 501, search_profile_id: 9 }, { listing_id: 502, search_profile_id: 9 }]);
    expect(lines.size).toBe(0);
  });

  it("a card without a search uses the account's default place; without one, no zone", async () => {
    let fake = fakeSupabase({ feature: true, listings: [ROW], profile: { default_origin_lat: -34.5875, default_origin_lon: -58.42, default_origin_label: "Palermo" } });
    let lines = await costLinesFor(fake.client, "u1", [{ listing_id: 501, search_profile_id: null }]);
    expect(lines.get(501)).toBe("Costo total estimado: USD 16.290 – 16.560 (ARS 21.188.000 – 21.518.000)");
    expect(fake.calls.map((c) => c.table)).toEqual(["listings", "profiles"]);
    expect(fake.calls[1].filter).toEqual(["id", "u1"]);
    // Without one: no line on the card (Juan 02/11: never a partial total; the same
    // «no sabemos tu localidad» on every card would only repeat what the listing page says).
    fake = fakeSupabase({ feature: true, listings: [ROW], profile: { default_origin_lat: null, default_origin_lon: null, default_origin_label: null } });
    lines = await costLinesFor(fake.client, "u1", [{ listing_id: 501 }]);
    expect(lines.has(501)).toBe(false);
    fake = fakeSupabase({ feature: true, listings: [ROW], searches: [{ id: 9, origin_lat: null, origin_lon: null, filters: {} }] });
    lines = await costLinesFor(fake.client, "u1", [{ listing_id: 501, search_profile_id: 9 }]);
    expect(lines.has(501)).toBe(false);
  });

  it("a USD listing reads the latest blue quote, else the oficial one", async () => {
    const usd = { ...ROW, price: 15000, currency: "USD", price_usd: 15000 };
    const today = new Intl.DateTimeFormat("en-CA", { timeZone: "America/Argentina/Buenos_Aires" }).format(new Date());
    mocks.fx = [{ rate: 1300, kind: "oficial", date: today }];
    let fake = fakeSupabase({ feature: true, listings: [usd], searches: [SEARCH] });
    expect((await costLinesFor(fake.client, "u1", [{ listing_id: 501, search_profile_id: 9 }])).get(501)).toBe(
      "Costo total estimado: USD 15.880 – 16.140 (ARS 20.654.000 – 20.973.000)",
    );
    mocks.fx = [];
    fake = fakeSupabase({ feature: true, listings: [usd], searches: [SEARCH] });
    expect((await costLinesFor(fake.client, "u1", [{ listing_id: 501, search_profile_id: 9 }])).get(501)).toBe(
      "Costo total estimado: sin dólar del día, no se puede estimar",
    );
  });
});
