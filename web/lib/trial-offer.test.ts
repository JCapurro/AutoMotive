import { describe, expect, it } from "vitest";

import { forbiddenTermsIn } from "./copy";
import { cardLead, cardTitle, keepLabel, opensSheet, payLabel, type Segment, sheetLead, sheetTitle, stripText, TRIAL_OFFER_SHEET_MIN, trialOffer } from "./trial-offer";

const text = (segments: Segment[]) => segments.map((s) => (typeof s === "string" ? s : s.mark)).join("");
const marks = (segments: Segment[]) => segments.filter((s): s is { mark: string } => typeof s !== "string").map((s) => s.mark);

describe("trialOffer", () => {
  it("is null unless the trial hides something of this search", () => {
    expect(trialOffer(30, 0)).toBeNull();
    expect(trialOffer(30, -3)).toBeNull();
    expect(trialOffer(30, null)).toBeNull();
    expect(trialOffer(30, 2.5)).toBeNull();
    expect(trialOffer(30, "48")).toBeNull();
  });

  it("adds what the list shows to what it hides", () => {
    expect(trialOffer(30, 48)).toEqual({ shown: 30, hidden: 48, total: 78 });
    // A recreated search whose trial was used elsewhere: nothing shown, some hidden.
    expect(trialOffer(0, 12)).toEqual({ shown: 0, hidden: 12, total: 12 });
    expect(trialOffer(undefined, 12)).toEqual({ shown: 0, hidden: 12, total: 12 });
  });

  it("opens the sheet by itself only from the threshold up", () => {
    expect(opensSheet(trialOffer(30, TRIAL_OFFER_SHEET_MIN - 1)!)).toBe(false);
    expect(opensSheet(trialOffer(30, TRIAL_OFFER_SHEET_MIN)!)).toBe(true);
    expect(opensSheet(trialOffer(0, 48)!)).toBe(true);
  });
});

describe("the offer's texts", () => {
  const usual = trialOffer(30, 48)!;

  it("say the same numbers in the sheet, the strip and the card", () => {
    expect(sheetTitle(usual)).toBe("Encontramos 78 autos. Tu prueba muestra 30.");
    expect(text(sheetLead(usual))).toBe("Los otros 48 también coinciden con lo que pediste y siguen publicados.");
    expect(marks(sheetLead(usual))).toEqual(["48"]);
    expect(text(stripText(usual))).toBe("Tu prueba muestra 30 de los 78 autos que coinciden.");
    expect(marks(stripText(usual))).toEqual(["30", "78"]);
    expect(text(cardTitle(usual))).toBe("Y 48 más que coinciden");
    expect(cardLead(usual)).toBe("Tu prueba muestra los primeros 30 que encontramos. Con Particular ves los 78, ordenados por mejor oportunidad, y te avisamos de los que aparezcan.");
    expect(payLabel(usual, 7, "$ 5.000")).toBe("Ver los 78 · 7 días por $ 5.000");
    expect(keepLabel(usual)).toBe("Seguir con mis 30");
  });

  it("keep the singulars right", () => {
    const one = trialOffer(30, 1)!;
    expect(text(sheetLead(one))).toBe("El otro también coincide con lo que pediste y sigue publicado.");
    expect(text(cardTitle(one))).toBe("Y 1 más que coincide");
    const single = trialOffer(1, 6)!;
    expect(sheetTitle(single)).toBe("Encontramos 7 autos. Tu prueba muestra 1.");
    expect(cardLead(single)).toContain("Tu prueba muestra el primero que encontramos.");
    expect(keepLabel(single)).toBe("Seguir con el que veo");
  });

  it("never say «muestra 0» when the list is empty", () => {
    const none = trialOffer(0, 12)!;
    expect(sheetTitle(none)).toBe("Encontramos 12 autos. Tu prueba no muestra ninguno.");
    expect(text(sheetLead(none))).toBe("Los 12 coinciden con lo que pediste y siguen publicados.");
    expect(text(stripText(none))).toBe("Tu prueba no muestra ninguno de los 12 autos que coinciden.");
    expect(text(cardTitle(none))).toBe("Hay 12 autos que coinciden");
    expect(cardLead(none)).toBe("Tu prueba no muestra ninguno. Con Particular ves los 12, ordenados por mejor oportunidad, y te avisamos de los que aparezcan.");
    expect(keepLabel(none)).toBe("Ahora no");
    const lone = trialOffer(0, 1)!;
    expect(sheetTitle(lone)).toBe("Encontramos 1 auto. Tu prueba no lo muestra.");
    expect(text(sheetLead(lone))).toBe("Coincide con lo que pediste y sigue publicado.");
    expect(text(stripText(lone))).toBe("Tu prueba no muestra el auto que coincide.");
    expect(text(cardTitle(lone))).toBe("Hay 1 auto que coincide");
    expect(cardLead(lone)).toBe("Tu prueba no muestra ninguno. Con Particular lo ves y te avisamos de los que aparezcan.");
    expect(payLabel(lone, 30, "$ 15.000")).toBe("Verlo · 30 días por $ 15.000");
  });

  it("pass the copy rules (lib/copy.ts: this file is outside the app-wide lint)", () => {
    const all = [usual, trialOffer(0, 12)!, trialOffer(30, 1)!, trialOffer(0, 1)!].flatMap((offer) => [
      sheetTitle(offer), text(sheetLead(offer)), text(stripText(offer)), text(cardTitle(offer)), cardLead(offer), payLabel(offer, 7, "$ 5.000"), keepLabel(offer),
    ]);
    expect(all.flatMap(forbiddenTermsIn)).toEqual([]);
  });
});
