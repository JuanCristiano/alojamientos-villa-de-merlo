"""
06_cruzar_fuentes.py

Compara el directorio oficial limpio (data/processed/alojamientos_oficial_clean.csv)
contra la fuente de OpenStreetMap (data/raw/alojamientos_osm_raw.csv), para ver
qué aparece en ambas fuentes, qué está solo en el oficial, y qué aparece solo en OSM.

IMPORTANTE — qué NO es este script:
No determina qué alojamientos están "habilitados" o "no habilitados". Un
alojamiento que aparece solo en OSM puede ser:
  - un alojamiento real que el directorio oficial no tiene cargado,
  - un dato viejo o desactualizado en OSM,
  - un alquiler temporal cargado por un vecino, sin relación con habilitación.
El resultado es una lista de CANDIDATOS para revisión manual, no una conclusión.

Tampoco fusiona registros automáticamente: solo indica coincidencias por
similitud de nombre, para que una persona decida caso por caso.

Cómo compara los nombres (importante para entender los resultados):
Cada fuente nombra las cosas distinto: el oficial suele guardar solo el
nombre propio ("Nona Olga"), mientras que OSM casi siempre antepone el tipo
de alojamiento ("Cabañas Nona Olga", "Hotel Algarrobo"). Comparar las
cadenas completas letra por letra penaliza mucho ese prefijo/sufijo. Por
eso primero se sacan palabras genéricas del rubro (cabañas, hotel, complejo,
posada, etc.) y se compara lo que queda, combinando dos métricas:
  - similitud de caracteres (agarra errores de tipeo, ej. "Algarrobo"/"Algorrobo")
  - superposición de palabras (agarra reordenamientos y agregados, ej.
    "Hostería Serrana" pegado al final de un nombre)

Uso:
    python scripts/06_cruzar_fuentes.py
"""

import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd

OFICIAL_PATH = Path(__file__).resolve().parent.parent / "data" / "processed" / "alojamientos_oficial_clean.csv"
OSM_PATH = Path(__file__).resolve().parent.parent / "data" / "raw" / "alojamientos_osm_raw.csv"
SALIDA_PATH = Path(__file__).resolve().parent.parent / "data" / "processed" / "comparacion_fuentes.csv"
REPORTE_PATH = Path(__file__).resolve().parent.parent / "data" / "processed" / "reporte_cruce_fuentes.txt"

UMBRAL_MATCH = 0.68

# Palabras de rubro que casi siempre aparecen pegadas al nombre propio y que
# NO ayudan a identificar el alojamiento (todo ya normalizado: sin tildes,
# minúsculas). Sacarlas antes de comparar evita que "Cabañas X" y "X" se
# vean como cosas distintas.
PALABRAS_GENERICAS = {
    "cabana", "cabanas", "cabin", "hotel", "hoteles", "hosteria", "hosterias",
    "hostal", "hostales", "hostel", "hostels", "posada", "posadas", "complejo",
    "complejos", "apart", "aparts", "resort", "spa", "camping", "duplex",
    "dupex", "villa", "chalet", "chalets", "boutique", "suite", "suites",
    "departamento", "departamentos", "casa", "y", "de", "del", "la", "el",
    "los", "las",
}


def normalizar(texto: str) -> str:
    if not isinstance(texto, str):
        return ""
    texto = texto.lower().strip()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto)


def nucleo(texto_norm: str) -> str:
    """Saca las palabras de rubro (cabañas, hotel, etc.) y deja el nombre propio."""
    palabras = [p for p in texto_norm.split() if p not in PALABRAS_GENERICAS]
    return " ".join(palabras) if palabras else texto_norm


def similitud(nombre_a: str, nombre_b: str) -> float:
    """Combina similitud de caracteres y superposición de palabras sobre el
    núcleo del nombre (sin palabras de rubro), y se queda con la mejor."""
    norm_a, norm_b = normalizar(nombre_a), normalizar(nombre_b)
    nucleo_a, nucleo_b = nucleo(norm_a), nucleo(norm_b)

    ratio_nucleo = SequenceMatcher(None, nucleo_a, nucleo_b).ratio()
    ratio_completo = SequenceMatcher(None, norm_a, norm_b).ratio()

    palabras_a = {p for p in nucleo_a.split() if len(p) > 2}
    palabras_b = {p for p in nucleo_b.split() if len(p) > 2}
    if palabras_a and palabras_b:
        jaccard = len(palabras_a & palabras_b) / len(palabras_a | palabras_b)
    else:
        jaccard = 0.0

    return max(ratio_nucleo, ratio_completo, jaccard)


def mejor_match(nombre: str, candidatos: list[str]) -> tuple[int | None, float]:
    mejor_idx, mejor_score = None, 0.0
    for idx, candidato in enumerate(candidatos):
        score = similitud(nombre, candidato)
        if score > mejor_score:
            mejor_score, mejor_idx = score, idx
    return mejor_idx, mejor_score


def main():
    if not OFICIAL_PATH.exists():
        print(f"No encuentro {OFICIAL_PATH}. ¿Corriste 03_limpiar_y_normalizar.py?")
        return
    if not OSM_PATH.exists():
        print(f"No encuentro {OSM_PATH}. ¿Corriste 04_extraer_osm.py?")
        return

    oficial = pd.read_csv(OFICIAL_PATH, dtype=str, keep_default_na=False)
    osm = pd.read_csv(OSM_PATH, dtype=str, keep_default_na=False)

    osm = osm[osm["nombre_publicado"].str.strip() != ""].reset_index(drop=True)
    osm_unico = osm.drop_duplicates(subset="nombre_publicado").reset_index(drop=True)

    nombres_oficial = oficial["nombre"].tolist()
    nombres_osm = osm_unico["nombre_publicado"].tolist()

    filas = []
    matches_osm_usados = set()

    for i, nombre_of in enumerate(nombres_oficial):
        idx, score = mejor_match(nombre_of, nombres_osm)
        coincide = idx is not None and score >= UMBRAL_MATCH
        if coincide:
            matches_osm_usados.add(idx)
        filas.append({
            "nombre": nombre_of,
            "en_oficial": "si",
            "en_osm": "si" if coincide else "no",
            "mejor_candidato_osm": nombres_osm[idx] if idx is not None else "",
            "similitud": round(score, 2),
            "categoria_oficial": oficial["categoria"].iloc[i],
            "categoria_osm": osm_unico["categoria_publicada"].iloc[idx] if coincide else "",
        })

    for j, nombre_osm in enumerate(nombres_osm):
        if j in matches_osm_usados:
            continue
        idx, score = mejor_match(nombre_osm, nombres_oficial)
        coincide = idx is not None and score >= UMBRAL_MATCH
        if coincide:
            continue  # ya lo capturó el bucle anterior desde el otro lado
        filas.append({
            "nombre": nombre_osm,
            "en_oficial": "no",
            "en_osm": "si",
            "mejor_candidato_osm": "",
            "similitud": round(score, 2) if idx is not None else 0.0,
            "categoria_oficial": "",
            "categoria_osm": osm_unico["categoria_publicada"].iloc[j],
        })

    df_comparacion = pd.DataFrame(filas)
    SALIDA_PATH.parent.mkdir(parents=True, exist_ok=True)
    df_comparacion.to_csv(SALIDA_PATH, index=False, encoding="utf-8")

    en_ambas = (df_comparacion["en_oficial"] == "si") & (df_comparacion["en_osm"] == "si")
    solo_oficial = (df_comparacion["en_oficial"] == "si") & (df_comparacion["en_osm"] == "no")
    solo_osm = (df_comparacion["en_oficial"] == "no") & (df_comparacion["en_osm"] == "si")

    lineas = []
    lineas.append("Reporte de cruce de fuentes — directorio oficial vs OpenStreetMap")
    lineas.append(f"Total oficial: {len(oficial)}  |  Total OSM (nombres únicos): {len(osm_unico)}")
    lineas.append(f"Umbral de coincidencia: {UMBRAL_MATCH}")
    lineas.append("")
    lineas.append(f"En ambas fuentes:                      {en_ambas.sum()}")
    lineas.append(f"Solo en el directorio oficial:         {solo_oficial.sum()}")
    lineas.append(f"Solo en OSM (candidatos a revisar):    {solo_osm.sum()}")
    lineas.append("")

    lineas.append("== Solo en el oficial — con el mejor candidato de OSM aunque no haya pasado el umbral ==")
    lineas.append("   (revisar a mano los que tengan similitud cercana al umbral, puede ser el mismo lugar)")
    for _, fila in df_comparacion[solo_oficial].iterrows():
        candidato = fila["mejor_candidato_osm"] or "(sin candidato parecido)"
        lineas.append(f"  {fila['nombre']:40s} -> mejor candidato OSM: {candidato} (similitud {fila['similitud']})")
    lineas.append("")

    lineas.append("== Solo en OSM (candidatos — revisar antes de asumir nada) ==")
    for _, fila in df_comparacion[solo_osm].iterrows():
        lineas.append(f"  {fila['nombre']}  (tipo OSM: {fila['categoria_osm']})")
    lineas.append("")

    lineas.append("NOTA: 'solo en OSM' no implica que el alojamiento no esté habilitado.")
    lineas.append("Puede faltar en el directorio oficial por desactualización, o el dato de")
    lineas.append("OSM puede estar viejo o mal cargado. Es una lista para revisar, no una conclusión.")

    reporte = "\n".join(lineas)
    print(reporte)
    REPORTE_PATH.write_text(reporte, encoding="utf-8")
    print(f"\n(Comparación completa en {SALIDA_PATH})")
    print(f"(Reporte también guardado en {REPORTE_PATH})")


if __name__ == "__main__":
    main()
