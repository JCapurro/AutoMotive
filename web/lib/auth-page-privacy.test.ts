import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it, vi } from "vitest";
const route = vi.hoisted(() => ({ pathname: "/auth/confirm-email", search: "token_hash=private" }));
vi.mock("next/navigation", () => ({ usePathname: () => route.pathname, useSearchParams: () => new URLSearchParams(route.search) }));
vi.mock("@/lib/google-analytics", () => ({ googleAnalyticsId: "G-TEST", hasAnalyticsConsent: () => true }));
vi.mock("@/lib/meta-pixel", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/meta-pixel")>()), metaPixelId: "123", pixel: vi.fn() }));
import { GoogleAnalytics } from "@/components/google-analytics";
import { MetaPixel } from "@/components/meta-pixel";
it.each([
  ["/auth/confirm-email", "token_hash=private"],
  ["/baja", "t=private-unsubscribe-token"],
])("does not load third-party tracking on %s, whose URL carries a token", (pathname, search) => {
  Object.assign(route, { pathname, search });
  expect(renderToStaticMarkup(createElement(GoogleAnalytics))).toBe("");
  expect(renderToStaticMarkup(createElement(MetaPixel))).toBe("");
});