/**
 * PAR-02 resto: the red flags of the listing page («Conviene verificar»)
 * (docs/superpowers/specs/2026-11-02-par02-resto-design.md). Data only, no UI
 * and no server-only code: the page, the list component and
 * validateConfigChange() import it.
 *
 * The worker builds the flags (worker/intelligence/red_flags.py); a duplicate
 * flag carries `link`, the other listing. It opens the other listing's page
 * when it is still in the base, else its URL in a new tab. Matches stored
 * before PAR-02 resto have no `link` and render as before.
 */
import { z } from "zod";

import type { RedFlag } from "@/lib/types";

/** Every id the worker emits, in app_config.red_flags.order's default (worker/intelligence/config.py). */
export const RED_FLAG_IDS = [
  "duplicate_photos", "much_cheaper", "partial_price_suspect", "private_many_listings",
  "cross_source_duplicate", "no_owners", "service_unavailable", "no_service", "timing_pending",
  "no_timing_belt", "short_description", "damage_mentioned", "commercial_use", "vtv_pending",
  "low_km_for_age", "repost", "price_mismatch", "year_mismatch", "km_mismatch",
] as const;

export const DUPLICATE_KINDS = ["duplicate_photos", "cross_source_photos", "cross_source_data"] as const;
export type DuplicateKind = (typeof DUPLICATE_KINDS)[number];

export const DUPLICATE_LINK_LABEL = "Ver la otra publicación";

/** Warnings first, the stored order otherwise (the page groups by severity; the email follows red_flags.order). */
export function sortFlags(flags: readonly RedFlag[]): RedFlag[] {
  return flags.slice().sort((a, b) => Number(b.severity === "warning") - Number(a.severity === "warning"));
}

function positiveId(value: unknown): number | null {
  return typeof value === "number" && Number.isSafeInteger(value) && value > 0 ? value : null;
}

/** http(s) only, with a host and no credentials: the other listing's public URL. */
export function safeExternalUrl(url: unknown): url is string {
  if (typeof url !== "string" || url.length > 2000) return false;
  try {
    const parsed = new URL(url);
    return (parsed.protocol === "https:" || parsed.protocol === "http:") && parsed.hostname !== "" && !parsed.username && !parsed.password;
  } catch {
    return false;
  }
}

/** The ids the duplicate links point to: the page asks which ones still exist, in one query. */
export function linkedListingIds(flags: readonly RedFlag[]): number[] {
  return [...new Set(flags.map((f) => positiveId(f.link?.listing_id)).filter((id): id is number => id !== null))];
}

function kindOf(flag: RedFlag): DuplicateKind {
  const kind = flag.link?.kind;
  if (typeof kind === "string" && (DUPLICATE_KINDS as readonly string[]).includes(kind)) return kind as DuplicateKind;
  return flag.id === "duplicate_photos" ? "duplicate_photos" : "cross_source_data";
}

export type DuplicateTarget = {
  href: string;
  external: boolean;
  otherListingId: number;
  kind: DuplicateKind;
};

/** Where «Ver la otra publicación» goes, or null (no link, or neither a stored listing nor a safe URL). */
export function duplicateTarget(flag: RedFlag, present: ReadonlySet<number>): DuplicateTarget | null {
  const link = flag.link;
  const id = positiveId(link?.listing_id);
  if (!link || id === null) return null;
  if (present.has(id)) return { href: `/app/listings/${id}`, external: false, otherListingId: id, kind: kindOf(flag) };
  if (safeExternalUrl(link.url)) return { href: link.url, external: true, otherListingId: id, kind: kindOf(flag) };
  return null;
}

/** The flags that open the «Antes de señar» checklist expanded (the price, or someone else's photos). */
export const EMPHASIS_FLAGS: ReadonlySet<string> = new Set(["much_cheaper", "partial_price_suspect", "duplicate_photos"]);

/** /admin/config: red_flags.order is a list of known ids without repeats (the worker ignores unknown ones anyway). */
export const RED_FLAGS_ORDER_MESSAGE = `order tiene que ser una lista sin repetidos de: ${RED_FLAG_IDS.join(", ")}.`;
export const RedFlagsOrderInput = z
  .array(z.enum(RED_FLAG_IDS))
  .refine((ids) => new Set(ids).size === ids.length, RED_FLAGS_ORDER_MESSAGE);
