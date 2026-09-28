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
};
export type CatalogMake = { make: string; models: CatalogModel[] };
export type Catalog = CatalogMake[];

/** vehicle_catalog as make → model → trims, for the form's selects (autocomplete, sección 9). */
export async function loadCatalog(supabase: SupabaseClient<Database>): Promise<Catalog> {
  const { data } = await supabase
    .from("vehicle_catalog")
    .select("make, model, trim, year_from, year_to, transmissions, fuels")
    .order("make")
    .order("model")
    .limit(5000);
  const makes = new Map<string, Map<string, CatalogModel>>();
  for (const row of data ?? []) {
    const models = makes.get(row.make) ?? new Map<string, CatalogModel>();
    makes.set(row.make, models);
    const entry =
      models.get(row.model) ??
      ({ model: row.model, trims: [], yearFrom: null, yearTo: null, transmissions: [], fuels: [] } as CatalogModel);
    models.set(row.model, entry);
    if (row.trim) {
      entry.trims.push(row.trim);
    } else {
      entry.yearFrom = row.year_from;
      entry.yearTo = row.year_to;
      entry.transmissions = row.transmissions;
      entry.fuels = row.fuels;
    }
  }
  const collator = new Intl.Collator("es");
  return [...makes.entries()]
    .sort(([a], [b]) => collator.compare(a, b))
    .map(([make, models]) => ({
      make,
      models: [...models.values()].sort((a, b) => collator.compare(a.model, b.model)),
    }));
}
