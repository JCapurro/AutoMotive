import { DEVICE_LABEL, type DetectedLocation } from "@/lib/search-location";

/**
 * «Mi ubicación» on the landing (lib/landing-hero.ts): the coordinates the
 * phone gave wait in this browser until the search is created, instead of
 * travelling in a URL or an email link. Read once, and only while fresh;
 * without storage the search falls back to the approximate zone, as before.
 */
const KEY = "ea_here";
const MAX_AGE_MS = 30 * 60_000;

export function storeHere(location: Pick<DetectedLocation, "lat" | "lon">, now: number = Date.now()): void {
  try {
    localStorage.setItem(KEY, JSON.stringify({ lat: location.lat, lon: location.lon, at: now }));
  } catch { /* No storage: the approximate zone is used. */ }
}

export function clearHere(): void {
  try {
    localStorage.removeItem(KEY);
  } catch { /* Nothing to clear. */ }
}

/** The stored place as a device location, consumed; null when absent, stale or malformed. */
export function takeHere(now: number = Date.now()): DetectedLocation | null {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    localStorage.removeItem(KEY);
    const { lat, lon, at } = JSON.parse(raw) as { lat?: unknown; lon?: unknown; at?: unknown };
    if (typeof lat !== "number" || typeof lon !== "number" || typeof at !== "number") return null;
    if (!Number.isFinite(lat) || !Number.isFinite(lon) || lat < -90 || lat > 90 || lon < -180 || lon > 180) return null;
    if (now - at > MAX_AGE_MS || now < at) return null;
    return { label: DEVICE_LABEL, lat, lon, approximate: false };
  } catch {
    return null;
  }
}
