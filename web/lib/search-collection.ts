import { FIRST_READ_GRACE_MS, FIRST_READ_MATCH_MS, STALE_READ_MS } from "@/lib/zone-notice";

export type CollectionState = "waiting" | "loading" | "done" | "failed" | "paused" | "unknown";
export type SearchSource = {
  id: string;
  name: string;
  enabled: boolean;
  collectionState?: CollectionState;
  /** A search by model only (the zone notice): a target of it still on its first read (onFirstRead). */
  firstRead?: boolean;
  /** …and a target created with the search, or stale for it (staleAt): the model's market was still being collected. */
  newTarget?: boolean;
};
export type CollectionRun = { status: string; started_at?: string | null; finished_at: string | null };
/** A target with its latest runs, newest first. */
export type CollectionTarget = { first_run_done: boolean; last_run_at?: string | null; collector_runs: CollectionRun[] };

const time = (value: string | null | undefined) => Date.parse(value ?? "");

/**
 * Whether a target's stock was over STALE_READ_MS old when the search
 * started needing it (`since`), so it reads the market again for it: one
 * brought back after a day inactive keeps first_run_done (worker
 * targets.sync_targets). Once a run since then moved last_run_at, the run
 * before it tells. An unreadable `since` counts as an old search: never.
 */
export function staleAt(target: CollectionTarget, since: number): boolean {
  if (!Number.isFinite(since)) return false;
  const [latest, prior] = target.collector_runs;
  if (!(time(latest?.started_at) >= since)) return !(time(target.last_run_at) >= since - STALE_READ_MS);
  return !prior || (!(time(prior.started_at) >= since) && !(time(prior.finished_at) >= since - STALE_READ_MS));
}

/**
 * Whether a target is still on a read the zone notice waits for
 * (docs/AVISO_ZONA.md): its first read, or a read again of a stale stock
 * (staleAt), where only a run since `since` counts. Held while that read
 * runs, and FIRST_READ_MATCH_MS after it ends, while the worker matches its
 * batch; while it hasn't started, only FIRST_READ_GRACE_MS after `since`, so
 * a source that never runs (Facebook down) doesn't hold it for good. A failed
 * read, or one that read nothing (an empty first run keeps first_run_done
 * off, crawl.py), holds it no longer than that. `since`: when the search
 * started needing the target, the later of their creation dates. Null: no
 * target linked yet.
 */
export function onFirstRead(target: CollectionTarget | null, since: number, now = Date.now()): boolean {
  if (target?.first_run_done && !staleAt(target, since)) return false;
  let run = target?.collector_runs[0];
  if (target?.first_run_done && run && run.status !== "running" && !(time(run.finished_at) >= since)) run = undefined;
  if (!run) return now - since < FIRST_READ_GRACE_MS;
  return run.status === "running" || now - time(run.finished_at) < FIRST_READ_MATCH_MS;
}

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
