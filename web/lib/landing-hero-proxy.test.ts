import { beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

const mocks = vi.hoisted(() => ({ getClaims: vi.fn() }));
vi.mock("@supabase/ssr", () => ({ createServerClient: () => ({ auth: { getClaims: mocks.getClaims } }) }));
import { proxy } from "@/proxy";

const page = (path: string, headers: Record<string, string> = {}) =>
  proxy(new NextRequest(`https://www.eseauto.com.ar${path}`, { headers: { "sec-fetch-dest": "document", ...headers } }));
const bucket = (response: Response) => response.headers.getSetCookie().find((c) => c.startsWith("hero_bucket="));

beforeEach(() => mocks.getClaims.mockResolvedValue({ data: { claims: null } }));

describe("the hero test's bucket in the proxy", () => {
  it("draws one from 0 to 99 on the first visit to the home, and hands it to that very render", async () => {
    const response = await page("/?utm_source=ig");
    const cookie = bucket(response);
    expect(cookie).toMatch(/^hero_bucket=\d{1,2};/);
    expect(cookie).toMatch(/HttpOnly/i);
    expect(cookie).toMatch(/Max-Age=7776000/i);
    // NextResponse.next({ request }) forwards the request's cookies to the page.
    expect(response.headers.get("x-middleware-request-cookie")).toContain(cookie!.split(";")[0]);
  });

  it("never redraws it, nor draws one off the home, on refusal, for prefetches or for signed-in users", async () => {
    expect(bucket(await page("/", { cookie: "hero_bucket=7" }))).toBeUndefined();
    expect(bucket(await page("/planes"))).toBeUndefined();
    expect(bucket(await page("/guias/ford/focus"))).toBeUndefined();
    expect(bucket(await page("/", { cookie: "ads_consent=denied" }))).toBeUndefined();
    expect(bucket(await page("/", { rsc: "1" }))).toBeUndefined();
    expect(bucket(await page("/", { "sec-fetch-dest": "empty" }))).toBeUndefined();
    mocks.getClaims.mockResolvedValue({ data: { claims: { sub: "u1" } } });
    expect(bucket(await page("/"))).toBeUndefined();
  });
});
