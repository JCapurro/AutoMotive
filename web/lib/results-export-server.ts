import "server-only";

import { exportFilename, resultsCsv, type ExportRow } from "@/lib/results-csv";
import { createClient } from "@/lib/supabase/server";

// The API returns at most 1000 rows per request; a Pro account may have more.
const PAGE = 1000;
const MAX_ROWS = 100_000;

function message(text: string, status: number): Response {
  return new Response(text, { status, headers: { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store" } });
}

/**
 * The CSV download of Pro (3.3): one search's results, or all of them with
 * `profileId` null. Read with the user's session: the database checks the
 * plan (export_search_results) and RLS keeps it to their own searches.
 */
export async function resultsCsvResponse(profileId: number | null): Promise<Response> {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return message("Iniciá sesión para descargar tus resultados.", 401);
  let name: string | null = null;
  if (profileId != null) {
    const { data: profile } = await supabase.from("search_profiles").select("name").eq("id", profileId).maybeSingle();
    if (!profile) return message("No encontramos esa búsqueda.", 404);
    name = profile.name;
  }
  const rows: ExportRow[] = [];
  for (let from = 0; from < MAX_ROWS; from += PAGE) {
    const { data, error } = await supabase
      .rpc("export_search_results", profileId == null ? {} : { p_profile_id: profileId })
      .range(from, from + PAGE - 1);
    if (error) {
      if (error.message.includes("plan_feature_unavailable")) {
        return message("Descargar los resultados es parte del plan Pro.", 403);
      }
      throw new Error(`export_search_results: ${error.message}`);
    }
    rows.push(...(data ?? []));
    if (!data || data.length < PAGE) break;
  }
  return new Response(resultsCsv(rows), {
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": `attachment; filename="${exportFilename(name)}"`,
      "Cache-Control": "no-store",
    },
  });
}
