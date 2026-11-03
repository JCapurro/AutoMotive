import { describe, expect, it } from "vitest";
import { trialReserveConfig } from "./trial-reserve";

describe("the trial reserve's switch (app_config.trial_reserve)", () => {
  it("is on only with enabled true and a backfill_max from 0, as the database reads it", () => {
    expect(trialReserveConfig({ enabled: true, backfill_max: 30 })).toEqual({ enabled: true, backfillMax: 30 });
    expect(trialReserveConfig({ enabled: true, backfill_max: 0 })).toEqual({ enabled: true, backfillMax: 0 });
    expect(trialReserveConfig({ enabled: true, backfill_max: 30.7 })).toEqual({ enabled: true, backfillMax: 30 });
    expect(trialReserveConfig({ enabled: false, backfill_max: 30 })).toEqual({ enabled: false, backfillMax: 30 });
  });
  it.each([undefined, null, {}, { enabled: true }, { enabled: true, backfill_max: -1 }, { enabled: true, backfill_max: "30" },
    { enabled: "true", backfill_max: 30 }, [true], true])("is off for %j", (raw) => {
    expect(trialReserveConfig(raw).enabled).toBe(false);
  });
});
