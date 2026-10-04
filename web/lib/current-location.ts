/** Resolve a locality, without requesting a street or house number. */
export async function currentLocationLabel(lat: number, lon: number): Promise<string | null> {
  try {
    const params = new URLSearchParams({
      lat: String(lat), lon: String(lon), format: "jsonv2",
      zoom: "14", addressdetails: "1", "accept-language": "es", layer: "address",
    });
    const response = await fetch(`https://nominatim.openstreetmap.org/reverse?${params}`, {
      signal: AbortSignal.timeout(5_000),
    });
    if (!response.ok) return null;
    const data = await response.json();
    const address = data.address;
    if (!address || typeof address !== "object") return null;
    const locality = address.city || address.town || address.village || address.municipality;
    const district = address.suburb || address.neighbourhood;
    const parts = [district, locality, address.state].filter(
      (value): value is string => typeof value === "string" && value.trim().length > 0,
    );
    return [...new Set(parts)].join(", ") || null;
  } catch {
    return null;
  }
}
