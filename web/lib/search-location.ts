export type DetectedLocation = {
  label: string;
  lat: number;
  lon: number;
  approximate: boolean;
};

const round = (value: number) => Math.round(value * 100) / 100;

/** Vercel supplies this estimate with the request; no external lookup or IP storage. */
export function approximateLocationFromHeaders(headers: Pick<Headers, "get">): DetectedLocation | null {
  if (headers.get("x-vercel-ip-country") !== "AR") return null;
  const latitude = headers.get("x-vercel-ip-latitude")?.trim();
  const longitude = headers.get("x-vercel-ip-longitude")?.trim();
  if (!latitude || !longitude) return null;
  const lat = Number(latitude);
  const lon = Number(longitude);
  if (!Number.isFinite(lat) || !Number.isFinite(lon) || lat < -90 || lat > 90 || lon < -180 || lon > 180) return null;
  let city = "";
  try {
    city = decodeURIComponent(headers.get("x-vercel-ip-city") ?? "").trim();
  } catch { /* A malformed city name must not prevent using valid coordinates. */ }
  return {
    label: (city ? `${city} (zona aproximada)` : "Mi zona aproximada").slice(0, 80),
    lat: round(lat),
    lon: round(lon),
    approximate: true,
  };
}

export type LocationResult =
  | { location: DetectedLocation; reason?: never }
  | { location: null; reason: "permission" | "denied" | "unavailable" | "timeout" };

let pendingPosition: Promise<LocationResult> | null = null;

function positionAttempt(geolocation: Geolocation, highAccuracy: boolean, timeout: number): Promise<LocationResult> {
  return new Promise((resolve) => {
    let settled = false;
    const finish = (result: LocationResult) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve(result);
    };
    // The browser's timeout excludes time spent waiting for permission. Bound that too.
    const timer = setTimeout(() => finish({ location: null, reason: "timeout" }), timeout);
    try {
      geolocation.getCurrentPosition(
        (position) => {
          const { latitude, longitude } = position.coords;
          if (!Number.isFinite(latitude) || !Number.isFinite(longitude) || Math.abs(latitude) > 90 || Math.abs(longitude) > 180) {
            finish({ location: null, reason: "unavailable" });
            return;
          }
          finish({ location: {
            label: "Mi ubicación actual", lat: round(latitude), lon: round(longitude), approximate: false,
          } });
        },
        (error) => finish({ location: null, reason: error.code === 1 ? "denied" : error.code === 3 ? "timeout" : "unavailable" }),
        { enableHighAccuracy: highAccuracy, maximumAge: 300_000, timeout },
      );
    } catch {
      finish({ location: null, reason: "unavailable" });
    }
  });
}

/** Automatic reads never open a permission prompt. An explicit click may request permission. */
export async function detectDeviceLocation(requestPermission = false): Promise<LocationResult> {
  if (typeof navigator === "undefined" || !navigator.geolocation) return { location: null, reason: "unavailable" };
  if (!requestPermission) {
    if (!navigator.permissions?.query) return { location: null, reason: "permission" };
    let timer: ReturnType<typeof setTimeout> | undefined;
    try {
      const permission = await Promise.race([
        navigator.permissions.query({ name: "geolocation" }),
        new Promise<null>((resolve) => { timer = setTimeout(() => resolve(null), 1_000); }),
      ]);
      if (permission?.state !== "granted") return { location: null, reason: permission?.state === "denied" ? "denied" : "permission" };
    } catch {
      return { location: null, reason: "permission" };
    } finally {
      clearTimeout(timer);
    }
  }
  // Assisted searches can mount several forms together. Share the device request.
  if (!pendingPosition) {
    pendingPosition = (async () => {
      const first = await positionAttempt(navigator.geolocation, false, 4_000);
      if (first.location || first.reason === "denied") return first;
      return positionAttempt(navigator.geolocation, true, 6_000);
    })().finally(() => { pendingPosition = null; });
  }
  return pendingPosition;
}
