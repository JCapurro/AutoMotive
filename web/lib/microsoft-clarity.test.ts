import { afterEach, expect, it, vi } from "vitest";

import { syncClarityConsent } from "@/lib/microsoft-clarity";

afterEach(() => vi.unstubAllGlobals());

it("grants both consent signals when recording starts", () => {
  const clarity = vi.fn();
  vi.stubGlobal("window", { clarity });
  syncClarityConsent(true);
  expect(clarity.mock.calls.map(([command]) => command)).toEqual(["start", "consentv2"]);
  expect(clarity).toHaveBeenLastCalledWith("consentv2", {
    ad_Storage: "granted", analytics_Storage: "granted",
  });
});

it("revokes storage and stops recording instead of continuing in cookieless mode", () => {
  const clarity = vi.fn();
  vi.stubGlobal("window", { clarity });
  syncClarityConsent(false);
  expect(clarity.mock.calls).toEqual([
    ["consentv2", { ad_Storage: "denied", analytics_Storage: "denied" }],
    ["stop"],
  ]);
});

it("does not initialize Clarity when the tag has not loaded", () => {
  const browserWindow = {};
  vi.stubGlobal("window", browserWindow);
  expect(() => syncClarityConsent(false)).not.toThrow();
  expect(browserWindow).not.toHaveProperty("clarity");
});
