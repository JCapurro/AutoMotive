import data from "@/lib/data/argentina-locations.json";
import type { Place } from "@/lib/locations";

/** Official Georef census localities, bundled so the selectors work offline. */
export const PROVINCES = data.provinces.map(([id, label]) => ({ id, label }));
export type City = Place & { provinceId: string; city: string; department: string };
export const CITIES: City[] = data.cities.filter((row) => row[2] !== "02").map((row) => {
  const [id, city, provinceId, department, lat, lon] = row as [string, string, string, string, number, number];
  const province = PROVINCES.find((p) => p.id === provinceId)!;
  return { id, city, provinceId, department, label: `${city}, ${province.label}`.slice(0, 80), lat, lon, radius: 30 };
});
// CABA is one city. Census communes should not appear as separate cities.
CITIES.push({ id: "caba", city: "Ciudad de Buenos Aires", provinceId: "02", department: "",
  label: "Ciudad de Buenos Aires, CABA", lat: -34.6037, lon: -58.3816, radius: 30 });
CITIES.sort((a, b) => a.city.localeCompare(b.city, "es"));

export function cityById(id: string): City | undefined {
  return CITIES.find((city) => city.id === id);
}

export function citiesInProvince(id: string): City[] {
  return CITIES.filter((city) => city.provinceId === id);
}

export function cityByLocation(location: { label: string; lat: number; lon: number }): City | undefined {
  return CITIES.find((city) => city.lat === location.lat && city.lon === location.lon && city.label === location.label);
}

function fold(text: string): string {
  return text.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}

/** A province's capital, for «Chaco» or «en Misiones» (a province alone doesn't name a locality). */
const CAPITALS: Record<string, string> = {
  chaco: "Resistencia", corrientes: "Corrientes", misiones: "Posadas", formosa: "Formosa",
  "entre rios": "Paraná", "santa fe": "Santa Fe", cordoba: "Córdoba", tucuman: "San Miguel de Tucumán",
  salta: "Salta", jujuy: "San Salvador de Jujuy", "santiago del estero": "Santiago del Estero",
  catamarca: "San Fernando del Valle de Catamarca", "la rioja": "La Rioja", "san juan": "San Juan",
  mendoza: "Mendoza", "san luis": "San Luis", "la pampa": "Santa Rosa", neuquen: "Neuquén",
  "rio negro": "Viedma", chubut: "Rawson", "santa cruz": "Río Gallegos", "tierra del fuego": "Ushuaia",
};

/** The capital of the province the text names alone ("Chaco", "provincia de Chaco"); undefined otherwise. */
export function provinceCapital(text: string): City | undefined {
  const name = fold(text).replace(/^(la |el )?(provincia|prov) (de |del )?/, "").replace(/^(la |el )/, "");
  const capital = CAPITALS[name];
  const province = capital ? PROVINCES.find((p) => fold(p.label) === name) : undefined;
  return province ? citiesInProvince(province.id).find((c) => fold(c.city) === fold(capital)) : undefined;
}

/** Avoid guessing when multiple provinces contain the same city name. */
export function cityFromText(text: string): City | undefined {
  const query = ` ${fold(text)} `;
  const candidates = CITIES.filter((c) => query.includes(` ${fold(c.city)} `));
  if (!candidates.length) return undefined;
  const longest = Math.max(...candidates.map((c) => fold(c.city).length));
  const matches = candidates.filter((c) => fold(c.city).length === longest);
  const province = PROVINCES.find((p) => query.includes(` ${fold(p.label)} `));
  const scoped = province ? matches.filter((c) => c.provinceId === province.id) : matches;
  return scoped.length === 1 ? scoped[0] : undefined;
}
