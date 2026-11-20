import { describe, expect, it } from "vitest";

import { closedKey, isPhonePromptPlace, PHONE_PROMPT_PLACES, PHONE_PROMPT_TEXT, promptQuiet, viewedKey } from "@/lib/phone-prompt";

const NOW = 1_800_000_000_000;
const DAY = 86_400_000;

describe("the mobile asked again", () => {
  it("stays quiet for a week after it was closed, then comes back", () => {
    expect(promptQuiet(String(NOW - 1000), NOW)).toBe(true);
    expect(promptQuiet(String(NOW - 6 * DAY), NOW)).toBe(true);
    expect(promptQuiet(String(NOW - 7 * DAY), NOW)).toBe(false);
    expect(promptQuiet(String(NOW - 30 * DAY), NOW)).toBe(false);
  });

  it("is not quiet without a mark, with the old permanent mark or with a mark that makes no sense", () => {
    expect(promptQuiet(null, NOW)).toBe(false);
    expect(promptQuiet("", NOW)).toBe(false);
    expect(promptQuiet("1", NOW)).toBe(false);          // the old «closed forever» flag: asked again
    expect(promptQuiet("ayer", NOW)).toBe(false);
    expect(promptQuiet(String(NOW + DAY), NOW)).toBe(false);   // a clock set back
  });

  it("keeps a separate mark per place, and says why in each", () => {
    expect(new Set(PHONE_PROMPT_PLACES.map(closedKey)).size).toBe(4);
    expect(new Set(PHONE_PROMPT_PLACES.map(viewedKey)).size).toBe(4);
    expect(closedKey("home")).not.toBe("ea_phone_prompt_closed");
    for (const place of PHONE_PROMPT_PLACES) {
      expect(PHONE_PROMPT_TEXT[place].body).toContain("opcional");
      expect(PHONE_PROMPT_TEXT[place].body).toContain("sin tu permiso");
      expect(PHONE_PROMPT_TEXT[place].body).not.toContain("ni a nadie");
    }
    expect(isPhonePromptPlace("home")).toBe(true);
    expect(isPhonePromptPlace("datos")).toBe(false);
  });
});
