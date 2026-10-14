import { resultsCsvResponse } from "@/lib/results-export-server";

export const dynamic = "force-dynamic";

/** Pro (3.3): the results of every search in one CSV. */
export async function GET() {
  return resultsCsvResponse(null);
}
