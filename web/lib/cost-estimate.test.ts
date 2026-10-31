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
  return { estimate, line: costLine(estimate), zones: o.zones ?? [PALERMO], from: o.from ?? "search", sellerKind: o.sellerKind ?? (seller ?? "none"), cfg };
}
const html = (v: CostView | null) => renderToStaticMarkup(createElement(CostEstimate, { listingId: 7, view: v }));
const text = (markup: string) => markup.replace(/<[^>]+>/g, "\n").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#x27;/g, "'");

describe("CostEstimate (the listing page)", () => {
  it("shows the header and a closed breakdown", () => {
    const markup = html(view());
    expect(markup).toContain('data-testid="cost-estimate"');
    expect(markup).toContain(">Costo total estimado: USD 16.290 – 16.560 (ARS 21.188.000 – 21.518.000)<");
    expect(markup).toMatch(/<details[^>]*data-testid="cost-estimate-details"[^>]*>/);
    expect(markup).not.toMatch(/<details[^>]* open/);
    const t = text(markup);
    for (const s of ["Ver detalle", "Precio publicado", "ARS 20.000.000", "Arancel de transferencia DNRPA", "ARS 200.000", "Sellos de CABA",
      "ARS 600.000", "Formularios 08 y 12", "ARS 8.000 – 18.900", "Patente anual (valores 2026)", "ARS 380.900 – 698.700",
      "Fuera del total: informe de dominio ARS 4.000 – 4.400, recomendado antes de señar.",
      "Gestor opcional: sin tarifa oficial, se pacta con el gestor.",
      "Patente y sellos de CABA, según tu búsqueda en «Palermo, CABA».", "Vendedor: particular.",
      "La valuación fiscal se estima como precio × 0,70–1,00 (supuesto propio, no oficial). Si la tabla oficial de tu modelo supera el precio, el arancel y los sellos son mayores.",
      "Dólar del aviso: $1.300.", "Montos redondeados hacia afuera.", "Parámetros al 30/10.", "Fuentes:"]) {
      expect(t, s).toContain(s);
    }
  });

  it("cites each term's source with its date", () => {
    const t = text(html(view()));
    expect(t).toContain("Arancel: Res. MJ 412/2026, Anexo I, arancel 2A (https://www.cira.org.ar/wp-content/uploads/anexo_7754131_1.pdf) (01/09)");
    expect(t).toMatch(/Sellos \(CABA\): Ley 6927 Anexo art\. 32 .* \(01\/01\)/);
    expect(t).toMatch(/Formularios \(08\): IF-2026-06520679-APN-SSGA#MJ .* \(19\/01\)/);
    expect(t).toMatch(/Patente \(CABA\): Ley 6927 Anexo art\. 50 .* \(01\/01\)/);
    expect(t).toMatch(/Valuación fiscal: Supuesto propio, no oficial\..* \(30\/10\)/);
    expect(t).toMatch(/Informe de dominio: Res\. MJ 412\/2026, Anexo I, arancel 5A \(01\/09\)/);
  });

  it("says what is missing and why", () => {
    let t = text(html(view({ year: null })));
    expect(t).toContain("Costo total estimado (sin patente): USD 16.000 – 16.020 (ARS 20.808.000 – 20.819.000)");
    expect(t).toContain("Patente: falta el año del modelo.");
    t = text(html(view({ jurisdiction: null, zones: [] })));
    expect(t).toContain("Costo total estimado (sin sellos ni patente): USD 15.540 – 15.560 (ARS 20.208.000 – 20.219.000)");
    expect(t).toContain("Sellos y patente: tu búsqueda no tiene zona en Argentina.");
    expect(t).not.toContain("Patente y sellos de");
    t = text(html(view({ jurisdiction: ["ba"], year: 1985, zones: [{ lat: -34.92, lon: -57.95, label: "La Plata" }] })));
    expect(t).toContain("Patente: modelo anterior a 1990 en Buenos Aires: sin dato.");
  });

  it("names AMBA, the rest of the country and several zones", () => {
    let t = text(html(view({ jurisdiction: ["caba", "ba"], zones: [{ lat: -34.6037, lon: -58.3816, label: "AMBA" }] })));
    expect(t).toContain("Patente y sellos de CABA y Buenos Aires, según tu búsqueda en «AMBA»: el rango cubre las dos.");
    expect(t).toContain("Tu búsqueda es AMBA: el rango cubre CABA y provincia de Buenos Aires.");
    t = text(html(view({ jurisdiction: ["rest"], zones: [{ lat: -32.94, lon: -60.65, label: "Rosario (zona aproximada)" }] })));
    expect(t).toContain("Patente y sellos de resto del país, según tu búsqueda en «Rosario (zona aproximada)».");
    expect(t).toContain("Resto del país: rango armado con Córdoba, Santa Fe y Mendoza.");
    t = text(html(view({ jurisdiction: ["caba", "rest"], zones: [PALERMO, CORDOBA] })));
    expect(t).toContain("Patente y sellos de CABA y resto del país, según tu búsqueda en «Palermo, CABA» y «Córdoba»: el rango cubre las dos.");
    t = text(html(view({ from: "profile", zones: [{ ...PALERMO, label: "Palermo" }] })));
    expect(t).toContain("Patente y sellos de CABA, según tu zona en «Palermo».");
  });

  it("names the seller: posible agencia, concesionaria, sin informar", () => {
    expect(text(html(view({ seller: "dealer", sellerKind: "inferred" })))).toContain("Vendedor: posible agencia.");
    expect(text(html(view({ seller: "dealer", sellerKind: "dealer" })))).toContain("Vendedor: concesionaria.");
    expect(text(html(view({ seller: null, sellerKind: "none" })))).toContain("Vendedor: sin informar: el rango cubre particular y agencia.");
  });

  it("shows only pesos without the listing's dollar", () => {
    const t = text(html(view({ fx_rate: null })));
    expect(t).toContain("Costo total estimado: ARS 21.188.000 – 21.518.000 (sin dólar del día)");
    expect(t).toContain("Sin dólar del día: el total va solo en pesos.");
  });

  it("a USD listing without a current quote: the header only, no breakdown", () => {
    const markup = html(view({ price: 15000, currency: "USD", fx_rate: null, fx: null }));
    expect(text(markup)).toContain("Costo total estimado: sin dólar del día, no se puede estimar");
    expect(markup).not.toContain("cost-estimate-details");
  });

  it("a USD listing with the blue quote says which one", () => {
    const t = text(html(view({ price: 15000, currency: "USD", fx_rate: null, fx: { rate: 1300, kind: "blue", date: "2026-10-29" } })));
    expect(t).toContain("USD 15.000 = ARS 19.500.000");
    expect(t).toContain("Dólar blue del 29/10: $1.300.");
  });

  it("labels the price as the listing page does", () => {
    expect(text(html(view({ cash: true })))).toContain("Precio de contado");
    expect(text(html(view({ cash: false })))).toContain("Precio publicado");
  });

  it("renders nothing without an estimate", () => {
    expect(html(null)).toBe("");
  });

  it("never says «8–10 %» nor «precio real»", () => {
    for (const v of [view(), view({ year: null }), view({ seller: "dealer", sellerKind: "inferred" }), view({ fx_rate: null })]) {
      const t = text(html(v)).toLowerCase();
      expect(t).not.toMatch(/8\s*[–-]\s*10\s*%/);
      expect(t).not.toContain("precio real");
      expect(t).toContain("estimado");
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
    fake = fakeSupabase({ feature: true, listings: [ROW], profile: { default_origin_lat: null, default_origin_lon: null, default_origin_label: null } });
    lines = await costLinesFor(fake.client, "u1", [{ listing_id: 501 }]);
    expect(lines.get(501)).toBe("Costo total estimado (sin sellos ni patente): USD 15.540 – 15.560 (ARS 20.208.000 – 20.219.000)");
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
