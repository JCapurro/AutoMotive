import { FOLLOW_LABEL } from "@/lib/copy";

// §29, plus X-01's follow-up states (search_follow_counts), always shown.
export const FILTERS = {
  new: "Nuevos",
  opportunities: "Oportunidades",
  all: "Todos",
  saved: "Favoritos",
  discarded: "Descartados",
  ...FOLLOW_LABEL,
} as const;
export type Filter = keyof typeof FILTERS;

/** The results page's ?f=: one of FILTERS, shared with search_results_viewed's check. */
export function isResultFilter(value: unknown): value is Filter {
  return typeof value === "string" && Object.hasOwn(FILTERS, value);
}
