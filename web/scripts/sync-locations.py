"""Refresh the offline city/province catalog from Argentina's official Georef API.

Run from any directory: python web/scripts/sync-locations.py
Source: https://www.argentina.gob.ar/georef/descarga-de-la-base-completa
"""
import json
from pathlib import Path
from urllib.request import urlopen

BASE = "https://apis.datos.gob.ar/georef/api/v2.0/"


def fetch(resource, fields):
    with urlopen(f"{BASE}{resource}?max=5000&campos={fields}&orden=nombre", timeout=30) as response:
        data = json.load(response)
    rows = data[resource.replace("-", "_")]
    if len(rows) != data["total"]:
        raise ValueError(f"Incomplete {resource} response")
    return rows


provinces = fetch("provincias", "id,nombre")
cities = fetch("localidades-censales", "id,nombre,centroide,provincia,departamento")
data = {
    "source": BASE + "localidades-censales",
    "provinces": [[p["id"], p["nombre"]] for p in provinces],
    "cities": [
        [c["id"], c["nombre"], c["provincia"]["id"], c["departamento"]["nombre"],
         round(c["centroide"]["lat"], 5), round(c["centroide"]["lon"], 5)]
        for c in cities
    ],
}
target = Path(__file__).resolve().parents[1] / "lib/data/argentina-locations.json"
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
print(f"Saved {len(provinces)} provinces and {len(cities)} cities ({target.stat().st_size:,} bytes)")
