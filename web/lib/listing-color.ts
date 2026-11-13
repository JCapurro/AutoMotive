/**
 * A listing's color in the card and the ficha (docs/PLAN_FILTRO_COLOR.md §8):
 * «Color: gris · según la foto» when the photo decided it, «· dato del aviso»
 * when the source or the text did; «Color sin confirmar» when the search
 * filters by color and the listing has none. A neighbor color the photo
 * suggested («color parecido: puede ser verde») comes in the match reason.
 */
import { COLOR_METHOD, COLOR_UNCONFIRMED, colorName, isColor } from "@/lib/copy";

/** attributes._color.method ("source" | "text" | "vision"), or null. */
export function colorMethodOf(attributes: unknown): string | null {
  const how = (attributes as { _color?: { method?: unknown } } | null)?._color;
  return typeof how?.method === "string" ? how.method : null;
}

/**
 * "Color: gris · según la foto"; without a known method, "Color: gris".
 * Without a color: «Color sin confirmar» only when `wanted` (the search has
 * filters.colors), else null.
 */
export function colorLine(color: unknown, method: unknown, wanted = false): string | null {
  if (!isColor(color)) return wanted ? COLOR_UNCONFIRMED : null;
  const how = typeof method === "string" ? COLOR_METHOD[method] : undefined;
  return `Color: ${colorName(color)}${how ? ` · ${how}` : ""}`;
}

/** Whether stored search filters ask for a color (filters.colors with a code). */
export function wantsColor(filters: unknown): boolean {
  const colors = (filters as { colors?: unknown } | null)?.colors;
  return Array.isArray(colors) && colors.some(isColor);
}
