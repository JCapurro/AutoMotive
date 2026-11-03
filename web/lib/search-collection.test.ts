import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { collectionPending, collectionState, onFirstRead, staleAt } from "@/lib/search-collection";
import type { SearchProfile } from "@/lib/types";

const mocks = vi.hoisted(() => ({
  admin: vi.fn(), targets: [] as Record<string, unknown>[], error: null as unknown, config: null as unknown,
}));
vi.mock("server-only", () => ({}));
vi.mock("@/lib/supabase/admin", () => ({ createAdminClient: mocks.admin }));
import { loadSearchCollection } from "@/lib/search-collection-server";

const profile: Pick<SearchProfile, "id" | "user_id" | "enabled" | "filters" | "created_at"> = {
  id: 7, user_id: "owner", enabled: true, filters: { make: "Ford", model: "Fiesta" }, created_at: "2026-10-06T12:00:00Z",
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
const configQuery = {
  select: vi.fn().mockReturnThis(), eq: vi.fn().mockReturnThis(),
  maybeSingle: () => Promise.resolve({ data: mocks.config === null ? null : { value: mocks.config }, error: null }),
};
beforeEach(() => {
  vi.clearAllMocks();
  vi.stubEnv("SUPABASE_SERVICE_ROLE_KEY", "test-only");
  mocks.error = null;
  mocks.config = null;
  mocks.targets = [
    { source: "kavak", make: "Ford", model: "Fiesta", first_run_done: true, last_run_at: "2026-10-06T14:00:00Z", created_at: "2026-09-01T00:00:00Z", collector_runs: [{ status: "ok", finished_at: "2026-10-06T15:00:00Z" }] },
    { source: "mercadolibre", make: "Ford", model: "Fiesta", first_run_done: true, last_run_at: "2026-10-06T11:00:00Z", created_at: "2026-09-01T00:00:00Z", collector_runs: [{ status: "running", finished_at: null }] },
  ];
  mocks.admin.mockReturnValue({ from: vi.fn((table: string) => (table === "app_config" ? configQuery : query)) });
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
    expect(result).toEqual([
      { ...sources[0], collectionState: "done", firstRead: false, newTarget: false },
      { ...sources[1], collectionState: "loading", firstRead: false, newTarget: false },
    ]);
    expect(query.contains).toHaveBeenCalledWith("query", { profile_ids: [7] });
    expect(query.in).toHaveBeenCalledWith("source", ["kavak", "mercadolibre"]);
    expect(query.order).toHaveBeenCalledWith("started_at", { referencedTable: "collector_runs", ascending: false });
    expect(query.limit).toHaveBeenCalledWith(2, { referencedTable: "collector_runs" });
    expect(query.select).toHaveBeenCalledWith("source,make,model,body_type,query,first_run_done,last_run_at,created_at,collector_runs(status,started_at,finished_at)");
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
    expect(result).toEqual([{ ...sources[0], collectionState: "done", firstRead: false, newTarget: false }, { ...sources[2], collectionState: "paused" }]);
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

describe("model-less searches (docs/CARROCERIA.md)", () => {
  const byBody = { ...profile, filters: { body_types: ["suv", "pickup"], price_max: 20_000 } };
  const run = (status: string) => [{ status, finished_at: status === "ok" ? "2026-10-15T15:00:00Z" : null }];

  it("follows the search's body type targets, showing the busiest of a source's", async () => {
    mocks.targets = [
      { source: "mercadolibre", make: null, model: null, body_type: "suv", query: { profile_ids: [7] }, collector_runs: run("ok") },
      { source: "mercadolibre", make: null, model: null, body_type: "pickup", query: { profile_ids: [7] }, collector_runs: run("running") },
      { source: "kavak", make: null, model: null, body_type: "suv", query: { profile_ids: [7] }, collector_runs: run("ok") },
      { source: "kavak", make: null, model: null, body_type: "pickup", query: { profile_ids: [7] }, collector_runs: run("ok") },
    ];
    const result = await loadSearchCollection(byBody, "owner", sources);
    expect(result).toEqual([{ ...sources[0], collectionState: "done" }, { ...sources[1], collectionState: "loading" }]);
  });
  it("waits for the body type targets not linked yet on the sources that search by body type", async () => {
    // A batch from another source can bootstrap the search before derive_targets links it.
    mocks.targets = [
      { source: "kavak", make: null, model: null, body_type: "suv", query: { profile_ids: [7] }, collector_runs: run("ok") },
    ];
    expect((await loadSearchCollection(byBody, "owner", sources))?.map((s) => s.collectionState)).toEqual(["waiting", "waiting"]);
    // Kavak has no convertible filter: nothing to wait for there.
    const convertible = { ...byBody, filters: { body_types: ["convertible"], price_max: 20_000 } };
    expect((await loadSearchCollection(convertible, "owner", sources))?.map((s) => s.collectionState)).toEqual(["done", "waiting"]);
    // Only the configured sources get targets by body type.
    mocks.config = { sources: ["kavak"], interval_seconds: 1800 };
    mocks.targets = [];
    expect((await loadSearchCollection(byBody, "owner", sources))?.map((s) => s.collectionState)).toEqual(["waiting", "done"]);
  });
  it("never takes a model's target, nor another body type's", async () => {
    mocks.config = { sources: [] };
    mocks.targets = [
      { source: "kavak", make: "Ford", model: "Fiesta", body_type: null, query: { profile_ids: [7] }, collector_runs: run("running") },
      { source: "mercadolibre", make: null, model: null, body_type: "sedan", query: { profile_ids: [7] }, collector_runs: run("running") },
    ];
    // A source without targets by body type feeds these searches from its other targets: idle, not waiting.
    expect((await loadSearchCollection(byBody, "owner", sources))?.map((s) => s.collectionState)).toEqual(["done", "done"]);
    // And a model search never takes a body type target.
    mocks.targets = [{ source: "kavak", make: null, model: null, body_type: "suv", query: { profile_ids: [7] }, collector_runs: run("ok") }];
    expect((await loadSearchCollection(profile, "owner", sources))?.[0].collectionState).toBe("waiting");
  });
  it("keeps the inventory targets and leaves a search without vehicle nor body types unknown", async () => {
    mocks.targets = [
      { source: "kavak", make: null, model: null, body_type: null, query: { inventory: true, profile_ids: [7] }, collector_runs: run("running") },
    ];
    expect((await loadSearchCollection(byBody, "owner", sources))?.[0].collectionState).toBe("loading");
    mocks.admin.mockClear();
    const legacy = await loadSearchCollection({ ...profile, filters: {} }, "owner", sources);
    expect(legacy?.every((s) => s.collectionState === "unknown")).toBe(true);
    expect(mocks.admin).not.toHaveBeenCalled();
  });
});

describe("the zone notice's first reads (docs/AVISO_ZONA.md)", () => {
  const NOW = Date.parse("2026-10-06T12:10:00Z");
  const DAY = 24 * 3_600_000;
  const ago = (ms: number) => new Date(NOW - ms).toISOString();
  const run = (status: string, finished?: number, started?: number) =>
    ({ status, started_at: started == null ? null : ago(started), finished_at: finished == null ? null : ago(finished) });
  const firstRun = (...runs: ReturnType<typeof run>[]) => ({ first_run_done: false, last_run_at: null, collector_runs: runs });

  it("waits for a first run under way, or for one not started within five minutes of the search", () => {
    expect(onFirstRead(firstRun(run("running")), NOW - 60 * 60_000, NOW)).toBe(true);
    expect(onFirstRead(firstRun(), NOW - 60_000, NOW)).toBe(true);
    expect(onFirstRead(firstRun(), NOW - 6 * 60_000, NOW)).toBe(false);
    expect(onFirstRead(null, NOW - 60_000, NOW)).toBe(true);
    expect(onFirstRead(null, NOW - 6 * 60_000, NOW)).toBe(false);
  });
  it("waits a few minutes after a first run ends, while the worker matches its batch, and no longer", () => {
    expect(onFirstRead(firstRun(run("ok", 60_000)), NOW - 10 * 60_000, NOW)).toBe(true);
    // A partial read is matched too.
    expect(onFirstRead(firstRun(run("failed", 60_000)), NOW - 10 * 60_000, NOW)).toBe(true);
    expect(onFirstRead(firstRun(run("failed", 4 * 60_000)), NOW - 60_000, NOW)).toBe(false);
    // An empty first read keeps first_run_done off.
    expect(onFirstRead(firstRun(run("ok", 4 * 60_000)), NOW - 60_000, NOW)).toBe(false);
    expect(onFirstRead(firstRun(run("ok")), NOW - 60_000, NOW)).toBe(false);
  });
  it("never waits for a target read within a day of the search, whatever it runs now", () => {
    const read = { first_run_done: true, last_run_at: ago(2 * 3_600_000), collector_runs: [run("running", undefined, 30_000), run("ok", DAY, DAY)] };
    expect(onFirstRead(read, NOW - 60_000, NOW)).toBe(false);
    expect(staleAt(read, NOW - 60_000)).toBe(false);
    // A search days old: every run since it is routine.
    const routine = { ...read, collector_runs: [run("ok", 60_000, 2 * 60_000), run("ok", 2 * 3_600_000, 2 * 3_600_000)] };
    expect(onFirstRead(routine, NOW - 3 * DAY, NOW)).toBe(false);
    expect(staleAt(routine, NOW - 3 * DAY)).toBe(false);
  });
  it("waits for a target brought back after days inactive to read the market again", () => {
    // sync_targets keeps first_run_done and last_run_at: its last read is two weeks old.
    const old = run("ok", 14 * DAY, 14 * DAY + 60_000);
    const back = (...latest: ReturnType<typeof run>[]) => ({ first_run_done: true, last_run_at: ago(14 * DAY), collector_runs: [...latest, old].slice(0, 2) });
    // Its old read doesn't count: not started yet, five minutes at most.
    expect(onFirstRead(back(), NOW - 60_000, NOW)).toBe(true);
    expect(onFirstRead(back(), NOW - 6 * 60_000, NOW)).toBe(false);
    // Reading, and while its batch is matched.
    expect(onFirstRead(back(run("running", undefined, 30_000)), NOW - 60_000, NOW)).toBe(true);
    expect(onFirstRead(back(run("ok", 30_000, 50_000)), NOW - 60_000, NOW)).toBe(true);
    expect(staleAt(back(), NOW - 60_000)).toBe(true);
    // Done: last_run_at moved, and the run before tells it was stale (cold).
    const caught = { first_run_done: true, last_run_at: ago(5 * 60_000), collector_runs: [run("ok", 4 * 60_000, 5 * 60_000), old] };
    expect(onFirstRead(caught, NOW - 6 * 60_000, NOW)).toBe(false);
    expect(staleAt(caught, NOW - 6 * 60_000)).toBe(true);
    // The next run is routine.
    expect(staleAt({ ...caught, collector_runs: [run("running", undefined, 10_000), caught.collector_runs[0]] }, NOW - 6 * 60_000)).toBe(false);
    // An unreadable creation date counts as an old search.
    expect(staleAt(back(), Number.NEGATIVE_INFINITY)).toBe(false);
  });
  it("marks the sources still on a first read and the targets created with the search", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-10-06T12:02:00Z"));
    try {
      mocks.targets = [
        { source: "kavak", make: "Ford", model: "Fiesta", first_run_done: false, created_at: "2026-10-06T12:00:01Z", collector_runs: [{ status: "running", finished_at: null }] },
        { source: "mercadolibre", make: "Ford", model: "Fiesta", first_run_done: true, last_run_at: "2026-10-06T11:30:00Z", created_at: "2026-09-01T00:00:00Z", collector_runs: [{ status: "ok", finished_at: "2026-10-06T12:01:00Z" }] },
      ];
      const result = await loadSearchCollection(profile, "owner", sources);
      expect(result?.map((s) => [s.firstRead, s.newTarget])).toEqual([[true, true], [false, false]]);
      // A target brought back after two weeks inactive reads the market again: waited for, and cold.
      mocks.targets[1] = { ...mocks.targets[1], last_run_at: "2026-09-22T12:00:00Z", collector_runs: [{ status: "ok", started_at: "2026-09-22T12:00:00Z", finished_at: "2026-09-22T12:05:00Z" }] };
      expect((await loadSearchCollection(profile, "owner", sources))?.map((s) => [s.firstRead, s.newTarget])).toEqual([[true, true], [true, true]]);
      // No target linked yet: its first read is on the way while the search is new.
      mocks.targets = [];
      expect((await loadSearchCollection(profile, "owner", sources))?.map((s) => s.firstRead)).toEqual([true, true]);
      vi.setSystemTime(new Date("2026-10-06T12:06:00Z"));
      expect((await loadSearchCollection(profile, "owner", sources))?.map((s) => s.firstRead)).toEqual([false, false]);
    } finally {
      vi.useRealTimers();
    }
  });
});
