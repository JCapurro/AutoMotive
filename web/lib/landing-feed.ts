import "server-only";

import { unstable_cache } from "next/cache";

import { type LandingFeed, parseLandingFeed } from "@/lib/landing-hero";
import { createAdminClient } from "@/lib/supabase/admin";

/**
 * public.landing_feed (service role), shared by every visit for ten minutes:
 * the home is rendered per request and this is the same for everyone. A
 * failed read throws inside the cache, so it is never kept.
 */
const cachedFeed = unstable_cache(
  async (): Promise<LandingFeed> => {
    const { data, error } = await createAdminClient().rpc("landing_feed");
    if (error) throw new Error(`landing_feed: ${error.message}`);
    return parseLandingFeed(data);
  },
  ["landing-feed"],
  { revalidate: 600 },
);

/** null when it can't be read (a base without the migration included): the hero falls back to its fixed example and models. */
export async function landingFeed(): Promise<LandingFeed | null> {
  try {
    return await cachedFeed();
  } catch {
    return null;
  }
}
