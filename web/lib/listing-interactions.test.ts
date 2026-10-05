import { beforeEach, describe, expect, it, vi } from "vitest";

const mock = vi.hoisted(() => ({
  upsert: vi.fn(),
  before: { status: "seen", saved: false },
  track: vi.fn(),
  refresh: vi.fn(),
}));
vi.mock("@/lib/auth", () => ({ requireUser: async () => ({ id: "user-1" }) }));
vi.mock("next/cache", () => ({ refresh: mock.refresh }));
vi.mock("@/lib/events", () => ({ track: mock.track }));
vi.mock("@/lib/supabase/server", () => ({ createClient: async () => ({
  from: () => ({
    select: () => ({ eq: () => ({ maybeSingle: async () => ({ data: mock.before }) }) }),
    upsert: mock.upsert,
  }),
}) }));
import { setStatus } from "@/app/app/listings/actions";

describe("listing actions", () => {
  beforeEach(() => { vi.clearAllMocks(); mock.upsert.mockResolvedValue({ error: null }); });
  it("saves Me interesa atomically with its status", async () => {
    await setStatus(42, "interested");
    expect(mock.upsert).toHaveBeenCalledExactlyOnceWith(
      { user_id: "user-1", listing_id: 42, status: "interested", rejection_reason: null, saved: true },
      { onConflict: "user_id,listing_id" },
    );
    expect(mock.track).toHaveBeenCalledWith(expect.anything(), "user-1", "listing_saved", { listing_id: 42, saved: true });
    expect(mock.refresh).toHaveBeenCalledOnce();
  });
  it("removes a discarded listing from saved listings", async () => {
    await setStatus(42, "discarded", "too_expensive");
    expect(mock.upsert.mock.calls[0][0]).toMatchObject({ status: "discarded", saved: false, rejection_reason: "too_expensive" });
  });
  it("does not report success or refresh after a failed write", async () => {
    mock.upsert.mockResolvedValue({ error: { message: "write failed" } });
    await expect(setStatus(42, "interested")).rejects.toThrow("write failed");
    expect(mock.refresh).not.toHaveBeenCalled();
    expect(mock.track).not.toHaveBeenCalled();
  });
});
