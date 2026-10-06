import { describe, expect, it } from "vitest";
import { priceContext, sellerStatements } from "./description";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { SellerDescription, DescriptionPriceContext } from "../components/app/description-insights";

const listing = {
  title: "Ford Fiesta", description: "Tiene granizo. Precio conversable. Único dueño.",
  description_facts: { v: 2, source: "llm", claims: { damage_mentioned: true, negotiable: true, single_owner: true },
    evidence: [{ field: "damage_mentioned", quote: "Tiene granizo" }, { field: "negotiable", quote: "Precio conversable" },
      { field: "single_owner", quote: "Único dueño" }] },
};

describe("seller description", () => {
  it("requires evidence in the current listing and handles old/null JSON", () => {
    expect(sellerStatements(listing)).toHaveLength(3);
    expect(sellerStatements({ ...listing, description: "Impecable" })).toEqual([]);
    expect(sellerStatements({ description_facts: { v: 1, single_owner: true } })).toEqual([]);
    expect(sellerStatements({ description_facts: null })).toEqual([]);
  });
  it("shows contradictions instead of replacing the published field", () => {
    const data = { title: "Fiesta", description: "Año 2017", year: 2018,
      description_facts: { v: 2, source: "llm", year: 2017, evidence: [{ field: "year", quote: "Año 2017" }] } };
    expect(sellerStatements(data)[0]).toMatchObject({ label: "Año", value: "2017", conflict: true });
  });
  it("never attributes the price difference or estimates a repair discount", () => {
    const result = priceContext(listing, null, 5);
    expect(result.intro).toContain("Faltan publicaciones comparables");
    expect(result.factors.join(" ")).toContain("podrían influir");
    expect(result.factors.join(" ")).not.toMatch(/\d+%|USD|ARS/);
  });
  it("negative damage claims are not a damage price factor", () => {
    const data = { description: "Sin choques", description_facts: { v: 2, source: "llm", claims: { damage_mentioned: false },
      evidence: [{ field: "damage_mentioned", quote: "Sin choques" }] } };
    expect(sellerStatements(data)[0]).toMatchObject({ quotes: ["Sin choques"], conflict: false });
    expect(priceContext(data, null, 5).factors).toEqual([]);
  });
  it("asks to confirm the total before comparing partial prices", () => {
    expect(priceContext({ ...listing, price_partial: true }, null, 5).intro).toContain("confirmar el total");
  });
  it("renders seller provenance and literal quotes alongside cautious price context", () => {
    const html = renderToStaticMarkup(createElement(SellerDescription, { listing }));
    expect(html).toContain("Según el vendedor");
    expect(html).toContain("Tiene granizo");
    expect(html).toContain("Ver qué dice el aviso");
    const price = renderToStaticMarkup(createElement(DescriptionPriceContext, { listing, refs: null, minN: 5 }));
    expect(price).toContain("Qué puede influir en el precio");
    expect(price).toContain("Faltan publicaciones comparables");
  });
});
