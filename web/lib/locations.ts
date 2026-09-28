/**
 * Places a search can be centered on. Coordinates come from the worker's
 * table (worker/normalization/geo.py), so the radius the web saves is measured
 * from the same points the worker geocodes listings against.
 * "AMBA" is the sección 4.3 preset: CABA's center and 60 km.
 */
export type Place = { id: string; label: string; lat: number; lon: number; radius: number };

export const AMBA: Place = { id: "amba", label: "AMBA", lat: -34.6037, lon: -58.3816, radius: 60 };

export const PLACES: Place[] = [
  { id: "caba", label: "CABA", lat: -34.6037, lon: -58.3816, radius: 20 },
  { id: "zona-norte", label: "Zona Norte (GBA)", lat: -34.4708, lon: -58.5286, radius: 25 },
  { id: "zona-oeste", label: "Zona Oeste (GBA)", lat: -34.6534, lon: -58.6198, radius: 25 },
  { id: "zona-sur", label: "Zona Sur (GBA)", lat: -34.7203, lon: -58.2545, radius: 25 },
  { id: "la-plata", label: "La Plata", lat: -34.9205, lon: -57.9536, radius: 30 },
  { id: "mar-del-plata", label: "Mar del Plata", lat: -38.0055, lon: -57.5426, radius: 40 },
  { id: "bahia-blanca", label: "Bahía Blanca", lat: -38.7183, lon: -62.2663, radius: 40 },
  { id: "tandil", label: "Tandil", lat: -37.3217, lon: -59.1332, radius: 40 },
  { id: "rosario", label: "Rosario", lat: -32.9442, lon: -60.6505, radius: 40 },
  { id: "santa-fe", label: "Santa Fe", lat: -31.6107, lon: -60.6973, radius: 40 },
  { id: "parana", label: "Paraná", lat: -31.7413, lon: -60.5115, radius: 40 },
  { id: "cordoba", label: "Córdoba", lat: -31.4201, lon: -64.1888, radius: 40 },
  { id: "mendoza", label: "Mendoza", lat: -32.8895, lon: -68.8458, radius: 40 },
  { id: "san-juan", label: "San Juan", lat: -31.5375, lon: -68.5364, radius: 40 },
  { id: "san-luis", label: "San Luis", lat: -33.3017, lon: -66.3378, radius: 40 },
  { id: "tucuman", label: "San Miguel de Tucumán", lat: -26.8083, lon: -65.2176, radius: 40 },
  { id: "salta", label: "Salta", lat: -24.7821, lon: -65.4232, radius: 40 },
  { id: "jujuy", label: "San Salvador de Jujuy", lat: -24.1858, lon: -65.2995, radius: 40 },
  { id: "corrientes", label: "Corrientes", lat: -27.4692, lon: -58.8306, radius: 40 },
  { id: "resistencia", label: "Resistencia", lat: -27.4519, lon: -58.9867, radius: 40 },
  { id: "posadas", label: "Posadas", lat: -27.3621, lon: -55.9009, radius: 40 },
  { id: "neuquen", label: "Neuquén", lat: -38.9516, lon: -68.0591, radius: 40 },
  { id: "bariloche", label: "Bariloche", lat: -41.1335, lon: -71.3103, radius: 40 },
  { id: "comodoro", label: "Comodoro Rivadavia", lat: -45.8641, lon: -67.4966, radius: 40 },
];

export function placeById(id: string): Place | undefined {
  return id === AMBA.id ? AMBA : PLACES.find((p) => p.id === id);
}

export function placeByLabel(label: string | null | undefined): Place | undefined {
  if (!label) return undefined;
  return [AMBA, ...PLACES].find((p) => p.label === label);
}
