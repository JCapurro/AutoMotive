import type { MetadataRoute } from "next";

import { siteUrl } from "@/lib/env";

/** F7, punto 11: the landing and the pages anyone can read. */
export default function sitemap(): MetadataRoute.Sitemap {
  return [
    { url: `${siteUrl}/`, changeFrequency: "weekly", priority: 1 },
    { url: `${siteUrl}/login`, changeFrequency: "yearly", priority: 0.5 },
    { url: `${siteUrl}/privacidad`, changeFrequency: "yearly", priority: 0.2 },
    { url: `${siteUrl}/terminos`, changeFrequency: "yearly", priority: 0.2 },
  ];
}
