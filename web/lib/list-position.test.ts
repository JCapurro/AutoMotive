import { describe, expect, it } from "vitest";

import { cleanListOrigin, cleanResultsViewed, listingHref, MAX_PAGE_IDS, pageListingIds, parseListOrigin } from "./list-position";

describe("listingHref", () => {
  it("keeps the bare link without a list (/app, /app/saved)", () => {
    expect(listingHref(42)).toBe("/app/listings/42");
    expect(listingHref(42, null)).toBe("/app/listings/42");
  });

  it("adds src, ord, flt and pos from a results list, never s, f or p", () => {
    const href = listingHref(42, { profileId: 796, sort: "score", filter: "new", position: 3 });
    expect(href).toBe("/app/listings/42?src=796&ord=score&flt=new&pos=3");
    const qs = new URL(href, "https://x.test").searchParams;
    expect(qs.has("s")).toBe(false);
    expect(qs.has("f")).toBe(false);
    expect(qs.has("p")).toBe(false);
  });
});

describe("parseListOrigin", () => {
  it("reads a valid link", () => {
    expect(parseListOrigin({ src: "796", ord: "price", flt: "opportunities", pos: "12" })).toEqual({ profileId: 796, sort: "price", filter: "opportunities", position: 12 });
    expect(parseListOrigin({ src: "1", ord: "km", flt: "visit_scheduled", pos: "2" }).filter).toBe("visit_scheduled");
  });

  it("drops each invalid part on its own", () => {
    expect(parseListOrigin({})).toEqual({ profileId: null, sort: null, filter: null, position: null });
    expect(parseListOrigin({ src: "abc", ord: "cheapest", flt: "everything", pos: "0" })).toEqual({ profileId: null, sort: null, filter: null, position: null });
    expect(parseListOrigin({ src: "-1", ord: "score", flt: "hasOwnProperty", pos: "1.5" })).toEqual({ profileId: null, sort: "score", filter: null, position: null });
    expect(parseListOrigin({ src: ["1", "2"], ord: ["score"], flt: ["all"], pos: "07" })).toEqual({ profileId: null, sort: null, filter: null, position: null });
    expect(parseListOrigin({ src: "1", ord: "toString", flt: "saved", pos: "99999999999" })).toEqual({ profileId: 1, sort: null, filter: "saved", position: null });
    // A bad tab drops only the tab.
    expect(parseListOrigin({ src: "5", ord: "recent", flt: "Todos", pos: "4" })).toEqual({ profileId: 5, sort: "recent", filter: null, position: 4 });
  });
});

describe("cleanListOrigin", () => {
  it("keeps valid numbers and a known sort", () => {
    expect(cleanListOrigin({ profileId: 5, sort: "km", filter: "discarded", position: 1 })).toEqual({ profileId: 5, sort: "km", filter: "discarded", position: 1 });
  });

  it("drops what a forged call sends", () => {
    const none = { profileId: null, sort: null, filter: null, position: null };
    expect(cleanListOrigin(null)).toEqual(none);
    expect(cleanListOrigin("x")).toEqual(none);
    expect(cleanListOrigin({ profileId: "5", sort: "__proto__", filter: "__proto__", position: 0 })).toEqual(none);
    expect(cleanListOrigin({ profileId: 1.5, sort: "margin", filter: 3, position: -3 })).toEqual({ ...none, sort: "margin" });
    expect(cleanListOrigin({ profileId: Number.MAX_SAFE_INTEGER + 1, position: Infinity })).toEqual(none);
    // A bad tab drops only the tab.
    expect(cleanListOrigin({ profileId: 2, sort: "price", filter: "drop table", position: 7 })).toEqual({ profileId: 2, sort: "price", filter: null, position: 7 });
  });
});

describe("pageListingIds", () => {
  const rows = Array.from({ length: 120 }, (_, i) => ({ listing_id: i + 1 }));

  it("sends only the page «Ver más» added", () => {
    expect(pageListingIds(rows.slice(0, 50), 1, 50)).toEqual(rows.slice(0, 50).map((r) => r.listing_id));
    expect(pageListingIds(rows.slice(0, 100), 2, 50)).toEqual(rows.slice(50, 100).map((r) => r.listing_id));
    expect(pageListingIds(rows, 3, 50)).toEqual(rows.slice(100).map((r) => r.listing_id));
  });

  it("is empty past the list and skips null ids", () => {
    expect(pageListingIds(rows.slice(0, 40), 2, 50)).toEqual([]);
    expect(pageListingIds([{ listing_id: 1 }, { listing_id: null }, { listing_id: 3 }], 1, 50)).toEqual([1, 3]);
  });
});

describe("cleanResultsViewed", () => {
  it("accepts a page", () => {
    expect(cleanResultsViewed(9, "score", "all", 2, [3, 1, 2])).toEqual({ profileId: 9, sort: "score", filter: "all", page: 2, listingIds: [3, 1, 2] });
    expect(cleanResultsViewed(9, "recent", "visit_scheduled", 1, [1])?.filter).toBe("visit_scheduled");
  });

  it("refuses anything invalid", () => {
    expect(cleanResultsViewed(0, "score", "all", 1, [1])).toBeNull();
    expect(cleanResultsViewed(9, "best", "all", 1, [1])).toBeNull();
    expect(cleanResultsViewed(9, "score", "everything", 1, [1])).toBeNull();
    expect(cleanResultsViewed(9, "score", "all", 0, [1])).toBeNull();
    expect(cleanResultsViewed(9, "score", "all", 1, [])).toBeNull();
    expect(cleanResultsViewed(9, "score", "all", 1, [1, "2"])).toBeNull();
    expect(cleanResultsViewed(9, "score", "all", 1, "1,2")).toBeNull();
    expect(cleanResultsViewed(9, "score", "all", 1, Array.from({ length: MAX_PAGE_IDS + 1 }, (_, i) => i + 1))).toBeNull();
  });
});
