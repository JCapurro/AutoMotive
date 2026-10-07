import { afterEach, describe, expect, it, vi } from "vitest";
import { approximateLocationFromHeaders } from "./search-location";

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.resetModules();
});

function geoHeaders(overrides: Record<string, string> = {}) {
  return new Headers({
    "x-vercel-ip-country": "AR",
    "x-vercel-ip-city": "C%C3%B3rdoba",
    "x-vercel-ip-latitude": "-31.4201",
    "x-vercel-ip-longitude": "-64.1888",
    ...overrides,
  });
}

function browser(state: PermissionState, getCurrentPosition = vi.fn()) {
  vi.stubGlobal("navigator", {
    permissions: { query: vi.fn().mockResolvedValue({ state }) },
    geolocation: { getCurrentPosition },
  });
  return getCurrentPosition;
}

const position = { coords: { latitude: -34.6037, longitude: -58.3816 } } as GeolocationPosition;
const geoError = (code: number) => ({ code }) as GeolocationPositionError;

describe("automatic connection zone", () => {
  it("uses the request's estimate with a visible approximate label and rounded coordinates", () => {
    expect(approximateLocationFromHeaders(geoHeaders())).toEqual({
      label: "Córdoba (zona aproximada)", lat: -31.42, lon: -64.19, approximate: true,
    });
  });

  it("does not invent a zone when headers are absent or the connection is outside Argentina", () => {
    expect(approximateLocationFromHeaders(new Headers())).toBeNull();
    expect(approximateLocationFromHeaders(geoHeaders({ "x-vercel-ip-country": "US" }))).toBeNull();
  });

  it.each(["", " ", "NaN", "Infinity", "-91"])("rejects invalid latitude %j", (latitude) => {
    expect(approximateLocationFromHeaders(geoHeaders({ "x-vercel-ip-latitude": latitude }))).toBeNull();
  });

  it("handles invalid longitude and malformed encoded city names", () => {
    expect(approximateLocationFromHeaders(geoHeaders({ "x-vercel-ip-longitude": "181" }))).toBeNull();
    expect(approximateLocationFromHeaders(geoHeaders({ "x-vercel-ip-city": "%invalid" }))?.label).toBe("Mi zona aproximada");
  });
});

describe("device location", () => {
  it.each(["prompt", "denied"] as const)("does not open a permission prompt when permission is %s", async (state) => {
    const get = browser(state);
    const { detectDeviceLocation } = await import("./search-location");
    expect(await detectDeviceLocation()).toEqual({ location: null, reason: state === "denied" ? "denied" : "permission" });
    expect(get).not.toHaveBeenCalled();
  });

  it("automatically retries a temporary failure and succeeds without a second click", async () => {
    const get = browser("granted", vi.fn()
      .mockImplementationOnce((_success, failure) => failure(geoError(2)))
      .mockImplementationOnce((success) => success(position)));
    const { detectDeviceLocation } = await import("./search-location");
    expect(await detectDeviceLocation()).toEqual({
      location: { label: "Mi ubicación actual", lat: -34.6, lon: -58.38, approximate: false },
    });
    expect(get).toHaveBeenCalledTimes(2);
    expect(get.mock.calls[0][2].enableHighAccuracy).toBe(false);
    expect(get.mock.calls[1][2].enableHighAccuracy).toBe(true);
    expect(get.mock.calls[0][2].maximumAge).toBe(300_000);
  });

  it("lets an explicit click request permission but never retries a denial", async () => {
    const get = browser("prompt", vi.fn((_success, failure) => failure(geoError(1))));
    const { detectDeviceLocation } = await import("./search-location");
    expect(await detectDeviceLocation(true)).toEqual({ location: null, reason: "denied" });
    expect(get).toHaveBeenCalledTimes(1);
  });

  it("shares a pending read among several assisted forms", async () => {
    let complete!: PositionCallback;
    const get = browser("granted", vi.fn((success) => { complete = success; }));
    const { detectDeviceLocation } = await import("./search-location");
    const first = detectDeviceLocation();
    const second = detectDeviceLocation();
    await vi.waitFor(() => expect(get).toHaveBeenCalledTimes(1));
    complete(position);
    expect(await first).toEqual(await second);
  });

  it("stops waiting after both attempts even when the browser never calls back", async () => {
    vi.useFakeTimers();
    const get = browser("granted");
    const { detectDeviceLocation } = await import("./search-location");
    const result = detectDeviceLocation();
    await vi.advanceTimersByTimeAsync(10_000);
    expect(await result).toEqual({ location: null, reason: "timeout" });
    expect(get).toHaveBeenCalledTimes(2);
  });

  it("bounds a stuck permission lookup and supports browsers without a Permissions API", async () => {
    vi.useFakeTimers();
    const get = browser("granted");
    vi.mocked(navigator.permissions.query).mockImplementation(() => new Promise(() => {}));
    const { detectDeviceLocation } = await import("./search-location");
    const result = detectDeviceLocation();
    await vi.advanceTimersByTimeAsync(1_000);
    expect(await result).toEqual({ location: null, reason: "permission" });
    expect(get).not.toHaveBeenCalled();
    vi.stubGlobal("navigator", { geolocation: { getCurrentPosition: get } });
    expect(await detectDeviceLocation()).toEqual({ location: null, reason: "permission" });
    expect(get).not.toHaveBeenCalled();
  });

  it("returns an unavailable result when geolocation is unsupported", async () => {
    vi.stubGlobal("navigator", {});
    const { detectDeviceLocation } = await import("./search-location");
    expect(await detectDeviceLocation()).toEqual({ location: null, reason: "unavailable" });
  });
});
