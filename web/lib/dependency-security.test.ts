import { describe, expect, it } from "vitest";

import { SearchInput } from "./search-form";

describe("bounded validation of user-supplied search collections", () => {
  it.each(["trims", "sources", "body_types", "extra_locations"] as const)(
    "rejects oversized %s before creating one issue for every invalid element",
    (field) => {
      const result = SearchInput.safeParse({
        make: "Ford",
        model: "Fiesta",
        [field]: Array.from({ length: 1000 }, () => null),
      });

      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error.issues).toHaveLength(1);
        expect(result.error.issues[0]).toMatchObject({ code: "too_big", path: [field] });
      }
    },
  );

  it("still validates individual values within the permitted collection size", () => {
    const result = SearchInput.safeParse({ make: "Ford", model: "Fiesta", trims: [null] });

    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0]).toMatchObject({ code: "invalid_type", path: ["trims", 0] });
    }
  });
});
