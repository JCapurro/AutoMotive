import { beforeEach, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ requireAdmin: vi.fn(), client: vi.fn(), read: vi.fn(), rpc: vi.fn(), refresh: vi.fn() }));
vi.mock("next/cache", () => ({ refresh: mocks.refresh }));
vi.mock("@/lib/admin", () => ({ requireAdmin: mocks.requireAdmin }));
vi.mock("@/lib/supabase/admin", () => ({ createAdminClient: mocks.client }));
import { updateConfig, updateSource } from "@/app/admin/actions";
import { DEFAULT_PRO_OFFER } from "@/lib/pro";

beforeEach(() => {
  vi.clearAllMocks();
  mocks.requireAdmin.mockResolvedValue({ id: "session-admin", email: "trusted@example.com" });
  mocks.read.mockResolvedValue({ data: { value: { x: 1 } }, error: null });
  mocks.rpc.mockResolvedValue({ data: 5, error: null });
  mocks.client.mockReturnValue({ rpc: mocks.rpc, from: vi.fn(() => ({ select: vi.fn(() => ({ eq: vi.fn(() => ({ maybeSingle: mocks.read })) })) })) });
});

it("uses the session actor and one atomic RPC for config, without a separate update", async () => {
  expect(await updateConfig("existing", '{"x":2}', { x: 1 })).toEqual({ ok: true });
  expect(mocks.rpc).toHaveBeenCalledExactlyOnceWith("admin_update_setting", { p_target_type: "app_config", p_target_key: "existing", p_expected: { x: 1 }, p_value: { x: 2 }, p_actor_id: "session-admin" });
  expect(mocks.refresh).toHaveBeenCalledOnce();
});
it("rejects stale config before RPC and detects a race from the locked comparison", async () => {
  expect(await updateConfig("existing", '{"x":2}', { x: 0 })).toHaveProperty("error", expect.stringMatching(/Otra persona/));
  expect(mocks.rpc).not.toHaveBeenCalled();
  mocks.rpc.mockResolvedValue({ error: { message: "setting_conflict" } });
  expect(await updateConfig("existing", '{"x":2}', { x: 1 })).toHaveProperty("error", expect.stringMatching(/Otra persona/));
  expect(mocks.refresh).not.toHaveBeenCalled();
});
it("does not report success when audit fails", async () => {
  mocks.rpc.mockResolvedValue({ error: { message: "audit insert failed" } });
  const result = await updateConfig("existing", '{"x":2}', { x: 1 });
  expect(result.ok).toBeUndefined();
  expect(result.error).toMatch(/historial/);
  expect(mocks.refresh).not.toHaveBeenCalled();
});
it("requires admin before reading or writing either action", async () => {
  mocks.requireAdmin.mockRejectedValue(new Error("not found"));
  await expect(updateConfig("existing", "{}", {})).rejects.toThrow("not found");
  await expect(updateSource({})).rejects.toThrow("not found");
  expect(mocks.client).not.toHaveBeenCalled();
});
it("rejects malformed, null, protected, missing and invalid known config", async () => {
  for (const text of ["{", "null", "[]", '{"overflow":1e999}']) expect(await updateConfig("existing", text, { x: 1 })).toHaveProperty("error");
  expect(await updateConfig("commercial_pilot", "{}", {})).toHaveProperty("error");
  mocks.read.mockResolvedValue({ data: { value: DEFAULT_PRO_OFFER }, error: null });
  expect(await updateConfig("pro_offer", JSON.stringify({ ...DEFAULT_PRO_OFFER, pass_30: { ...DEFAULT_PRO_OFFER.pass_30, amount: 1 } }), DEFAULT_PRO_OFFER)).toHaveProperty("error", expect.stringMatching(/versión/));
  mocks.read.mockResolvedValue({ data: null, error: { message: "read failed" } });
  expect(await updateConfig("existing", "{}", {})).toHaveProperty("error", expect.stringMatching(/leer/));
  mocks.read.mockResolvedValue({ data: null, error: null });
  expect(await updateConfig("missing", "{}", {})).toHaveProperty("error", expect.stringMatching(/no existe/));
  expect(mocks.rpc).not.toHaveBeenCalled();
});
it("keeps exact source cadence and sends previous fields for concurrency", async () => {
  const input = { id: "source", enabled: false, crawl_interval_seconds: 125, expected: { enabled: true, crawl_interval_seconds: 123 } };
  expect(await updateSource(input)).toEqual({ ok: true });
  expect(mocks.rpc).toHaveBeenCalledExactlyOnceWith("admin_update_setting", { p_target_type: "sources", p_target_key: "source", p_value: { enabled: false, crawl_interval_seconds: 125 }, p_expected: input.expected, p_actor_id: "session-admin" });
});
it("rejects invalid sources and exposes stale source writes", async () => {
  expect(await updateSource({ id: "source", enabled: true, crawl_interval_seconds: 60 })).toHaveProperty("error");
  expect(mocks.rpc).not.toHaveBeenCalled();
  mocks.rpc.mockResolvedValue({ error: { message: "setting_conflict" } });
  expect(await updateSource({ id: "source", enabled: true, crawl_interval_seconds: 60, expected: { enabled: true, crawl_interval_seconds: 120 } })).toHaveProperty("error", expect.stringMatching(/Otra persona/));
  expect(mocks.refresh).not.toHaveBeenCalled();
});
