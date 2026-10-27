import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ requireAdmin: vi.fn(), createAdminClient: vi.fn(), rpc: vi.fn(), from: vi.fn() }));
vi.mock("server-only", () => ({}));
vi.mock("@/lib/admin", () => ({ requireAdmin: mocks.requireAdmin }));
vi.mock("@/lib/supabase/admin", () => ({ createAdminClient: mocks.createAdminClient }));
import { loadAdminDashboard } from "./admin-dashboard-data";
import { getDashboardPeriod } from "./admin-dashboard";

function emptySnapshot() {
  const period = getDashboardPeriod("7", new Date("2026-10-27T12:00:00Z"));
  const metrics = { signups: 0, activationEligible: 0, activatedWithin24h: 0, activeUsers: 0,
    searchesCreated: 0, firstValueEligible: 0, firstValueUnobserved: 0, firstValueWithin24h: 0, firstValueMedianHours: null,
    grossRevenue: 0, refunds: 0, particularSales: 0, agencyPayments: 0, firstPayingUsers: 0 };
  return { ...period, firstValueTrackingSince: "2026-10-01T00:00:00Z", current: metrics, previous: metrics, daily: Array.from({ length: 7 }, (_, i) => ({
    day: new Date(Date.parse(period.start) + i * 86_400_000).toISOString().slice(0, 10),
    signups: 0, activeUsers: 0, searchesCreated: 0, grossRevenue: 0, refunds: 0,
  })), currentState: { enabledSearches: 0, searchesWithoutValue24h: 0, pendingNotifications: 0,
    failedNotifications: 0, pendingCheckouts: 0, checkoutSyncErrors: 0, agencyMonthlyEquivalent: 0, authorizedRecurringMrr: 0 } };
}

beforeEach(() => {
  vi.resetAllMocks();
  mocks.requireAdmin.mockResolvedValue({ id: "admin" });
  mocks.createAdminClient.mockReturnValue({ rpc: mocks.rpc, from: mocks.from });
  mocks.rpc.mockResolvedValue({ data: null, error: { message: "private SQL diagnostic" } });
  mocks.from.mockImplementation(() => {
    const query = { select: () => query, order: () => query, gte: () => query, lt: () => query,
      range: async () => ({ data: [], error: null }) };
    return query;
  });
});

describe("privileged dashboard loader", () => {
  it("requires admin before creating the service client", async () => {
    mocks.requireAdmin.mockRejectedValue(new Error("not-found"));
    await expect(loadAdminDashboard()).rejects.toThrow("not-found");
    expect(mocks.createAdminClient).not.toHaveBeenCalled();
  });
  it("keeps a database error separate from successful empty health sections", async () => {
    const result = await loadAdminDashboard("7", new Date("2026-10-27T12:00:00Z"));
    expect(result.metrics.data).toBeNull();
    expect(result.metrics.error).toContain("métricas");
    expect(result.metrics.error).not.toContain("private");
    expect(result.sources).toEqual({ data: [], error: null });
    expect(result.llm).toEqual({ data: [], error: null });
    expect(mocks.rpc).toHaveBeenCalledWith("admin_decision_metrics", {
      p_start: "2026-10-20T03:00:00.000Z", p_end: "2026-10-27T03:00:00.000Z", p_as_of: "2026-10-27T12:00:00.000Z",
    });
  });
  it("rejects an incomplete SQL snapshot instead of publishing zeros", async () => {
    mocks.rpc.mockResolvedValue({ data: { current: { signups: 0 } }, error: null });
    const result = await loadAdminDashboard();
    expect(result.metrics.data).toBeNull();
    expect(result.metrics.error).toBeTruthy();
  });
  it.each(["PGRST202", "42883"])("makes a missing metrics migration actionable: %s", async (code) => {
    mocks.rpc.mockResolvedValue({ data: null, error: { code, message: "private schema details" } });
    const result = await loadAdminDashboard();
    expect(result.metrics.error).toContain("migración admin_decision_metrics");
    expect(result.metrics.error).not.toContain("private");
  });
  it("accepts a complete validated empty snapshot", async () => {
    mocks.rpc.mockResolvedValue({ data: emptySnapshot(), error: null });
    const result = await loadAdminDashboard("7", new Date("2026-10-27T12:00:00Z"));
    expect(result.metrics.error).toBeNull();
    expect(result.metrics.data?.current.signups).toBe(0);
    expect(result.metrics.data?.daily).toHaveLength(7);
  });
  it("rejects a wrong window and missing daily observations", async () => {
    for (const data of [{ ...emptySnapshot(), start: "2026-10-19T03:00:00Z" },
      { ...emptySnapshot(), daily: emptySnapshot().daily.slice(1) }]) {
      mocks.rpc.mockResolvedValue({ data, error: null });
      const result = await loadAdminDashboard("7", new Date("2026-10-27T12:00:00Z"));
      expect(result.metrics.data).toBeNull();
      expect(result.metrics.error).toBeTruthy();
    }
  });
  it("reads every health aggregate even when the server caps pages below the requested size", async () => {
    const rows = Array.from({ length: 1001 }, (_, i) => ({ id: String(i), name: `source ${i}`, enabled: true,
      consecutive_failures: 0, last_ok_at: null, last_run_at: null, last_run_status: null, last_error: null,
      runs_24h: 0, failed_24h: 0 }));
    const range = vi.fn(async (start: number) => ({ data: rows.slice(start, start + 100), error: null, count: rows.length }));
    mocks.from.mockImplementation((name) => {
      const query = { select: () => query, order: () => query, gte: () => query, lt: () => query,
        range: name === "admin_source_health" ? range : async () => ({ data: [], error: null, count: 0 }) };
      return query;
    });
    const result = await loadAdminDashboard();
    expect(result.sources.error).toBeNull();
    expect(result.sources.data).toHaveLength(1001);
    expect(range).toHaveBeenCalledTimes(11);
  });
  it("keeps service client initialization failures visible in all blocks", async () => {
    mocks.createAdminClient.mockImplementation(() => { throw new Error("secret invalid key"); });
    const result = await loadAdminDashboard();
    for (const block of [result.metrics, result.sources, result.llm]) {
      expect(block.data).toBeNull();
      expect(block.error).toBeTruthy();
      expect(block.error).not.toContain("secret");
    }
  });
  it("reports a thrown source read without losing the other blocks", async () => {
    mocks.from.mockImplementation((name) => {
      if (name === "admin_source_health") throw new Error("network connection secret");
      const query = { select: () => query, order: () => query, gte: () => query, lt: () => query,
        range: async () => ({ data: [], error: null }) };
      return query;
    });
    const result = await loadAdminDashboard();
    expect(result.sources.data).toBeNull();
    expect(result.sources.error).toContain("fuentes");
    expect(result.sources.error).not.toContain("secret");
    expect(result.llm).toEqual({ data: [], error: null });
  });
});
