import { describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

vi.mock("@/lib/origin", () => ({ requestOrigin: () => "https://www.eseauto.com.ar" }));

import { GET } from "@/app/fundador/[code]/route";
import { founderOfferTerms, parseFounderOffer, planPrice } from "@/lib/pro";

const OFFER = { amount: 50000, months: 6, slots: 10, left: 7, regular: 100000 };

describe("precio fundador por link", () => {
  it("lee la oferta de founder_offer y descarta lo que no es una oferta", () => {
    expect(parseFounderOffer(OFFER)).toEqual(OFFER);
    expect(parseFounderOffer({ ...OFFER, regular: 40000 })).toEqual({ ...OFFER, regular: null });
    for (const bad of [null, "x", {}, { ...OFFER, amount: 0 }, { ...OFFER, left: -1 }, { ...OFFER, months: 1.5 }]) {
      expect(parseFounderOffer(bad)).toBeNull();
    }
  });

  it("dice cuánto dura el precio y a cuánto pasa después", () => {
    expect(founderOfferTerms(OFFER)).toBe(`Todo Pro, con el precio fijo por 6 meses desde tu primer pago; después pasa a ${planPrice(100000)} por mes, con aviso 30 días antes.`);
    expect(founderOfferTerms({ ...OFFER, regular: null })).toBe("Todo Pro, con el precio fijo por 6 meses desde tu primer pago.");
  });

  it("el link lleva a Pro con el código, y un código raro no pasa", async () => {
    const go = async (code: string) => (await GET(new NextRequest(`https://www.eseauto.com.ar/fundador/${code}`), { params: Promise.resolve({ code }) })).headers.get("location");
    expect(await go("abc123def456")).toBe("https://www.eseauto.com.ar/app/pro?plan=pro_monthly&fundador=abc123def456");
    expect(await go("<script>")).toBe("https://www.eseauto.com.ar/app/pro?plan=pro_monthly");
  });
});
