import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

import { fetchMatchMargins, marginAccess, marginLinesFor, parseMarginAccess } from "@/lib/margin-data";
import { marginCardLine, marginLine } from "@/lib/margin-view";
import { effectiveSort, isSort, SORTS, sortsFor } from "@/lib/sorts";

const GOLDEN = JSON.parse(readFileSync(path.resolve(__dirname, "../../worker/tests/fixtures/margin/golden.json"), "utf-8")) as {
  cases: { name: string; implausible?: boolean; margin_ref: unknown }[];
};
const REF = GOLDEN.cases[0].margin_ref;
// A margin stored before the guard: an ARS price loaded as USD (Facebook).
const BORA = GOLDEN.cases.find((c) => c.name === "implausible: ARS cargado como USD")!.margin_ref;

type Client = Parameters<typeof marginLinesFor>[0];
function client(rpc: (fn: string, args?: unknown) => unknown): Client {
  return { rpc: vi.fn(async (fn: string, args?: unknown) => rpc(fn, args)) } as unknown as Client;
}

describe("margin access (PRO-02 gating)", () => {
  it("only with the feature and a minimum", () => {
    expect(parseMarginAccess({ enabled: true, min_threshold_usd: 500 })).toEqual({ minThresholdUsd: 500 });
    for (const data of [null, {}, { enabled: false, min_threshold_usd: 500 }, { enabled: true, min_threshold_usd: null },
      { enabled: true, min_threshold_usd: 0 }, { enabled: true, min_threshold_usd: 12.5 }, { enabled: "true", min_threshold_usd: 500 }]) {
      expect(parseMarginAccess(data)).toBeNull();
    }
  });

  it("a database without the migration: no access, no throw", async () => {
    expect(await marginAccess(client(() => ({ data: null, error: { message: "Could not find the function public.my_margin_access" } })))).toBeNull();
    expect(await marginAccess(client(() => { throw new Error("network"); }))).toBeNull();
    expect(await marginAccess(client(() => ({ data: { enabled: true, min_threshold_usd: 500 }, error: null })))).toEqual({ minThresholdUsd: 500 });
  });
});

describe("fetchMatchMargins / marginLinesFor", () => {
  it("an error (the RPC missing) leaves the map empty", async () => {
    expect((await fetchMatchMargins(async () => ({ data: null, error: { message: "missing" } }), [1])).size).toBe(0);
    expect((await fetchMatchMargins(async () => { throw new Error("x"); }, [1])).size).toBe(0);
  });

  it("no call without ids, unknown shapes dropped", async () => {
    const rpc = vi.fn(async () => ({ data: [{ match_id: 1, margin_ref: REF }, { match_id: 2, margin_ref: { v: 9 } }], error: null }));
    expect((await fetchMatchMargins(rpc, [])).size).toBe(0);
    expect(rpc).not.toHaveBeenCalled();
    const map = await fetchMatchMargins(rpc, [1, 1, 2, null]);
    expect(rpc).toHaveBeenCalledWith("my_match_margins", { p_match_ids: [1, 2] });
    expect([...map.keys()]).toEqual([1]);
  });

  it("a stored margin for an implausible price is dropped: no line on the card", async () => {
    const supabase = client(() => ({ data: [{ match_id: 7, margin_ref: REF }, { match_id: 8, margin_ref: BORA }], error: null }));
    const lines = await marginLinesFor(supabase, { minThresholdUsd: 500 }, [{ listing_id: 70, match_id: 7 }, { listing_id: 80, match_id: 8 }]);
    expect([...lines.keys()]).toEqual([70]);
    const map = await fetchMatchMargins(async () => ({ data: [{ match_id: 8, margin_ref: BORA }], error: null }), [8]);
    expect(map.size).toBe(0);
  });

  it("without access, nothing past the check (not Pro)", async () => {
    const supabase = client(() => ({ data: [{ match_id: 7, margin_ref: REF }], error: null }));
    expect((await marginLinesFor(supabase, null, [{ listing_id: 70, match_id: 7 }])).size).toBe(0);
    expect(supabase.rpc).not.toHaveBeenCalled();
  });

  it("with access, the short card line by listing (the listing page keeps the full one)", async () => {
    const supabase = client(() => ({ data: [{ match_id: 7, margin_ref: REF }], error: null }));
    const lines = await marginLinesFor(supabase, { minThresholdUsd: 500 }, [{ listing_id: 70, match_id: 7 }, { listing_id: 71, match_id: 8 }]);
    expect(lines.get(70)).toBe(marginCardLine(REF));
    expect(lines.get(70)).toBe("Margen bruto estimado: USD 1.210 a 1.230 (n\u00a0=\u00a06\u00a0agencias)");
    expect(lines.get(70)).not.toBe(marginLine(REF));
    expect(lines.has(71)).toBe(false);
  });

  it("without enough dealers, the short line that says so (Juan, 02/11)", async () => {
    const few = { v: 1, status: "few_dealers", dealer_n: 2, min_n: 5, n: 10, level_used: "transmission" };
    const supabase = client(() => ({ data: [{ match_id: 7, margin_ref: few }], error: null }));
    const lines = await marginLinesFor(supabase, { minThresholdUsd: 500 }, [{ listing_id: 70, match_id: 7 }]);
    expect(lines.get(70)).toBe("Margen estimado: pocas agencias para estimarlo (n\u00a0=\u00a02)");
  });
});

describe("sorts", () => {
  it("«Mayor margen estimado» only with the margin", () => {
    expect(SORTS.margin).toBe("Mayor margen estimado");
    expect(sortsFor(false)).not.toContain("margin");
    expect(sortsFor(true)).toContain("margin");
    expect(isSort("margin")).toBe(true);
    expect(effectiveSort("margin", false)).toBe("score");
    expect(effectiveSort("margin", true)).toBe("margin");
    expect(effectiveSort("price", false)).toBe("price");
    expect(effectiveSort("nope", true)).toBe("score");
  });
});
