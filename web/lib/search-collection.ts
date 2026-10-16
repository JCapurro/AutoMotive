export type CollectionState = "waiting" | "loading" | "done" | "failed" | "paused" | "unknown";
export type SearchSource = { id: string; name: string; enabled: boolean; collectionState?: CollectionState };
export type CollectionRun = { status: string; finished_at: string | null };

/**
 * The body types each collector can search (its BODY_TYPES: worker/collectors/
 * mercadolibre.py, kavak.py; worker/tests/test_body_type_targets.py keeps this
 * line equal). A source in app_config.body_type_targets.sources gets a target
 * per body type it can search (docs/CARROCERIA.md).
 */
export const BODY_TYPE_SEARCHES: Record<string, readonly string[]> = {"kavak": ["hatchback", "monovolumen", "pickup", "rural", "sedan", "suv", "utilitario"], "mercadolibre": ["convertible", "coupe", "hatchback", "monovolumen", "pickup", "rural", "sedan", "suv", "utilitario"]};

/** app_config.body_type_targets.sources when it can't be read (the migration's value). */
export const DEFAULT_BODY_TYPE_SOURCES = ["mercadolibre", "kavak"];

/** The body types of a search without a model that `source` crawls a target for. */
export function bodyTypeTargetsOf(source: string, bodyTypes: readonly string[], configured: readonly string[]): string[] {
  if (!configured.includes(source)) return [];
  const searchable = BODY_TYPE_SEARCHES[source] ?? [];
  return bodyTypes.filter((code) => searchable.includes(code));
}

export function collectionState(run: CollectionRun | undefined): CollectionState {
  if (!run) return "waiting";
  if (run.status === "running") return "loading";
  if (run.status === "failed") return "failed";
  if (run.status === "ok" && run.finished_at) return "done";
  return "unknown";
}

export function collectionPending(sources: SearchSource[] | null) {
  return sources?.some((source) => source.collectionState === "waiting" || source.collectionState === "loading") ?? false;
}
