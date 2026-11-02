import { readFileSync } from "node:fs";
import path from "node:path";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mock = vi.hoisted(() => ({ track: vi.fn() }));
vi.mock("@/lib/auth", () => ({ requireUser: async () => ({ id: "user-1" }) }));
vi.mock("next/cache", () => ({ refresh: vi.fn() }));
vi.mock("@/lib/events", () => ({ track: mock.track }));
vi.mock("@/lib/config", () => ({ webConfig: async () => ({}) }));
vi.mock("@/lib/supabase/server", () => ({ createClient: async () => ({}) }));

import { trackDuplicateLink } from "@/app/app/listings/actions";
import { RedFlagList } from "@/components/app/red-flag-list";
import { configFieldLabel, validateConfigChange } from "@/lib/admin-config";
import { forbiddenTermsIn } from "@/lib/copy";
import {
  DUPLICATE_LINK_LABEL,
  duplicateTarget,
  linkedListingIds,
  RED_FLAG_IDS,
  RED_FLAGS_ORDER_MESSAGE,
  safeExternalUrl,
  sortFlags,
} from "@/lib/red-flags";
import { emphasize } from "@/lib/risk-checklist";
import type { RedFlag } from "@/lib/types";

const ROOT = path.resolve(__dirname, "..");

// PAR-02 resto: the three new flags as the worker stores them (worker/intelligence/red_flags.py).
const PRIVATE: RedFlag = { id: "private_many_listings", severity: "info", text: "El vendedor tiene 7 publicaciones activas: conviene preguntar si es titular." };
const PHOTOS: RedFlag = {
  id: "duplicate_photos",
  severity: "warning",
  text: "Las fotos de esta publicación aparecen también en otra publicación (Rosario Garage) con otros datos: conviene pedir fotos actuales y ver el auto antes de señar.",
  link: { listing_id: 501, url: "https://example.test/rosariogarage/1", source_name: "Rosario Garage", kind: "duplicate_photos" },
};
const CROSS: RedFlag = {
  id: "cross_source_duplicate",
  severity: "info",
  text: "Parece el mismo auto publicado también en Mercado Libre (mismas fotos): conviene comparar las dos publicaciones.",
  link: { listing_id: 777, url: "https://auto.mercadolibre.com.ar/MLA-1", source_name: "Mercado Libre", kind: "cross_source_photos" },
};
const OLD: RedFlag = { id: "no_owners", severity: "info", text: "El aviso no dice cuántos dueños tuvo." };

describe("red flags of the listing page (PAR-02 resto)", () => {
  it("puts warnings first and keeps the stored order otherwise", () => {
    expect(sortFlags([PRIVATE, OLD, PHOTOS, CROSS]).map((f) => f.id)).toEqual(["duplicate_photos", "private_many_listings", "no_owners", "cross_source_duplicate"]);
  });

  it("links to the other listing's page when it is in the base, else to its URL", () => {
    expect(duplicateTarget(CROSS, new Set([777]))).toEqual({ href: "/app/listings/777", external: false, otherListingId: 777, kind: "cross_source_photos" });
    expect(duplicateTarget(CROSS, new Set())).toEqual({ href: "https://auto.mercadolibre.com.ar/MLA-1", external: true, otherListingId: 777, kind: "cross_source_photos" });
    expect(duplicateTarget(OLD, new Set([777]))).toBeNull();
    expect(duplicateTarget({ ...CROSS, link: { listing_id: 777, url: "javascript:alert(1)" } }, new Set())).toBeNull();
    expect(duplicateTarget({ ...CROSS, link: { listing_id: -3, url: "https://x.test/" } }, new Set())).toBeNull();
    // A stored link without kind (or an unknown one) falls back by flag id.
    expect(duplicateTarget({ ...PHOTOS, link: { listing_id: 501 } }, new Set([501]))?.kind).toBe("duplicate_photos");
    expect(duplicateTarget({ ...CROSS, link: { listing_id: 777, kind: "nope" } }, new Set([777]))?.kind).toBe("cross_source_data");
  });

  it("asks only for the linked ids, once each", () => {
    expect(linkedListingIds([PRIVATE, PHOTOS, CROSS, { ...CROSS, id: "x" }, OLD])).toEqual([501, 777]);
    expect(linkedListingIds([PRIVATE, OLD])).toEqual([]);
  });

  it("accepts only http(s) URLs with a host and no credentials", () => {
    expect(safeExternalUrl("https://auto.mercadolibre.com.ar/MLA-1")).toBe(true);
    expect(safeExternalUrl("http://example.test/a")).toBe(true);
    for (const url of ["javascript:alert(1)", "data:text/html,x", "https://user:pw@example.test/", "/app/listings/1", "", null, 3, `https://x.test/${"a".repeat(2001)}`]) {
      expect(safeExternalUrl(url), String(url)).toBe(false);
    }
  });

  it("renders «Conviene verificar» with the new flags (snapshot)", () => {
    const html = renderToStaticMarkup(createElement(RedFlagList, { listingId: 42, flags: sortFlags([PRIVATE, PHOTOS, CROSS, OLD]), present: new Set([501]) }));
    expect(html).toMatchSnapshot();
    // Internal link to the stored listing, external one in a new tab, none for the old flag.
    expect(html).toContain('href="/app/listings/501"');
    expect(html).toContain('href="https://auto.mercadolibre.com.ar/MLA-1" target="_blank" rel="noopener noreferrer"');
    expect(html.match(/data-testid="duplicate-link"/g)).toHaveLength(2);
    expect(html.match(new RegExp(DUPLICATE_LINK_LABEL, "g"))).toHaveLength(2);
  });

  it("renders a stored flag without link exactly as before", () => {
    const html = renderToStaticMarkup(createElement(RedFlagList, { listingId: 42, flags: [OLD], present: new Set<number>() }));
    expect(html).not.toContain("duplicate-link");
    expect(html).toContain(OLD.text);
  });

  it("opens the checklist emphasized when the photos are someone else's", () => {
    expect(emphasize([PHOTOS])).toBe(true);
    expect(emphasize([CROSS, PRIVATE])).toBe(false);
  });

  it("keeps the ids in step with the worker's default order", () => {
    const config = readFileSync(path.resolve(ROOT, "../worker/intelligence/config.py"), "utf-8");
    const block = config.match(/DEFAULT_FLAG_ORDER = \(([^)]*)\)/)?.[1] ?? "";
    expect([...block.matchAll(/"([a-z_]+)"/g)].map((m) => m[1])).toEqual([...RED_FLAG_IDS]);
  });

  it("never claims a verification, a certainty or an agency in the new copy", () => {
    const banned = ["robad", "estafa", "fraude", "verificado por ese auto", "certificad", "garantiz", "agencia", "revendedor"];
    const texts = [PRIVATE.text, PHOTOS.text, CROSS.text, DUPLICATE_LINK_LABEL];
    for (const file of ["lib/red-flags.ts", "components/app/red-flag-list.tsx", "components/app/duplicate-link.tsx"]) {
      texts.push(readFileSync(path.join(ROOT, file), "utf-8").replace(/\/\*\*[\s\S]*?\*\/|\/\/.*$/gm, ""));
    }
    for (const text of texts) {
      const folded = text.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();
      expect(banned.filter((term) => folded.includes(term)), text.slice(0, 80)).toEqual([]);
      expect(forbiddenTermsIn(text), text.slice(0, 80)).toEqual([]);
    }
  });
});

describe("trackDuplicateLink (PAR-02 resto)", () => {
  beforeEach(() => vi.clearAllMocks());

  it("records duplicate_link_clicked with the pair, its kind and where it went", async () => {
    await trackDuplicateLink(42, 777, "cross_source_photos", "external");
    await trackDuplicateLink(42, 501, "duplicate_photos", "internal");
    expect(mock.track.mock.calls.map((call) => call.slice(1))).toEqual([
      ["user-1", "duplicate_link_clicked", { listing_id: 42, other_listing_id: 777, kind: "cross_source_photos", target: "external" }],
      ["user-1", "duplicate_link_clicked", { listing_id: 42, other_listing_id: 501, kind: "duplicate_photos", target: "internal" }],
    ]);
  });

  it.each([
    [0, 777, "cross_source_photos", "external"],
    [42, -1, "cross_source_photos", "external"],
    [42, 1.5, "cross_source_photos", "external"],
    ["42", 777, "cross_source_photos", "external"],
    [42, 777, "much_cheaper", "external"],
    [42, 777, "cross_source_data", "elsewhere"],
    [42, Number.NaN, "cross_source_data", "internal"],
  ])("ignores %j → %j (%j, %j)", async (listingId, other, kind, target) => {
    await trackDuplicateLink(listingId as number, other as number, kind as "duplicate_photos", target as "internal");
    expect(mock.track).not.toHaveBeenCalled();
  });
});

describe("/admin/config for the PAR-02 resto keys", () => {
  const risk = { checklist_enabled: true, links: {} };
  const redFlags = { much_cheaper_pct: 25, much_cheaper_verify_pct: 35, anticipo_pct: 50 };

  it("accepts the default duplicate and photo hash keys and the old config", () => {
    const full = {
      ...risk,
      photo_hash_count: 3,
      phash_max_distance: 6,
      photo_hash: { enabled: false, daily_image_cap: 600, max_attempts: 2, max_bytes: 2_000_000, timeout_seconds: 10, per_host_interval_seconds: 1, common_min_sellers: 3, skip_sources: ["facebook", "onlycarsusados", "sc_clasificados"] },
      cross_source: { km_tol_pct: 3, price_tol_pct: 5, data_min_km: 10_000, data_max_dist_km: 50, photo_conflict_km_pct: 10, photo_conflict_price_pct: 15 },
      signals: { private_many_listings: "on", cross_source_photos: "on", cross_source_data: "shadow", duplicate_photos: "on" },
    };
    expect(validateConfigChange("risk", full, risk)).toBeNull();
    expect(validateConfigChange("risk", risk, full)).toBeNull();
  });

  it.each([
    [{ photo_hash_count: 0 }, /photo_hash_count/],
    [{ photo_hash_count: 2.5 }, /photo_hash_count/],
    [{ phash_max_distance: 17 }, /phash_max_distance/],
    [{ photo_hash: { enabled: "yes" } }, /photo_hash.enabled/],
    [{ photo_hash: { daily_image_cap: 9000 } }, /daily_image_cap/],
    [{ photo_hash: { skip_sources: "facebook" } }, /skip_sources/],
    [{ cross_source: { km_tol_pct: 25 } }, /km_tol_pct/],
    [{ cross_source: { photo_conflict_price_pct: 60 } }, /photo_conflict_price_pct/],
    [{ signals: { cross_source_data: "maybe" } }, /on, shadow u off/],
  ])("rejects risk %j", (change, message) => {
    expect(validateConfigChange("risk", { ...risk, ...change }, risk)).toMatch(message);
  });

  it("accepts red_flags.order of known ids without repeats", () => {
    expect(validateConfigChange("red_flags", { ...redFlags, order: [...RED_FLAG_IDS] }, redFlags)).toBeNull();
    expect(validateConfigChange("red_flags", { ...redFlags, order: ["much_cheaper", "duplicate_photos"] }, redFlags)).toBeNull();
    expect(validateConfigChange("red_flags", { ...redFlags, order: ["much_cheaper", "much_cheaper"] }, redFlags)).toBe(RED_FLAGS_ORDER_MESSAGE);
    expect(validateConfigChange("red_flags", { ...redFlags, order: ["nope"] }, redFlags)).toBe(RED_FLAGS_ORDER_MESSAGE);
    expect(validateConfigChange("red_flags", { ...redFlags, order: "much_cheaper" }, redFlags)).toBe(RED_FLAGS_ORDER_MESSAGE);
  });

  it("names the new fields in the change preview", () => {
    expect(configFieldLabel("risk", "photo_hash.enabled")).toBe("Hash de fotos prendido (descarga imágenes)");
    expect(configFieldLabel("risk", "signals.cross_source_data")).toBe("Señal cross_source_data (on, shadow u off)");
  });
});
