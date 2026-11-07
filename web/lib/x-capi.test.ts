import { afterEach, beforeEach, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));
vi.mock("next/headers", () => ({ cookies: vi.fn(), headers: vi.fn() }));
vi.mock("@/lib/x-pixel", () => ({
  xPixelId: "rimgs",
  TWCLID_COOKIE: "x_twclid",
  X_EVENTS: { purchase: "tw-rimgs-buy01", signup: "tw-rimgs-sign1", firstSearch: "" },
}));

const fetchMock = vi.fn();
const attribution = { consent: true, twclid: "click-1", ip: "190.0.0.1", ua: "UA", url: "https://eseauto.com.ar/app/pro" };

beforeEach(() => {
  vi.resetModules();
  vi.stubEnv("X_PIXEL_TOKEN", "secret-token");
  vi.stubGlobal("fetch", fetchMock);
  fetchMock.mockResolvedValue({ ok: true });
});
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); vi.clearAllMocks(); });

const send = async (over: Record<string, unknown> = {}) => {
  const { sendXConversion } = await import("./x-capi");
  await sendXConversion({ conversion: "purchase", conversionId: "purchase:c1:7", at: new Date().toISOString(), attribution, ...over });
};
const body = () => JSON.parse(fetchMock.mock.calls[0][1].body).conversions[0];

it("posts the conversion with the token header, the event id and the click and browser identifiers", async () => {
  await send();
  expect(fetchMock.mock.calls[0][0]).toBe("https://ads-api.x.com/12/measurement/conversions/rimgs");
  expect(fetchMock.mock.calls[0][1].headers["X-Pixel-Token"]).toBe("secret-token");
  expect(body()).toMatchObject({
    event_id: "tw-rimgs-buy01", conversion_id: "purchase:c1:7", event_source_url: attribution.url,
    identifiers: [{ twclid: "click-1", ip_address: "190.0.0.1", user_agent: "UA" }],
  });
  expect(body().conversion_time).toMatch(/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$/);
});

it("needs the user agent to send the IP", async () => {
  await send({ attribution: { consent: true, ip: "190.0.0.1" } });
  expect(fetchMock).not.toHaveBeenCalled();
  await send({ attribution: { consent: true, twclid: "click-1", ip: "190.0.0.1" } });
  expect(body().identifiers).toEqual([{ twclid: "click-1" }]);
});

it("sends nothing without consent, without a token, without an event id or when too old", async () => {
  await send({ attribution: { consent: false } });
  await send({ attribution: null });
  await send({ conversion: "firstSearch" });
  await send({ at: new Date(Date.now() - 8 * 86_400_000) });
  vi.stubEnv("X_PIXEL_TOKEN", "");
  await send();
  expect(fetchMock).not.toHaveBeenCalled();
});

it("never throws when X fails", async () => {
  fetchMock.mockResolvedValue({ ok: false, status: 500 });
  vi.spyOn(console, "error").mockImplementation(() => {});
  await expect(send()).resolves.toBeUndefined();
});

it("reads the twclid cookie by default and nothing once the visitor rejects the banner", async () => {
  const { cookies, headers } = await import("next/headers");
  const { readXAttribution } = await import("./x-capi");
  const jar = (values: Record<string, string>) => ({ get: (name: string) => (name in values ? { value: values[name] } : undefined) });
  vi.mocked(headers).mockResolvedValue(new Headers({ "x-forwarded-for": "190.0.0.1, 10.0.0.1", "user-agent": "UA" }) as never);

  vi.mocked(cookies).mockResolvedValue(jar({ x_twclid: "click-1" }) as never);
  expect(await readXAttribution()).toMatchObject({ consent: true, twclid: "click-1", ip: "190.0.0.1", ua: "UA" });

  vi.mocked(cookies).mockResolvedValue(jar({ x_twclid: "click-1", ads_consent: "denied" }) as never);
  expect(await readXAttribution()).toEqual({ consent: false });
});
