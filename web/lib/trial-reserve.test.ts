import { describe, expect, it } from "vitest";
import { trialNoticeMode, trialReserveConfig } from "./trial-reserve";

describe("the trial reserve's switch (app_config.trial_reserve)", () => {
  it("is on only with enabled true and a backfill_max from 0, as the database reads it", () => {
    expect(trialReserveConfig({ enabled: true, backfill_max: 30 })).toEqual({ enabled: true, backfillMax: 30, randomStock: false, noticeSince: null });
    expect(trialReserveConfig({ enabled: true, backfill_max: 0 })).toEqual({ enabled: true, backfillMax: 0, randomStock: false, noticeSince: null });
    expect(trialReserveConfig({ enabled: true, backfill_max: 30.7 })).toEqual({ enabled: true, backfillMax: 30, randomStock: false, noticeSince: null });
    expect(trialReserveConfig({ enabled: false, backfill_max: 30 })).toEqual({ enabled: false, backfillMax: 30, randomStock: false, noticeSince: null });
  });
  it.each([undefined, null, {}, { enabled: true }, { enabled: true, backfill_max: -1 }, { enabled: true, backfill_max: "30" },
    { enabled: "true", backfill_max: 30 }, [true], true])("is off for %j", (raw) => {
    expect(trialReserveConfig(raw).enabled).toBe(false);
  });
  it("reads random_stock and notice_since only with the reserve on; notice mode needs both", () => {
    const since = "2026-11-21T12:00:00Z";
    expect(trialReserveConfig({ enabled: true, backfill_max: 45, random_stock: true, notice_since: since }))
      .toEqual({ enabled: true, backfillMax: 45, randomStock: true, noticeSince: since });
    expect(trialReserveConfig({ enabled: false, backfill_max: 45, random_stock: true, notice_since: since }))
      .toEqual({ enabled: false, backfillMax: 45, randomStock: false, noticeSince: null });
    expect(trialReserveConfig({ enabled: true, backfill_max: 45, random_stock: "true", notice_since: "mañana" }))
      .toEqual({ enabled: true, backfillMax: 45, randomStock: false, noticeSince: null });
    expect(trialNoticeMode(trialReserveConfig({ enabled: true, backfill_max: 45, notice_since: since }))).toBe(true);
    expect(trialNoticeMode(trialReserveConfig({ enabled: true, backfill_max: 30 }))).toBe(false);
    expect(trialNoticeMode(trialReserveConfig({ enabled: false, backfill_max: 30, notice_since: since }))).toBe(false);
    expect(trialNoticeMode(null)).toBe(false);
  });
});
