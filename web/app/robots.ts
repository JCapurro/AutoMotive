import type { MetadataRoute } from "next";

import { siteUrl } from "@/lib/env";

/** F7, punto 11: only the public pages are indexed. */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: { userAgent: "*", allow: "/", disallow: ["/app", "/admin", "/r/", "/api/", "/auth/", "/baja"] },
    sitemap: `${siteUrl}/sitemap.xml`,
  };
}
