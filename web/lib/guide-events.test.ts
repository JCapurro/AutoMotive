import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ createClient: vi.fn(), rpc: vi.fn() }));
vi.mock("@/lib/supabase/client", () => ({ createClient: mocks.createClient }));

/**
 * PAR-04 components/guides/guide-events.ts: the guide pages' events never
 * break the page, and GA4 gets nothing without the visitor's consent.
 */
async function load(gaId: string, cookie: string | null) {
  vi.resetModules();
  vi.stubEnv("NEXT_PUBLIC_GA4_ID", gaId);
  const gtag = vi.fn();
  vi.stubGlobal("window", { gtag });
  if (cookie === null) vi.stubGlobal("document", undefined);
  else vi.stubGlobal("document", { cookie });
  const events = await import("@/components/guides/guide-events");
  return { ...events, gtag };
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.createClient.mockReturnValue({ rpc: mocks.rpc });
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("guide events", () => {
  it("logGuideEvent calls log_guide_event with the slugs", async () => {
    mocks.rpc.mockResolvedValue({ data: null, error: null });
    const { logGuideEvent } = await load("", "");
    logGuideEvent("guide_viewed", "toyota", "corolla");
    expect(mocks.rpc).toHaveBeenCalledWith("log_guide_event", { p_name: "guide_viewed", p_slug_make: "toyota", p_slug_model: "corolla" });
  });

  it("a base without the RPC (a rejected call) or without Supabase never throws", async () => {
    const unhandled = vi.fn();
    process.on("unhandledRejection", unhandled);
    try {
      mocks.rpc.mockReturnValue(Promise.reject(new Error("Could not find the function public.log_guide_event")));
      const { logGuideEvent } = await load("", "");
      expect(() => logGuideEvent("guide_cta_clicked", "toyota", "corolla")).not.toThrow();
      mocks.createClient.mockImplementation(() => {
        throw new Error("Missing NEXT_PUBLIC_SUPABASE_URL");
      });
      expect(() => logGuideEvent("guide_questions_copied", "toyota", "corolla")).not.toThrow();
      await new Promise((resolve) => setTimeout(resolve, 10));
      expect(unhandled).not.toHaveBeenCalled();
    } finally {
      process.off("unhandledRejection", unhandled);
    }
  });

  it("guideViewItem sends a GA4 view_item only with consent", async () => {
    // «Rechazar» in the banner: nothing goes to GA4.
    const denied = await load("G-TEST", "px_q=1; ads_consent=denied");
    denied.guideViewItem("toyota", "corolla", "Toyota Corolla");
    expect(denied.gtag).not.toHaveBeenCalled();
    // No answer yet counts as granted (lib/meta-pixel.ts).
    const allowed = await load("G-TEST", "ads_consent=granted");
    allowed.guideViewItem("toyota", "corolla", "Toyota Corolla");
    expect(allowed.gtag).toHaveBeenCalledWith("event", "view_item", {
      items: [{ item_id: "guide:toyota/corolla", item_name: "Toyota Corolla", item_category: "guide" }],
    });
    // Without a GA4 id, or on the server (no document), nothing is sent.
    const noId = await load("", "");
    noId.guideViewItem("toyota", "corolla", "Toyota Corolla");
    expect(noId.gtag).not.toHaveBeenCalled();
    const server = await load("G-TEST", null);
    server.guideViewItem("toyota", "corolla", "Toyota Corolla");
    expect(server.gtag).not.toHaveBeenCalled();
  });
});
