import type { MetadataRoute } from "next";

import { siteUrl } from "@/lib/env";

/** F7, punto 11: never indexed, for every crawler (admin, API, private user areas). */
const DISALLOW = ["/app", "/admin", "/r/", "/m/", "/api/", "/auth/", "/baja"];

/**
 * PAR-04 (GEO): the search and answer engines' crawlers, named so a default
 * that blocks AI crawlers never leaves the guides out of their answers.
 */
const AI_CRAWLERS = [
  "GPTBot",
  "OAI-SearchBot",
  "ChatGPT-User",
  "ClaudeBot",
  "Claude-SearchBot",
  "Claude-User",
  "PerplexityBot",
  "Perplexity-User",
  "Google-Extended",
  "Applebot-Extended",
  "CCBot",
  "Bingbot",
];

/** F7, punto 11: only the public pages are indexed; PAR-04: /guias and llms.txt explicitly. */
export default function robots(): MetadataRoute.Robots {
  const allow = ["/", "/guias", "/llms.txt", "/llms-full.txt"];
  return {
    rules: [
      { userAgent: "*", allow, disallow: DISALLOW },
      { userAgent: AI_CRAWLERS, allow, disallow: DISALLOW },
    ],
    sitemap: `${siteUrl}/sitemap.xml`,
  };
}
