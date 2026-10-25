import { describe, expect, it } from "vitest";

import { feedbackComment, feedbackEmailId, feedbackReason, offeredReasons } from "./email-feedback-reasons";

describe("email feedback links", () => {
  it("takes only the known reasons", () => {
    expect(feedbackReason("bought")).toBe("bought");
    expect(feedbackReason("spam")).toBeNull();
    expect(feedbackReason("toString")).toBeNull();
    expect(feedbackReason(["bought"])).toBeNull();
  });

  it("takes only numeric ids", () => {
    expect(feedbackEmailId("41")).toBe(41);
    expect(feedbackEmailId("41x")).toBeNull();
    expect(feedbackEmailId(undefined)).toBeNull();
  });

  it("trims the comment, caps it and drops an empty one", () => {
    expect(feedbackComment("  solo miraba ")).toBe("solo miraba");
    expect(feedbackComment("   ")).toBeNull();
    expect(feedbackComment("x".repeat(3000))).toHaveLength(2000);
  });

  it("offers wrong_search only after an assisted request", () => {
    expect(offeredReasons("search_abandoned", undefined)).toContain("wrong_search");
    expect(offeredReasons("search_feedback", "search_abandoned")).toContain("wrong_search");
    expect(offeredReasons("search_feedback", "search_not_started")).not.toContain("wrong_search");
    expect(offeredReasons("search_not_started", undefined)).toEqual(
      ["browsing", "missing_model", "unclear", "bought", "other"]);
  });
});
