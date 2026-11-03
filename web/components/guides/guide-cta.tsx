"use client";

import { logGuideEvent } from "@/components/guides/guide-events";
import { LandingSearch } from "@/components/landing-search";

/**
 * «Crear mi búsqueda» with the guide's model prefilled. The session is read in
 * the browser: signed out it opens the same email-only signup as the landing,
 * signed in it goes to /app/searches/new?prompt=… (the assisted mode).
 */
export function GuideCta({ prompt, slugMake, slugModel }: { prompt: string; slugMake: string; slugModel: string }) {
  return <LandingSearch initialText={prompt} onStart={() => logGuideEvent("guide_cta_clicked", slugMake, slugModel)} />;
}
