import { describe, expect, it } from "vitest";

import { orderReasons, whyText } from "./why";

const REASONS = {
  km_target: { result: "fail" as const, detail: "130.000 km", kind: "soft" as const },
  price: { result: "ok" as const, detail: "USD 10.300", kind: "hard" as const },
  transmission: { result: "unknown" as const, detail: "", kind: "hard" as const },
  model: { result: "ok" as const, detail: "Ford Fiesta", kind: "hard" as const },
  year: { result: "ok" as const, detail: "2017", kind: "hard" as const },
};

describe("whyText", () => {
  it("writes the §45 block", () => {
    expect(whyText(4837, 222, REASONS, 87)).toBe(
      [
        "Listing #4837",
        "matched Search #222",
        "",
        "model = true",
        "year = true",
        "price = true",
        "transmission = unknown",
        "km_target = false  (preferencia)",
        "",
        "score = 87",
      ].join("\n"),
    );
  });

  it("keeps unknown fields after the known order", () => {
    const keys = orderReasons({ zzz: { result: "ok", detail: "" }, model: { result: "ok", detail: "" } }).map(([k]) => k);
    expect(keys).toEqual(["model", "zzz"]);
  });
});

describe("body_type (docs/CARROCERIA.md)", () => {
  it("orders the body type right after the fuel, before the zone", () => {
    const keys = orderReasons({
      location: { result: "ok", detail: "" },
      body_type: { result: "fail", detail: "es Sedán, se busca SUV" },
      fuel: { result: "ok", detail: "" },
      model: { result: "ok", detail: "" },
    }).map(([k]) => k);
    expect(keys).toEqual(["model", "fuel", "body_type", "location"]);
    expect(whyText(1, 2, { body_type: { result: "unknown", detail: "" } }, 50)).toContain("body_type = unknown");
  });
});
