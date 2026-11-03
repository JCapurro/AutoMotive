import type { MetadataRoute } from "next";

import { siteUrl } from "@/lib/env";
import { guidePath } from "@/lib/guides";
import { publishedGuideIndex } from "@/lib/guides-data";

// PAR-04: the published guides change without a deploy (revalidatePath on publishing).
export const revalidate = 3600;

const STATIC: MetadataRoute.Sitemap = [
  { url: `${siteUrl}/`, changeFrequency: "weekly", priority: 1 },
  { url: `${siteUrl}/planes`, changeFrequency: "monthly", priority: 0.8 },
  { url: `${siteUrl}/login`, changeFrequency: "yearly", priority: 0.5 },
  { url: `${siteUrl}/privacidad`, changeFrequency: "yearly", priority: 0.2 },
  { url: `${siteUrl}/terminos`, changeFrequency: "yearly", priority: 0.2 },
];

/** F7, punto 11: the landing and the pages anyone can read; PAR-04: /guias and each published guide. */
export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  let guides: Awaited<ReturnType<typeof publishedGuideIndex>> = [];
  try {
    guides = await publishedGuideIndex();
  } catch {
    // A database problem never takes the sitemap down: the static entries stay.
    return STATIC;
  }
  return [
    ...STATIC,
    { url: `${siteUrl}/guias`, changeFrequency: "weekly", priority: 0.6 },
    ...guides.map((g) => ({
      url: `${siteUrl}${guidePath(g.slugMake, g.slugModel)}`,
      lastModified: g.updatedAt,
      changeFrequency: "monthly" as const,
      priority: 0.5,
    })),
  ];
}
