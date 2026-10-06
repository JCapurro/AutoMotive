import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it, vi } from "vitest";
vi.mock("next/navigation", () => ({ usePathname: () => "/auth/confirm-email", useSearchParams: () => new URLSearchParams("token_hash=private") }));
vi.mock("@/lib/google-analytics", () => ({ googleAnalyticsId: "G-TEST", GA_CONSENT_COOKIE: "ga_consent", hasAnalyticsConsent: () => true }));
vi.mock("@/lib/meta-pixel", () => ({ metaPixelId: "123", CONSENT_COOKIE: "ads_consent", PIXEL_QUEUE_COOKIE: "px_q", pixel: vi.fn() }));
import { GoogleAnalytics } from "@/components/google-analytics";
import { MetaPixel } from "@/components/meta-pixel";
it("does not load third-party tracking on pages containing confirmation tokens", () => {
  expect(renderToStaticMarkup(createElement(GoogleAnalytics))).toBe("");
  expect(renderToStaticMarkup(createElement(MetaPixel))).toBe("");
});
