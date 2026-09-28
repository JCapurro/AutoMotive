import { describe, expect, it } from "vitest";

import { unsubscribeToken } from "./unsubscribe";

describe("unsubscribeToken", () => {
  it("takes a uuid", () => {
    expect(unsubscribeToken("0B1C2D3E-4F50-4a6b-8c7d-9e0f1a2b3c4d")).toBe("0b1c2d3e-4f50-4a6b-8c7d-9e0f1a2b3c4d");
  });
  it("rejects anything else", () => {
    for (const v of [undefined, null, "", "abc", ["0b1c2d3e-4f50-4a6b-8c7d-9e0f1a2b3c4d"], "0b1c2d3e-4f50-4a6b-8c7d-9e0f1a2b3c4d; drop"]) {
      expect(unsubscribeToken(v)).toBeNull();
    }
  });
});
