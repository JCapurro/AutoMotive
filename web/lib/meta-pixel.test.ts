import { expect, it } from "vitest";

import { trackingAllowed } from "@/lib/meta-pixel";

it("tracks by default, before the visitor answers the banner", () => {
  expect(trackingAllowed("")).toBe(true);
  expect(trackingAllowed("sb-auth=x; px_q=%5B%5D")).toBe(true);
  expect(trackingAllowed("ads_consent=granted")).toBe(true);
});

it("stops every platform once the visitor rejects", () => {
  expect(trackingAllowed("ads_consent=denied")).toBe(false);
  expect(trackingAllowed("sb-auth=x; ads_consent=denied; px_q=%5B%5D")).toBe(false);
});
