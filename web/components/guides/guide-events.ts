"use client";

import { analyticsEvent } from "@/lib/google-analytics";
import { createClient } from "@/lib/supabase/client";

export type GuideEventName = "guide_viewed" | "guide_cta_clicked" | "guide_questions_copied";

/**
 * PAR-04: the guide pages are static, so their events leave from the browser
 * (log_guide_event, signed in or not; a base without the RPC or a cap reached
 * says nothing). Never breaks the page.
 */
export function logGuideEvent(name: GuideEventName, slugMake: string, slugModel: string): void {
  try {
    void createClient()
      .rpc("log_guide_event", { p_name: name, p_slug_make: slugMake, p_slug_model: slugModel })
      .then(() => undefined, () => undefined);
  } catch {
    // No Supabase in this browser: the event is lost, the page works.
  }
}

/** GA4 view_item of a guide (with the visitor's consent, like every analyticsEvent). */
export function guideViewItem(slugMake: string, slugModel: string, name: string): void {
  analyticsEvent("view_item", {
    items: [{ item_id: `guide:${slugMake}/${slugModel}`, item_name: name, item_category: "guide" }],
  });
}
