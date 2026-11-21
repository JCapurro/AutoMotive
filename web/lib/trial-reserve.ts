/**
 * Prueba gratis, paso 1 (docs/PRUEBA_HONESTA.md): app_config.trial_reserve,
 * the switch that keeps room in the trial for listings new during it. On,
 * what was already published takes at most backfill_max of the trial's
 * results (the database applies it: admit_free_result). It ships off.
 *
 * «40 + N» (docs/PRUEBA_COMPLETA.md) adds three optional fields, read only
 * with the reserve on:
 *   - new_max: the cap on new results; with it the trial is in "new mode" and
 *     completes when the cap is reached;
 *   - random_stock: the first run's stock is a random sample, not the newest;
 *   - notice_since: the trial_complete email goes to trials started since
 *     (the worker's; the web only shows it in /admin/config).
 */
export type TrialReserveConfig = {
  enabled: boolean; backfillMax: number;
  /** The cap on new results, or null (no cap: legacy mode). */
  newMax: number | null;
  randomStock: boolean;
  noticeSince: string | null;
};

const wholeFromZero = (n: unknown): n is number => typeof n === "number" && Number.isFinite(n) && n >= 0;

/**
 * On only with `enabled` explicitly true and a whole backfill_max from 0, as
 * the database reads it; anything else, off. The new fields follow the same
 * rule: a broken value is off (no cap, no sample, no notice).
 */
export function trialReserveConfig(raw: unknown): TrialReserveConfig {
  const value = raw !== null && typeof raw === "object" && !Array.isArray(raw) ? (raw as Record<string, unknown>) : {};
  const max = value.backfill_max;
  const valid = wholeFromZero(max);
  const enabled = value.enabled === true && valid;
  const since = typeof value.notice_since === "string" && !Number.isNaN(Date.parse(value.notice_since)) ? value.notice_since : null;
  return {
    enabled,
    backfillMax: valid ? Math.floor(max) : 0,
    newMax: enabled && wholeFromZero(value.new_max) ? Math.floor(value.new_max) : null,
    randomStock: enabled && value.random_stock === true,
    noticeSince: enabled && wholeFromZero(value.new_max) ? since : null,
  };
}
