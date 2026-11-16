import { beforeEach, describe, expect, it, vi } from "vitest";

const m = vi.hoisted(() => ({ resolveMx: vi.fn() }));
vi.mock("server-only", () => ({}));
vi.mock("node:dns", () => ({ promises: { resolveMx: m.resolveMx } }));

import { clearEmailCheckCache, emailProblem, emailProblemMessage } from "@/lib/email-check";

const dnsError = (code: string) => Object.assign(new Error(code), { code });

beforeEach(() => {
  vi.resetAllMocks();
  clearEmailCheckCache();
  m.resolveMx.mockResolvedValue([{ exchange: "mx.example.com", priority: 10 }]);
});

describe("emailProblem", () => {
  it("lets a domain that takes mail through", async () => {
    expect(await emailProblem("persona@example.com")).toBeNull();
    expect(m.resolveMx).toHaveBeenCalledWith("example.com");
  });

  it("stops a typo of a common provider, with the fix, without asking the DNS", async () => {
    expect(await emailProblem("juan@gmail.con")).toEqual({ reason: "typo", suggestion: "juan@gmail.com" });
    expect(m.resolveMx).not.toHaveBeenCalled();
  });

  it("stops throwaway inboxes, subdomains included", async () => {
    expect(await emailProblem("a@mailinator.com")).toEqual({ reason: "disposable" });
    expect(await emailProblem("a@x.yopmail.com")).toEqual({ reason: "disposable" });
  });

  it("stops a domain with no mail servers, or a null MX", async () => {
    m.resolveMx.mockRejectedValueOnce(dnsError("ENOTFOUND"));
    expect(await emailProblem("a@no-such-domain.test")).toEqual({ reason: "no_mail" });
    m.resolveMx.mockRejectedValueOnce(dnsError("ENODATA"));
    expect(await emailProblem("a@web-only.test")).toEqual({ reason: "no_mail" });
    m.resolveMx.mockResolvedValueOnce([{ exchange: ".", priority: 0 }]);
    expect(await emailProblem("a@null-mx.test")).toEqual({ reason: "no_mail" });
  });

  it("lets it through when the DNS fails or is slow: our failure never stops anyone", async () => {
    m.resolveMx.mockRejectedValueOnce(dnsError("ETIMEOUT"));
    expect(await emailProblem("a@flaky.test")).toBeNull();
    vi.useFakeTimers();
    m.resolveMx.mockReturnValueOnce(new Promise(() => {}));
    const pending = emailProblem("a@slow.test");
    await vi.advanceTimersByTimeAsync(3000);
    expect(await pending).toBeNull();
    vi.useRealTimers();
  });

  it("asks the DNS once per domain for a while", async () => {
    await emailProblem("a@example.com");
    await emailProblem("b@example.com");
    expect(m.resolveMx).toHaveBeenCalledTimes(1);
  });

  it("says what to fix", () => {
    expect(emailProblemMessage({ reason: "typo", suggestion: "juan@gmail.com" })).toContain("juan@gmail.com");
    expect(emailProblemMessage({ reason: "disposable" })).toContain("temporales");
    expect(emailProblemMessage({ reason: "no_mail" })).toContain("no puede recibir");
  });
});
