import "server-only";

import type { SupabaseClient } from "@supabase/supabase-js";

import type { Database } from "@/types/database";

export type CatalogModel = {
  model: string;
  trims: string[];
  yearFrom: number | null;
  yearTo: number | null;
  transmissions: string[];
  fuels: string[];
  /** vehicle_catalog.body_types: most common first; one = certain, none = unknown (docs/CARROCERIA.md). */
  bodyTypes: string[];
};
export type CatalogMake = { make: string; models: CatalogModel[] };
export type Catalog = CatalogMake[];

/** vehicle_catalog as make → model → trims, for the form's selects (autocomplete, sección 9). */
export async function loadCatalog(supabase: SupabaseClient<Database>): Promise<Catalog> {
  // PostgREST caps a response at max_rows (1000) whatever .limit() says, and the
  // catalog has more rows than that (models + trims): page through it, or the
  // makes at the end of the alphabet (Volkswagen, Volvo) never reach the form.
  const PAGE = 1000;
  const data: Database["public"]["Tables"]["vehicle_catalog"]["Row"][] = [];
  for (let from = 0; ; from += PAGE) {
    const { data: page } = await supabase
      .from("vehicle_catalog")
      .select("make, model, trim, year_from, year_to, transmissions, fuels, body_types")
      .order("make")
      .order("model")
      .order("trim", { nullsFirst: true })
      .order("id")
      .range(from, from + PAGE - 1);
    data.push(...((page ?? []) as typeof data));
    if (!page || page.length < PAGE) break;
  }
  const makes = new Map<string, Map<string, CatalogModel>>();
  for (const row of data) {
    const models = makes.get(row.make) ?? new Map<string, CatalogModel>();
    makes.set(row.make, models);
    const entry =
      models.get(row.model) ??
      ({ model: row.model, trims: [], yearFrom: null, yearTo: null, transmissions: [], fuels: [], bodyTypes: [] } as CatalogModel);
    models.set(row.model, entry);
    if (row.trim) {
      entry.trims.push(row.trim);
    } else {
      entry.yearFrom = row.year_from;
      entry.yearTo = row.year_to;
      entry.transmissions = row.transmissions;
      entry.fuels = row.fuels;
      entry.bodyTypes = row.body_types ?? [];
    }
  }
  const collator = new Intl.Collator("es");
  // numeric: "116i" before "120i".
  const trimCollator = new Intl.Collator("es", { numeric: true });
  return [...makes.entries()]
    .sort(([a], [b]) => collator.compare(a, b))
    .map(([make, models]) => ({
      make,
      models: [...models.values()]
        .sort((a, b) => collator.compare(a.model, b.model))
        // Rows come back in no set order; the form lists trims as given.
        .map((m) => ({ ...m, trims: m.trims.sort(trimCollator.compare) })),
    }));
}
