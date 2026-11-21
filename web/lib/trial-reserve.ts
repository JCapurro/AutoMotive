/**
 * Prueba gratis (docs/PRUEBA_HONESTA.md): app_config.trial_reserve, read here,
 * the switch that keeps room in the trial for listings new during it. On,
 * what was already published takes at most backfill_max of the trial's
 * results (the database applies it: admit_free_result). It ships off.
 *
 * Two optional fields, read only with the reserve on (docs/PRUEBA_COMPLETA.md):
 *   - random_stock: the first run's stock is a random sample, not the newest;
 *   - notice_since: ISO timestamp; with it the trial is in "notice mode": it is
 *     told as its 50 publicaciones, and when they are used the results page
 *     shows the complete pop-up and trial_complete goes to trials started since.
 */
export type TrialReserveConfig = {
  enabled: boolean; backfillMax: number;
  randomStock: boolean;
  /** notice_since when it parses, with the reserve on; null otherwise. */
  noticeSince: string | null;
};

/**
 * On only with `enabled` explicitly true and a whole backfill_max from 0, as
 * the database reads it; anything else, off. The optional fields follow the
 * same rule: a broken value is off (no sample, no notice mode).
 */
export function trialReserveConfig(raw: unknown): TrialReserveConfig {
  const value = raw !== null && typeof raw === "object" && !Array.isArray(raw) ? (raw as Record<string, unknown>) : {};
  const max = value.backfill_max;
  const valid = typeof max === "number" && Number.isFinite(max) && max >= 0;
  const enabled = value.enabled === true && valid;
  const since = typeof value.notice_since === "string" && !Number.isNaN(Date.parse(value.notice_since)) ? value.notice_since : null;
  return {
    enabled,
    backfillMax: valid ? Math.floor(max) : 0,
    randomStock: enabled && value.random_stock === true,
    noticeSince: enabled ? since : null,
  };
}

/** Notice mode (docs/PRUEBA_COMPLETA.md): the reserve on with a readable notice_since. The one test for every web surface. */
export function trialNoticeMode(config: TrialReserveConfig | null | undefined): boolean {
  return config?.enabled === true && config.noticeSince != null;
}
