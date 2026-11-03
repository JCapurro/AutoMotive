import "server-only";

import { siteUrl } from "@/lib/env";
import { publishedGuidesByModel } from "@/lib/guides-data";
import type { PublicGuide } from "@/lib/guides";

/**
 * The published guides for llms.txt / llms-full.txt. At build time a database
 * problem renders the file without guides (regenerated within the hour)
 * instead of failing the deploy; at runtime it throws, and ISR keeps serving
 * the file it had (like /guias).
 */
async function modelsOrEmptyAtBuild(): Promise<PublicGuide[][]> {
  try {
    return await publishedGuidesByModel();
  } catch (error) {
    if (process.env.NEXT_PHASE === "phase-production-build") return [];
    throw error;
  }
}

/** A text/markdown response built from the published guides. */
export async function markdownResponse(build: (models: PublicGuide[][], site: string) => string): Promise<Response> {
  const body = build(await modelsOrEmptyAtBuild(), siteUrl);
  return new Response(body, { headers: { "Content-Type": "text/markdown; charset=utf-8" } });
}
