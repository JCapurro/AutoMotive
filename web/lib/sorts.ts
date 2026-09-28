/** §29 "Orden" of the results. Shared by the page (server) and the select (client). */
export const SORTS = {
  recent: "Más recientes",
  score: "Mejor oportunidad",
  price: "Menor precio",
  km: "Menor kilometraje",
} as const;
export type Sort = keyof typeof SORTS;

export function isSort(value: unknown): value is Sort {
  return typeof value === "string" && Object.hasOwn(SORTS, value);
}
