import type { MetadataRoute } from "next";

import { siteUrl } from "@/lib/env";
import { guidePath, makePath, METHOD_PATH } from "@/lib/guides";
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

/** The newest of some ISO dates (undefined without any). */
function latest(dates: string[]): string | undefined {
  return [...dates].sort().at(-1);
}

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
    { url: `${siteUrl}/guias`, lastModified: latest(guides.map((g) => g.updatedAt)), changeFrequency: "weekly", priority: 0.6 },
    { url: `${siteUrl}${METHOD_PATH}`, changeFrequency: "yearly", priority: 0.3 },
    // One page per make: its date is its newest model's.
    ...[...new Set(guides.map((g) => g.slugMake))].map((slugMake) => ({
      url: `${siteUrl}${makePath(slugMake)}`,
      lastModified: latest(guides.filter((g) => g.slugMake === slugMake).map((g) => g.updatedAt)),
      changeFrequency: "weekly" as const,
      priority: 0.5,
    })),
    ...guides.map((g) => ({
      url: `${siteUrl}${guidePath(g.slugMake, g.slugModel)}`,
      lastModified: g.updatedAt,
      changeFrequency: "monthly" as const,
      priority: 0.5,
    })),
  ];
}
