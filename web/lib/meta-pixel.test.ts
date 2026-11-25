import { expect, it, vi } from "vitest";

import { trackingAllowed, untrackedPath } from "@/lib/meta-pixel";

it("tracks by default, before the visitor answers the banner", () => {
  expect(trackingAllowed("")).toBe(true);
  expect(trackingAllowed("sb-auth=x; px_q=%5B%5D")).toBe(true);
  expect(trackingAllowed("ads_consent=granted")).toBe(true);
});

it("stops every platform once the visitor rejects", () => {
  expect(trackingAllowed("ads_consent=denied")).toBe(false);
  expect(trackingAllowed("sb-auth=x; ads_consent=denied; px_q=%5B%5D")).toBe(false);
});

it("keeps tracking off the pages whose URL carries a secret", () => {
  expect(untrackedPath("/auth/confirm-email")).toBe(true);
  expect(untrackedPath("/auth/reset-password")).toBe(true);
  expect(untrackedPath("/baja")).toBe(true);
  expect(untrackedPath("/")).toBe(false);
  expect(untrackedPath("/app/searches/new")).toBe(false);
  expect(untrackedPath("/bajas")).toBe(false);
});

it("sends the payment screen as a custom event, one id per surface and search", async () => {
  vi.resetModules();
  vi.stubEnv("NEXT_PUBLIC_META_PIXEL_ID", "123");
  const fbq = vi.fn();
  vi.stubGlobal("window", { fbq, setTimeout });
  try {
    const { paywallPixel } = await import("@/lib/meta-pixel");
    paywallPixel("sheet", 42);
    paywallPixel("quota_popup", 7);
    expect(fbq).toHaveBeenNthCalledWith(1, "trackCustom", "PaywallViewed", { content_name: "sheet" }, { eventID: "paywall:sheet:42" });
    expect(fbq).toHaveBeenNthCalledWith(2, "trackCustom", "PaywallViewed", { content_name: "quota_popup" }, { eventID: "paywall:quota_popup:7" });
  } finally {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
    vi.resetModules();
  }
});
