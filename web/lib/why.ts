import { COLOR_UNCONFIRMED, REASON_NAME, REASON_OK, REASON_ORDER } from "@/lib/copy";
import type { Reason } from "@/lib/types";

/** Hard filters first in the §23 order, then the soft preferences. */
export function orderReasons(reasons: Record<string, Reason>): [string, Reason][] {
  const rank = (key: string, r: Reason) => (r.kind === "soft" ? 100 : 0) + (REASON_ORDER.indexOf(key) + 1 || 50);
  return Object.entries(reasons).sort(([a, ra], [b, rb]) => rank(a, ra) - rank(b, rb));
}

/**
 * A «¿Por qué apareció?» row (§23): its title and the detail under it, or null.
 * ok → «Versión buscada» (caja and combustible say which); unknown → «Caja:
 * no informado», with no detail; fail → «…: no coincide con tu preferencia».
 * The color's unknown (docs/PLAN_FILTRO_COLOR.md) is «Color: sin confirmar»,
 * with the worker's detail below when it says more («color parecido: puede ser verde»).
 */
export function reasonText(name: string, reason: Reason): { title: string; detail: string | null } {
  const label = REASON_NAME[name] ?? name;
  const detail = reason.detail?.trim() ? reason.detail : null;
  if (reason.result === "ok") {
    const title = name === "transmission" || name === "fuel" ? `${label} ${reason.detail.toLowerCase()}` : (REASON_OK[name] ?? label);
    return { title, detail };
  }
  if (reason.result === "unknown") {
    if (name !== "color") return { title: `${label}: no informado`, detail: null };
    const more = detail != null && detail.toLocaleLowerCase("es") !== COLOR_UNCONFIRMED.toLocaleLowerCase("es");
    return { title: `${label}: sin confirmar`, detail: more ? detail : null };
  }
  return { title: `${label}: no coincide con tu preferencia`, detail };
}

/**
 * The §45 block, exactly as the PRD writes it:
 *
 *   Listing #4837
 *   matched Search #222
 *
 *   model = true
 *   year = true
 *
 *   score = 87
 *
 * One line per match_reasons field (ok → true, fail → false, unknown →
 * unknown); soft preferences are marked "(preferencia)".
 */
export function whyText(listingId: number, profileId: number, reasons: Record<string, Reason>, score: number): string {
  const lines = [`Listing #${listingId}`, `matched Search #${profileId}`, ""];
  for (const [key, r] of orderReasons(reasons)) {
    const value = r.result === "ok" ? "true" : r.result === "fail" ? "false" : "unknown";
    lines.push(`${key} = ${value}${r.kind === "soft" ? "  (preferencia)" : ""}`);
  }
  lines.push("", `score = ${score}`);
  return lines.join("\n");
}
