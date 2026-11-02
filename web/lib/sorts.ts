import { MARGIN } from "@/lib/copy";

/** §29 "Orden" of the results. Shared by the page (server) and the select (client). */
export const SORTS = {
  recent: "Más recientes",
  score: "Mejor oportunidad",
  price: "Menor precio",
  km: "Menor kilometraje",
  // PRO-02: only with the plan's dealer_margin (sortsFor); search_results ignores it otherwise.
  margin: MARGIN.sort,
} as const;
export type Sort = keyof typeof SORTS;

export function isSort(value: unknown): value is Sort {
  return typeof value === "string" && Object.hasOwn(SORTS, value);
}

/** The orders a user can pick: «Mayor margen estimado» only with the margin (Pro). */
export function sortsFor(margin: boolean): Sort[] {
  return (Object.keys(SORTS) as Sort[]).filter((s) => margin || s !== "margin");
}

/** The order a page uses: ?s= when the user can pick it, else by score. */
export function effectiveSort(value: unknown, margin: boolean): Sort {
  return isSort(value) && sortsFor(margin).includes(value) ? value : "score";
}
