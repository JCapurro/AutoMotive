import { beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

const mocks = vi.hoisted(() => ({ getClaims: vi.fn() }));
vi.mock("@supabase/ssr", () => ({ createServerClient: () => ({ auth: { getClaims: mocks.getClaims } }) }));
import { parseOrigin } from "./acquisition";
import { proxy } from "@/proxy";

const page = (path: string, headers: Record<string, string> = {}) =>
  proxy(new NextRequest(`https://www.eseauto.com.ar${path}`, { headers: { "sec-fetch-dest": "document", ...headers } }));
const kept = (response: Response) => response.headers.getSetCookie().find((c) => c.startsWith("first_touch="));

beforeEach(() => mocks.getClaims.mockResolvedValue({ data: { claims: null } }));

describe("first touch in the proxy", () => {
  it("keeps the first page of an anonymous visit", async () => {
    const cookie = kept(await page("/guias/ford/focus?utm_source=whatsapp", { referer: "https://l.facebook.com/" }));
    expect(cookie).toMatch(/HttpOnly/i);
    const value = decodeURIComponent(cookie!.split(";")[0].slice("first_touch=".length));
    expect(parseOrigin(value)).toMatchObject({ source: "whatsapp", referrer: "l.facebook.com", landing: "/guias/ford/focus" });
  });

  it("never rewrites it, nor keeps it on refusal, prefetches, alert links or for signed-in users", async () => {
    expect(kept(await page("/?utm_source=x", { cookie: "first_touch=%7B%7D" }))).toBeUndefined();
    expect(kept(await page("/", { cookie: "ads_consent=denied" }))).toBeUndefined();
    expect(kept(await page("/", { rsc: "1" }))).toBeUndefined();
    expect(kept(await page("/", { "sec-fetch-dest": "empty" }))).toBeUndefined();
    expect(kept(await page("/r/12?to=listing"))).toBeUndefined();
    mocks.getClaims.mockResolvedValue({ data: { claims: { sub: "u1" } } });
    expect(kept(await page("/planes"))).toBeUndefined();
  });
});
