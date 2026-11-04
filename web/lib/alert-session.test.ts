import { describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

import { alertLinkSecrets, alertLinkSignature, validAlertLinkSignature } from "@/lib/alert-session";

const SECRET = "alert-link-test-secret-0123456789abcdef";
const OWNER = "8d3a7c4e-1f2b-4c5d-9e6f-0a1b2c3d4e5f";
const sig = (scope: "r" | "m", id: number) => alertLinkSignature(SECRET, scope, id, OWNER);

describe("email signatures retained for scoped feedback", () => {
  it("preserves the worker's signature vectors for previously sent links", () => {
    expect(sig("r", 42)).toBe("QmbEMrNzw4hGRVgh7FPfPw");
    expect(sig("m", 7)).toBe("txvVh27uBxAp7KCEPptC0w");
  });

  it("binds the kind of email, its id and its owner", () => {
    const link = { scope: "m" as const, id: 7, signature: sig("m", 7) };
    expect(validAlertLinkSignature(link, OWNER, [SECRET])).toBe(true);
    expect(validAlertLinkSignature({ ...link, id: 8 }, OWNER, [SECRET])).toBe(false);
    expect(validAlertLinkSignature({ ...link, scope: "r" }, OWNER, [SECRET])).toBe(false);
    expect(validAlertLinkSignature(link, "another-user", [SECRET])).toBe(false);
    expect(validAlertLinkSignature(link, OWNER, [`${SECRET}-new`])).toBe(false);
    for (const signature of [null, "", `${sig("m", 7)}=`, sig("m", 7).slice(0, 21), "../../etc/passwd!!"]) {
      expect(validAlertLinkSignature({ ...link, signature }, OWNER, [SECRET])).toBe(false);
    }
  });

  it("accepts the previous secret while rotating and ignores short secrets", () => {
    const fresh = `${SECRET}-rotated`;
    expect(alertLinkSecrets({ ALERT_LINK_SECRET: fresh, ALERT_LINK_SECRET_PREVIOUS: SECRET })).toEqual([fresh, SECRET]);
    expect(validAlertLinkSignature({ scope: "m", id: 7, signature: sig("m", 7) }, OWNER, [fresh, SECRET])).toBe(true);
    expect(alertLinkSecrets({ ALERT_LINK_SECRET: "x".repeat(31) })).toEqual([]);
    expect(alertLinkSecrets({})).toEqual([]);
  });
});
