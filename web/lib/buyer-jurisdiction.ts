import "server-only";

import data from "@/lib/data/argentina-locations.json";
import type { CostConfig, Jurisdiction, Zone } from "@/lib/cost-estimator";
import { JURISDICTIONS } from "@/lib/cost-estimator";

/**
 * PAR-01: the buyer's jurisdiction from a search's zones. A port of
 * worker/normalization/zone.py nearest_locality (the same flat preselection of
 * _CANDIDATES localities, then haversine_km, over the same Georef file) and of
 * worker/intelligence/cost_estimator.py buyer_jurisdiction; the golden vectors
 * check both. Server-only: it loads the 4.022 localities.
 */

type City = { name: string; provinceId: string; lat: number; lon: number };
const CITIES: City[] = (data.cities as [string, string, string, string, number, number][]).map(
  ([, name, provinceId, , lat, lon]) => ({ name, provinceId, lat, lon }),
);
/** worker/normalization/zone.py _CANDIDATES */
const CANDIDATES = 8;
/** worker/normalization/geo.py _EARTH_RADIUS_KM */
const EARTH_RADIUS_KM = 6371.0088;
/** Python's math.radians multiplies by pi/180 (one rounding), so do we. */
const DEG_TO_RAD = Math.PI / 180;
/** Georef province codes: CABA, Buenos Aires; any other is "rest". */
const PROVINCE: Record<string, Jurisdiction> = { "02": "caba", "06": "ba" };

export function haversineKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const phi1 = lat1 * DEG_TO_RAD;
  const phi2 = lat2 * DEG_TO_RAD;
  const dPhi = (lat2 - lat1) * DEG_TO_RAD;
  const dLambda = (lon2 - lon1) * DEG_TO_RAD;
  const a = Math.sin(dPhi / 2) ** 2 + Math.cos(phi1) * Math.cos(phi2) * Math.sin(dLambda / 2) ** 2;
  return 2 * EARTH_RADIUS_KM * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

const nearestCache = new Map<string, { city: City; km: number }>();

/** The nearest Georef locality and its distance in km, cached by (lat, lon). */
export function nearestLocality(lat: number, lon: number): { city: City; km: number } {
  const key = `${lat},${lon}`;
  const hit = nearestCache.get(key);
  if (hit) return hit;
  const scale = Math.cos(lat * DEG_TO_RAD) ** 2;
  const flat = (c: City) => (c.lat - lat) ** 2 + scale * (c.lon - lon) ** 2;
  const candidates = CITIES.map((c) => ({ c, d: flat(c) }))
    .sort((a, b) => a.d - b.d)
    .slice(0, CANDIDATES)
    .map(({ c }) => c);
  let best = candidates[0];
  let bestKm = haversineKm(lat, lon, best.lat, best.lon);
  for (const c of candidates.slice(1)) {
    const km = haversineKm(lat, lon, c.lat, c.lon);
    if (km < bestKm) [best, bestKm] = [c, km];
  }
  const out = { city: best, km: bestKm };
  if (nearestCache.size > 4096) nearestCache.clear();
  nearestCache.set(key, out);
  return out;
}

function fold(text: string | null): string {
  return (text ?? "").normalize("NFD").replace(/\p{M}/gu, "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}

/**
 * The set of {caba, ba, rest} the search covers, or null (missing): a zone
 * without coordinates, or farther than buyer_zone.max_locality_km from the
 * nearest Argentine locality, voids it. AMBA covers CABA and Buenos Aires.
 */
export function buyerJurisdiction(zones: Zone[], cfg: CostConfig | null): Jurisdiction[] | null {
  const zone = cfg?.blocks.buyer_zone;
  if (!zone || !zones.length) return null;
  const out = new Set<Jurisdiction>();
  for (const z of zones) {
    if (z.lat == null || z.lon == null || !Number.isFinite(z.lat) || !Number.isFinite(z.lon)) return null;
    if (fold(z.label) === "amba") {
      out.add("caba").add("ba");
      continue;
    }
    const { city, km } = nearestLocality(z.lat, z.lon);
    if (km > zone.max_locality_km) return null;
    out.add(PROVINCE[city.provinceId] ?? "rest");
  }
  return JURISDICTIONS.filter((j) => out.has(j));
}
