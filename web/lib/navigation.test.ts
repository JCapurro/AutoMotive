import { describe, expect, it } from "vitest";

import { afterRecovery, recoveryNext, safeNext } from "@/lib/navigation";

describe("safeNext", () => {
  it("keeps same-site paths with their query", () => {
    expect(safeNext("/app/searches/new?prompt=Fiesta%20manual")).toBe("/app/searches/new?prompt=Fiesta%20manual");
    expect(safeNext("/app/pro?plan=pass_30&from=results")).toBe("/app/pro?plan=pass_30&from=results");
  });

  it.each([
    ["https://evil.example", "absolute URL"],
    ["//evil.example", "protocol-relative"],
    ["/.//evil.example", "dot segment that collapses into protocol-relative"],
    ["/a/..//evil.example", "parent segment that collapses into protocol-relative"],
    ["/\\evil.example", "backslash"],
    ["/\tevil.example", "tab the URL parser drops"],
    ["/\n/evil.example", "newline"],
    ["/\r/evil.example", "carriage return"],
    ["app", "relative path"],
    ["", "empty"],
  ])("rejects %j (%s)", (value) => {
    expect(safeNext(value)).toBe("/app");
    expect(safeNext(value, "/x")).toBe("/x");
  });
});

describe("recovery destinations", () => {
  it("only lead to the password form, carrying a safe inner destination", () => {
    expect(recoveryNext("/admin")).toBe("/auth/reset-password");
    expect(recoveryNext("/auth/reset-passwordX?next=/app")).toBe("/auth/reset-password");
    expect(recoveryNext(`/auth/reset-password?${new URLSearchParams({ next: "/app/pro?plan=pass_30" })}`))
      .toBe("/auth/reset-password?next=%2Fapp%2Fpro%3Fplan%3Dpass_30");
    expect(recoveryNext(`/auth/reset-password?${new URLSearchParams({ next: "//evil.example" })}`)).toBe("/auth/reset-password?next=%2Fapp");
  });

  it("end at the inner destination, or /app", () => {
    expect(afterRecovery(`/auth/reset-password?${new URLSearchParams({ next: "/app/settings" })}`)).toBe("/app/settings");
    expect(afterRecovery("/auth/reset-password")).toBe("/app");
    expect(afterRecovery("https://evil.example")).toBe("/app");
  });
});
