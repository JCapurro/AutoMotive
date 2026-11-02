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
import * as actions from "@/app/app/listings/actions";
import { setSaved, setStatus } from "@/app/app/listings/actions";

describe("listing actions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mock.upsert.mockResolvedValue({ error: null });
    mock.before = { status: "seen", saved: false };
  });
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

describe("follow-up (X-01)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mock.upsert.mockResolvedValue({ error: null });
    mock.before = { status: "seen", saved: false };
  });
  it("never changes a purchased listing's status", async () => {
    mock.before = { status: "purchased", saved: true };
    await expect(setStatus(42, "contacted")).rejects.toThrow();
    expect(mock.upsert).not.toHaveBeenCalled();
  });
  it("still refuses Comprado and Nuevo through setStatus", async () => {
    await expect(setStatus(42, "purchased")).rejects.toThrow();
    await expect(setStatus(42, "new")).rejects.toThrow();
    expect(mock.upsert).not.toHaveBeenCalled();
  });
  it.each(["contacted", "visit_scheduled"] as const)("sets %s without touching saved", async (status) => {
    mock.before = { status: "interested", saved: true };
    await setStatus(42, status);
    const row = mock.upsert.mock.calls[0][0];
    expect(row).toEqual({ user_id: "user-1", listing_id: 42, status, rejection_reason: null });
    expect(row).not.toHaveProperty("saved");
    expect(mock.track).toHaveBeenCalledWith(expect.anything(), "user-1", "listing_status_changed", {
      listing_id: 42, status, from: "interested", via: "web",
    });
    expect(mock.track).not.toHaveBeenCalledWith(expect.anything(), "user-1", "listing_saved", expect.anything());
  });

  it("has no note action any more (Juan 02/11): nothing writes user_listing_interactions.note", () => {
    expect(actions).not.toHaveProperty("setNote");
  });
  it("setSaved reports listing_saved, so saving from a follow-up keeps the metric", async () => {
    await setSaved(42, true);
    expect(mock.upsert.mock.calls[0][0]).toEqual({ user_id: "user-1", listing_id: 42, saved: true });
    expect(mock.track).toHaveBeenCalledWith(expect.anything(), "user-1", "listing_saved", { listing_id: 42, saved: true });
  });
});
