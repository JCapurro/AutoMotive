/**
 * Prueba gratis, paso 1 (docs/PRUEBA_HONESTA.md): app_config.trial_reserve,
 * the switch that keeps room in the trial for listings new during it. On,
 * what was already published takes at most backfill_max of the trial's
 * results (the database applies it: admit_free_result). It ships off.
 */
export type TrialReserveConfig = { enabled: boolean; backfillMax: number };

/** On only with `enabled` explicitly true and a whole backfill_max from 0, as the database reads it; anything else, off. */
export function trialReserveConfig(raw: unknown): TrialReserveConfig {
  const value = raw !== null && typeof raw === "object" && !Array.isArray(raw) ? (raw as Record<string, unknown>) : {};
  const max = value.backfill_max;
  const valid = typeof max === "number" && Number.isFinite(max) && max >= 0;
  return { enabled: value.enabled === true && valid, backfillMax: valid ? Math.floor(max) : 0 };
}
