import { describe, expect, it } from "vitest";

import { formatArPhone, normalizeArPhone } from "@/lib/phone";

describe("normalizeArPhone", () => {
  it.each([
    ["11 2345-6789", "+5491123456789"],
    ["011 15 2345-6789", "+5491123456789"],
    ["+54 9 11 2345 6789", "+5491123456789"],
    ["+54 11 2345 6789", "+5491123456789"],
    ["5491123456789", "+5491123456789"],
    ["0341 15 456-7890", "+5493414567890"],
    ["(0351) 456-7890", "+5493514567890"],
    ["2944 15 12-3456", "+5492944123456"],
  ])("%s → %s", (raw, expected) => {
    expect(normalizeArPhone(raw)).toBe(expected);
  });

  it.each(["", "1234", "abc", "11 2345-678", "0800 333 1234", "+1 415 555 0100", "11 99 2345-6789"])("rejects %s", (raw) => {
    expect(normalizeArPhone(raw)).toBeNull();
  });
});

describe("formatArPhone", () => {
  it("formats Buenos Aires and the rest of the country", () => {
    expect(formatArPhone("+5491123456789")).toBe("+54 9 11 2345-6789");
    expect(formatArPhone("+5493414567890")).toBe("+54 9 341 456-7890");
  });
  it("leaves anything else as it is", () => {
    expect(formatArPhone(null)).toBe("");
    expect(formatArPhone("+14155550100")).toBe("+14155550100");
  });
});
