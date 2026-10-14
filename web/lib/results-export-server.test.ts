import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ExportRow } from "@/lib/results-csv";

const mocks = vi.hoisted(() => ({ client: null as unknown }));
vi.mock("server-only", () => ({}));
vi.mock("@/lib/supabase/server", () => ({ createClient: async () => mocks.client }));

import { resultsCsvResponse } from "@/lib/results-export-server";

const ROW: ExportRow = {
  search_name: "Ford Fiesta", detected_at: "2026-10-14T18:30:00Z", source_name: "MercadoLibre", title: "Fiesta",
  version: null, year: 2017, mileage_km: 98000, price: 10300, currency: "USD", comparables_pct: -12, score: 84,
  url: "https://example.test/1",
};

function client({ user = { id: "u1" }, profile = { name: "Ford Fiesta" } as { name: string } | null,
  total = 1, error = null as { message: string } | null } = {}) {
  const ranges: [number, number][] = [];
  const rpc = vi.fn(() => ({
    range: async (from: number, to: number) => {
      ranges.push([from, to]);
      if (error) return { data: null, error };
      const n = Math.max(Math.min(to + 1, total) - from, 0);
      return { data: Array.from({ length: n }, () => ROW), error: null };
    },
  }));
  mocks.client = {
    auth: { getUser: async () => ({ data: { user } }) },
    from: () => ({ select: () => ({ eq: () => ({ maybeSingle: async () => ({ data: profile }) }) }) }),
    rpc,
  };
  return { rpc, ranges };
}

describe("resultsCsvResponse", () => {
  beforeEach(() => { mocks.client = null; });

  it("downloads one search as a CSV file named after it", async () => {
    const { rpc } = client();
    const res = await resultsCsvResponse(7);
    expect(res.status).toBe(200);
    expect(res.headers.get("Content-Type")).toBe("text/csv; charset=utf-8");
    expect(res.headers.get("Content-Disposition")).toMatch(/^attachment; filename="ese-auto-ford-fiesta-\d{4}-\d{2}-\d{2}\.csv"$/);
    expect(rpc).toHaveBeenCalledWith("export_search_results", { p_profile_id: 7 });
    const bytes = new Uint8Array(await res.arrayBuffer());
    expect([...bytes.slice(0, 3)]).toEqual([0xef, 0xbb, 0xbf]);            // the UTF-8 BOM Excel looks for
    const body = new TextDecoder().decode(bytes);                          // (the decoder drops it)
    expect(body.startsWith("Búsqueda;Fecha de detección;")).toBe(true);
    expect(body.split("\r\n")).toHaveLength(3);
  });

  it("reads past the API's 1000 rows a request", async () => {
    const { rpc, ranges } = client({ total: 2500 });
    const res = await resultsCsvResponse(null);
    expect(rpc).toHaveBeenCalledWith("export_search_results", {});
    expect(ranges).toEqual([[0, 999], [1000, 1999], [2000, 2999]]);
    expect((await res.text()).trim().split("\r\n")).toHaveLength(2501);
    expect(res.headers.get("Content-Disposition")).toContain("ese-auto-busquedas-");
  });

  it("refuses a plan without the export, an unknown search and a signed-out visitor", async () => {
    client({ error: { message: "plan_feature_unavailable" } });
    expect((await resultsCsvResponse(7)).status).toBe(403);
    client({ profile: null });
    expect((await resultsCsvResponse(8)).status).toBe(404);
    client({ user: null as unknown as { id: string } });
    expect((await resultsCsvResponse(7)).status).toBe(401);
  });

  it("any other database error is a server error", async () => {
    client({ error: { message: "connection reset" } });
    await expect(resultsCsvResponse(7)).rejects.toThrow("export_search_results: connection reset");
  });
});
