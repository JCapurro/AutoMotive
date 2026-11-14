"use client";

import { analyticsEvent } from "@/lib/google-analytics";
import type { HeroVariant } from "@/lib/landing-hero";
import { createClient } from "@/lib/supabase/client";

export type LandingEventName = "landing_viewed" | "landing_search_started" | "landing_dialog_opened";
/** What started the search: a model chip, «Otro», typing, a row of the feed. */
export type LandingHow = "model" | "other" | "typed" | "row";

/**
 * The home's events (log_landing_event, signed in or not): what the two heroes
 * are compared with. Like the guides' (components/guides/guide-events.ts), a
 * base without the RPC or a cap reached says nothing, and it never breaks the
 * page. GA4 gets the same event, with the visitor's consent.
 */
export function logLandingEvent(name: LandingEventName, variant: HeroVariant, how?: LandingHow): void {
  analyticsEvent(name, { variant, ...(how ? { how } : {}) });
  try {
    void createClient()
      .rpc("log_landing_event", { p_name: name, p_variant: variant, ...(how ? { p_how: how } : {}) })
      .then(() => undefined, () => undefined);
  } catch {
    // No Supabase in this browser: the event is lost, the page works.
  }
}
