import { describe, expect, it } from "vitest";

import { bonusTrial } from "./bonus-trial";

describe("bonusTrial", () => {
  it("reads the three states", () => {
    expect(bonusTrial({ state: "active", ends_at: "2026-11-02T22:00:00+00:00" }))
      .toEqual({ state: "active", endsAt: "2026-11-02T22:00:00+00:00" });
    expect(bonusTrial({ state: "available", days: 7 })).toEqual({ state: "available", endsAt: null });
    expect(bonusTrial({ state: "unavailable" })).toEqual({ state: "unavailable", endsAt: null });
  });

  it("takes anything else as unavailable", () => {
    expect(bonusTrial(null)).toEqual({ state: "unavailable", endsAt: null });
    expect(bonusTrial({ state: "pending", ends_at: "x" })).toEqual({ state: "unavailable", endsAt: null });
  });
});
