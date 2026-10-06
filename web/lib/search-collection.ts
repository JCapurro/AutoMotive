export type CollectionState = "waiting" | "loading" | "done" | "failed" | "paused" | "unknown";
export type SearchSource = { id: string; name: string; enabled: boolean; collectionState?: CollectionState };
export type CollectionRun = { status: string; finished_at: string | null };

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
