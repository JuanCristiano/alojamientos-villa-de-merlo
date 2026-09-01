"""
04_extraer_osm.py

Fuente adicional del proyecto "Alojamientos Villa de Merlo".
Baja los puntos etiquetados como alojamiento en OpenStreetMap dentro del
área de Villa de Merlo, usando la Overpass API (gratuita, sin API key).

Esto NO reemplaza al directorio oficial ni prueba habilitación: es una
fuente independiente y abierta para comparar cobertura y detectar
alojamientos que el directorio oficial no lista (o viceversa).

Atribución obligatoria si se publica o presenta este dataset:
  "Datos © colaboradores de OpenStreetMap, disponibles bajo licencia ODbL."
  https://www.openstreetmap.org/copyright

Uso:
    python scripts/04_extraer_osm.py
"""

import csv
import datetime as dt
from pathlib import Path

import requests

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Overpass exige identificar el cliente: sin esto, algunos servidores
# devuelven 406 Not Acceptable directamente.
HEADERS = {
    "User-Agent": (
        "MerloAlojamientosBot/1.0 (proyecto de portfolio, uso educativo, "
        "contacto: jcristiano@hotmail.com.ar)"
    )
}

# Bounding box generoso alrededor de Villa de Merlo (sur, oeste, norte, este),
# para no perder alojamientos en zonas como Rincón del Este o camino a Piedra Blanca.
BBOX = (-32.42, -65.08, -32.28, -64.95)

# Tipos de OSM que consideramos "alojamiento" para este proyecto.
TIPOS_ALOJAMIENTO = ["hotel", "guest_house", "hostel", "apartment", "chalet", "motel", "camp_site"]

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "data" / "raw" / "alojamientos_osm_raw.csv"

FIELDNAMES = [
    "nombre_publicado",
    "categoria_publicada",
    "direccion_raw",
    "telefonos_raw",
    "email_raw",
    "instagram_raw",
    "web_raw",
    "etiquetas_raw",
    "url_origen",
    "fecha_extraccion",
    "fuente",
    "latitud",
    "longitud",
    "osm_id",
    "osm_tipo_elemento",
]


def construir_query() -> str:
    tipos_regex = "|".join(TIPOS_ALOJAMIENTO)
    s, w, n, e = BBOX
    return f"""
    [out:json][timeout:60];
    (
      node["tourism"~"^({tipos_regex})$"]({s},{w},{n},{e});
      way["tourism"~"^({tipos_regex})$"]({s},{w},{n},{e});
    );
    out center tags;
    """


def armar_direccion(tags: dict) -> str:
    partes = []
    calle = tags.get("addr:street", "")
    numero = tags.get("addr:housenumber", "")
    if calle:
        partes.append(f"{calle} {numero}".strip())
    if tags.get("addr:city"):
        partes.append(tags["addr:city"])
    return ", ".join(partes)


def main():
    print("Consultando Overpass API (puede tardar unos segundos)...")
    resp = requests.post(OVERPASS_URL, data={"data": construir_query()}, headers=HEADERS, timeout=90)
    resp.raise_for_status()
    data = resp.json()

    elementos = data.get("elements", [])
    print(f"Elementos encontrados: {len(elementos)}")

    filas = []
    for el in elementos:
        tags = el.get("tags", {})

        if el["type"] == "node":
            lat, lon = el.get("lat"), el.get("lon")
        else:  # way: la posición viene en "center"
            centro = el.get("center", {})
            lat, lon = centro.get("lat"), centro.get("lon")

        # OSM guarda accesibilidad como tag propio; lo mapeamos a nuestra
        # columna de etiquetas para que sea comparable con el oficial.
        etiquetas = []
        if tags.get("wheelchair") == "yes":
            etiquetas.append("Accesible")

        filas.append({
            "nombre_publicado": tags.get("name", ""),
            "categoria_publicada": tags.get("tourism", ""),
            "direccion_raw": armar_direccion(tags),
            "telefonos_raw": tags.get("phone", tags.get("contact:phone", "")),
            "email_raw": tags.get("email", tags.get("contact:email", "")),
            "instagram_raw": tags.get("contact:instagram", ""),
            "web_raw": tags.get("website", tags.get("contact:website", "")),
            "etiquetas_raw": " | ".join(etiquetas),
            "url_origen": f"https://www.openstreetmap.org/{el['type']}/{el['id']}",
            "fecha_extraccion": dt.date.today().isoformat(),
            "fuente": "openstreetmap",
            "latitud": lat,
            "longitud": lon,
            "osm_id": el["id"],
            "osm_tipo_elemento": el["type"],
        })

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(filas)

    sin_nombre = sum(1 for f in filas if not f["nombre_publicado"])
    print(f"\nListo. {len(filas)} elementos guardados en {OUTPUT_PATH}")
    if sin_nombre:
        print(f"Aviso: {sin_nombre} elementos no tienen el tag 'name' en OSM (quedan con nombre_publicado vacío).")
    print("\nRecordá citar la fuente si presentás este dataset:")
    print('  "Datos © colaboradores de OpenStreetMap, licencia ODbL"')
    print("  https://www.openstreetmap.org/copyright")


if __name__ == "__main__":
    main()
