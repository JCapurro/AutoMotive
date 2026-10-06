import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { collectionPending, collectionState } from "@/lib/search-collection";
import type { SearchProfile } from "@/lib/types";

const mocks = vi.hoisted(() => ({ admin: vi.fn(), targets: [] as Record<string, unknown>[], error: null as unknown }));
vi.mock("server-only", () => ({}));
vi.mock("@/lib/supabase/admin", () => ({ createAdminClient: mocks.admin }));
import { loadSearchCollection } from "@/lib/search-collection-server";

const profile: Pick<SearchProfile, "id" | "user_id" | "enabled" | "filters"> = {
  id: 7, user_id: "owner", enabled: true, filters: { make: "Ford", model: "Fiesta" },
};
const sources = [
  { id: "kavak", name: "Kavak", enabled: true },
  { id: "mercadolibre", name: "MercadoLibre", enabled: true },
  { id: "v6", name: "V6", enabled: false },
];
const query = {
  select: vi.fn().mockReturnThis(), contains: vi.fn().mockReturnThis(), in: vi.fn().mockReturnThis(),
  eq: vi.fn().mockReturnThis(), order: vi.fn().mockReturnThis(), limit: vi.fn().mockReturnThis(),
  then: (resolve: (value: unknown) => unknown) => Promise.resolve({ data: mocks.targets, error: mocks.error }).then(resolve),
};
beforeEach(() => {
  vi.clearAllMocks();
  vi.stubEnv("SUPABASE_SERVICE_ROLE_KEY", "test-only");
  mocks.error = null;
  mocks.targets = [
    { source: "kavak", make: "Ford", model: "Fiesta", collector_runs: [{ status: "ok", finished_at: "2026-10-06T15:00:00Z" }] },
    { source: "mercadolibre", make: "Ford", model: "Fiesta", collector_runs: [{ status: "running", finished_at: null }] },
  ];
  mocks.admin.mockReturnValue({ from: vi.fn().mockReturnValue(query) });
});
afterEach(() => vi.unstubAllEnvs());

describe("collection state from real target runs", () => {
  it("requires a successful finished run for a tick, including a completed run with zero listings", () => {
    expect(collectionState({ status: "ok", finished_at: "2026-10-06T15:00:00Z" })).toBe("done");
    expect(collectionState({ status: "ok", finished_at: null })).toBe("unknown");
    expect(collectionState({ status: "running", finished_at: null })).toBe("loading");
    expect(collectionState({ status: "failed", finished_at: "2026-10-06T15:00:00Z" })).toBe("failed");
    expect(collectionState(undefined)).toBe("waiting");
    expect(collectionPending([{ ...sources[0], collectionState: "waiting" }])).toBe(true);
    expect(collectionPending([{ ...sources[0], collectionState: "done" }])).toBe(false);
  });
  it("reads only the search's targets and the latest run of each, exposing just sanitized states", async () => {
    const result = await loadSearchCollection(profile, "owner", sources);
    expect(result).toEqual([{ ...sources[0], collectionState: "done" }, { ...sources[1], collectionState: "loading" }]);
    expect(query.contains).toHaveBeenCalledWith("query", { profile_ids: [7] });
    expect(query.in).toHaveBeenCalledWith("source", ["kavak", "mercadolibre"]);
    expect(query.order).toHaveBeenCalledWith("started_at", { referencedTable: "collector_runs", ascending: false });
    expect(query.limit).toHaveBeenCalledWith(1, { referencedTable: "collector_runs" });
    expect(query.select).toHaveBeenCalledWith("source,make,model,query,collector_runs(status,finished_at)");
  });
  it("never makes a privileged query for a different owner or a paused search", async () => {
    expect((await loadSearchCollection(profile, "another-user", sources))?.every((s) => s.collectionState === "unknown")).toBe(true);
    expect((await loadSearchCollection({ ...profile, enabled: false }, "owner", sources))?.every((s) => s.collectionState === "paused")).toBe(true);
    expect(mocks.admin).not.toHaveBeenCalled();
  });
  it("keeps a missing or stale vehicle target pending instead of accepting another model's success", async () => {
    mocks.targets[0].model = "Ka";
    const result = await loadSearchCollection(profile, "owner", sources);
    expect(result?.[0].collectionState).toBe("waiting");
    mocks.targets = [];
    expect((await loadSearchCollection(profile, "owner", sources))?.every((s) => s.collectionState === "waiting")).toBe(true);
  });
  it("accepts a completed inventory target shared with this search, requiring its explicit inventory flag", async () => {
    mocks.targets[0] = { ...mocks.targets[0], make: null, model: null, query: { inventory: true, profile_ids: [7] } };
    const result = await loadSearchCollection(profile, "owner", sources);
    expect(result?.[0].collectionState).toBe("done");
    expect(result?.[0]).not.toHaveProperty("query");
    mocks.targets[0].query = { profile_ids: [7] };
    expect((await loadSearchCollection(profile, "owner", sources))?.[0].collectionState).toBe("waiting");
  });
  it("limits collection to the saved platform subset and keeps disabled sources paused", async () => {
    const result = await loadSearchCollection({ ...profile, filters: { make: "Ford", model: "Fiesta", sources: ["kavak", "v6"] } }, "owner", sources);
    expect(result).toEqual([{ ...sources[0], collectionState: "done" }, { ...sources[2], collectionState: "paused" }]);
    expect(query.in).toHaveBeenCalledWith("source", ["kavak"]);
  });
  it("shows unknown on query failure or missing credentials without manufacturing completion", async () => {
    mocks.error = { message: "private diagnostic" };
    const result = await loadSearchCollection(profile, "owner", sources);
    expect(result?.every((s) => s.collectionState === "unknown")).toBe(true);
    expect(JSON.stringify(result)).not.toContain("private diagnostic");
    vi.stubEnv("SUPABASE_SERVICE_ROLE_KEY", "");
    mocks.admin.mockClear();
    expect((await loadSearchCollection(profile, "owner", sources))?.every((s) => s.collectionState === "unknown")).toBe(true);
    expect(mocks.admin).not.toHaveBeenCalled();
  });
});
