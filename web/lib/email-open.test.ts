import { describe, expect, it } from "vitest";

import { openTarget } from "@/lib/email-open";

describe("openTarget", () => {
  it("reads an alert or a plan email", () => {
    expect(openTarget("42", "n")).toEqual({ kind: "n", id: 42 });
    expect(openTarget("7", "m")).toEqual({ kind: "m", id: 7 });
  });

  it("ignores anything else", () => {
    for (const [id, k] of [["42", null], ["42", "x"], ["0", "n"], ["-1", "n"], ["4.2", "n"], ["abc", "m"], ["9".repeat(19), "n"]] as const) {
      expect(openTarget(id, k)).toBeNull();
    }
  });
});
