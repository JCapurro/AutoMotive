import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { copyProblem, GUIDE_COPY, guideForListing } from "@/lib/guides";

const index = [
  { make: "Ford", model: "Focus", slugMake: "ford", slugModel: "focus", updatedAt: "2026-11-01T00:00:00Z" },
  { make: "Volkswagen", model: "Gol Trend", slugMake: "volkswagen", slugModel: "gol-trend", updatedAt: "2026-11-01T00:00:00Z" },
];

describe("guideForListing (the ficha's «Ver la guía del …»)", () => {
  it("finds the published model by make and catalog model, ignoring case and spaces", () => {
    expect(guideForListing(index, "FORD", " focus ")?.slugModel).toBe("focus");
    expect(guideForListing(index, "volkswagen", "Gol Trend")?.slugModel).toBe("gol-trend");
  });

  it("is null without a published guide, a make or a model", () => {
    expect(guideForListing(index, "Ford", "Fiesta")).toBeNull();
    expect(guideForListing(index, "Chevrolet", "Focus")).toBeNull();
    expect(guideForListing(index, null, "Focus")).toBeNull();
    expect(guideForListing(index, "Ford", "")).toBeNull();
    expect(guideForListing([], "Ford", "Focus")).toBeNull();
  });

  it("the link's text is clean copy", () => {
    expect(copyProblem(GUIDE_COPY.listingLink)).toBeNull();
    expect(GUIDE_COPY.listingLink.replace("{name}", "Ford Focus")).toBe("Ver la guía del Ford Focus");
  });
});

describe("«Guías» in the public header and footer", () => {
  it("the header links to /guias next to Inicio and Planes, current on the guides' pages", () => {
    const home = renderToStaticMarkup(createElement(SiteHeader, { signedIn: false, page: "home" }));
    expect(home).toMatch(/<a[^>]*href="\/guias"[^>]*>Guías<\/a>/);
    expect(home).not.toMatch(/<a aria-current="page"[^>]*href="\/guias"/);
    const guides = renderToStaticMarkup(createElement(SiteHeader, { signedIn: false, page: "guias" }));
    expect(guides).toMatch(/<a aria-current="page"[^>]*href="\/guias">Guías<\/a>/);
    expect(guides.indexOf(">Planes<")).toBeLessThan(guides.indexOf(">Guías<"));
  });

  it("the footer links to /guias with the legal links", () => {
    const html = renderToStaticMarkup(createElement(SiteFooter));
    expect(html).toMatch(/<a[^>]*href="\/guias"[^>]*>Guías<\/a>/);
    expect(html).toContain('href="/privacidad"');
  });
});
