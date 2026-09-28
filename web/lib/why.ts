import { REASON_ORDER } from "@/lib/copy";
import type { Reason } from "@/lib/types";

/** Hard filters first in the §23 order, then the soft preferences. */
export function orderReasons(reasons: Record<string, Reason>): [string, Reason][] {
  const rank = (key: string, r: Reason) => (r.kind === "soft" ? 100 : 0) + (REASON_ORDER.indexOf(key) + 1 || 50);
  return Object.entries(reasons).sort(([a, ra], [b, rb]) => rank(a, ra) - rank(b, rb));
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
