import { type NextRequest } from "next/server";

import { resultsCsvResponse } from "@/lib/results-export-server";

export const dynamic = "force-dynamic";

/** Pro (3.3): this search's results as a CSV. */
export async function GET(_request: NextRequest, ctx: RouteContext<"/app/searches/[id]/export">) {
  const { id } = await ctx.params;
  const profileId = Number(id);
  if (!Number.isSafeInteger(profileId) || profileId <= 0) {
    return new Response("No encontramos esa búsqueda.", { status: 404 });
  }
  return resultsCsvResponse(profileId);
}
