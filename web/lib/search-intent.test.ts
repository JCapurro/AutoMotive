import { describe, expect, it } from "vitest";

import { ASSISTED_MAX_CHARS } from "@/lib/assisted";
import { safeNext } from "@/lib/navigation";
import { searchIntentPrompt, searchStartHref } from "@/lib/search-intent";

describe("landing search intent", () => {
  it("keeps the current route when the optional prompt is empty", () => {
    expect(searchStartHref(false)).toBe("/login?next=/app/searches/new");
    expect(searchStartHref(false, " \n ")).toBe("/login?next=/app/searches/new");
    expect(searchStartHref(true)).toBe("/app/searches/new");
  });

  it("preserves accents and URL punctuation through the login destination", () => {
    const prompt = "Busco Córdoba & zona norte, hasta USD 12.000 + automático? #1";
    const login = new URL(searchStartHref(false, ` ${prompt} `), "https://eseauto.test");
    const next = safeNext(login.searchParams.get("next"));
    const search = new URL(next, login.origin);
    expect(login.pathname).toBe("/login");
    expect(search.pathname).toBe("/app/searches/new");
    expect(search.searchParams.get("prompt")).toBe(prompt);
    expect(searchStartHref(true, prompt)).toBe(next);
  });

  it("accepts bounded text and ignores malformed or oversized URL values", () => {
    expect(searchIntentPrompt("  Fiesta manual  ")).toBe("Fiesta manual");
    expect(searchIntentPrompt(undefined)).toBe("");
    expect(searchIntentPrompt(["Fiesta", "Polo"])).toBe("");
    expect(searchIntentPrompt("a".repeat(ASSISTED_MAX_CHARS))).toHaveLength(ASSISTED_MAX_CHARS);
    expect(searchIntentPrompt("a".repeat(ASSISTED_MAX_CHARS + 1))).toBe("");
  });
});
