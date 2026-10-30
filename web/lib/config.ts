import "server-only";

import { cache } from "react";

import { listingTrackingConfig } from "@/lib/listing-tracking";
import { type PlanLimitsConfig, planLimits, type ProOffer, proOffer } from "@/lib/pro";
import { type RiskConfig, riskConfig } from "@/lib/risk-checklist";
import { createAdminClient } from "@/lib/supabase/admin";
import { paymentsEnabled } from "@/lib/mercadopago-server";

/**
 * app_config is server-only (sección 4.4): read with the service role. Only
 * the few values the web shows are exposed, with the seed's defaults.
 */
export type WebConfig = {
  minComparables: number;
  /** public.comparables' pool (seed: ±1 año, ±25% km, últimos 30 días). */
  comparables: { yearTol: number; kmTolPct: number; maxAgeDays: number };
  watchlistStaleDays: number;
  proOffer: ProOffer;
  /** app_config.plan_limits: what each plan includes, as the database applies it. */
  planLimits: PlanLimitsConfig;
  commercialPilot: boolean;
  automaticPayments: boolean;
  /** app_config.email_only_signup: the free search's email-only accounts and their brakes. */
  emailOnlySignup: EmailOnlySignup;
  /** app_config.listing_tracking (X-01): the private note's length limit. */
  listingTracking: { noteMaxChars: number };
  /** app_config.risk (PAR-02): the «Antes de señar» checklist switch and its official links (none until Juan loads them). */
  risk: RiskConfig;
};

export type EmailOnlySignup = {
  enabled: boolean;
  perIpHour: number;
  perDay: number;
  linksPerUserHour: number;
  linksPerIpHour: number;
  lookupsPerIpHour: number;
  /** Sessions a signed email link may start per account and hour (lib/alert-session.ts); 0 turns them off. */
  alertSessionsPerUserHour: number;
};

/** Missing or malformed values fall back to the migration's defaults; enabled only when explicitly true. */
export function emailOnlySignup(raw: unknown): EmailOnlySignup {
  const value = (raw ?? {}) as Record<string, unknown>;
  const count = (key: string, fallback: number) => {
    const n = Number(value[key] ?? fallback);
    return Number.isFinite(n) && n >= 0 ? Math.floor(n) : fallback;
  };
  return {
    enabled: value.enabled === true,
    perIpHour: count("per_ip_hour", 10),
    perDay: count("per_day", 100),
    linksPerUserHour: count("links_per_user_hour", 3),
    linksPerIpHour: count("links_per_ip_hour", 20),
    lookupsPerIpHour: count("lookups_per_ip_hour", 30),
    alertSessionsPerUserHour: count("alert_sessions_per_user_hour", 10),
  };
}

export const webConfig = cache(async (): Promise<WebConfig> => {
  const { data } = await createAdminClient()
    .from("app_config")
    .select("key, value")
    .in("key", ["comparables", "watchlist_stale_days", "pro_offer", "commercial_pilot", "plan_limits", "alerts_max_per_user_day", "email_only_signup", "listing_tracking", "risk"]);
  const values = Object.fromEntries((data ?? []).map((row) => [row.key, row.value]));
  const comparables = (values.comparables ?? {}) as { min_n?: number; year_tol?: number; km_tol_pct?: number; max_age_days?: number };
  return {
    minComparables: Number(comparables.min_n ?? 5),
    comparables: {
      yearTol: Number(comparables.year_tol ?? 1),
      kmTolPct: Number(comparables.km_tol_pct ?? 25),
      maxAgeDays: Number(comparables.max_age_days ?? 30),
    },
    watchlistStaleDays: Number(values.watchlist_stale_days ?? 30),
    proOffer: proOffer(values.pro_offer),
    planLimits: planLimits(values.plan_limits, Number(values.alerts_max_per_user_day ?? 10)),
    commercialPilot: (values.commercial_pilot as { enabled?: boolean } | undefined)?.enabled === true,
    automaticPayments: paymentsEnabled() && (values.commercial_pilot as { enabled?: boolean } | undefined)?.enabled === true,
    emailOnlySignup: emailOnlySignup(values.email_only_signup),
    listingTracking: listingTrackingConfig(values.listing_tracking),
    risk: riskConfig(values.risk),
  };
});
