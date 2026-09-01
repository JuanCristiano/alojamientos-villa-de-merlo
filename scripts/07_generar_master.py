"""
07_generar_master.py

Último paso: arma el dataset consolidado final, combinando:
  - Las 62 fichas del directorio oficial (limpias, con su estado de coincidencia
    en OSM ya verificado a mano en los casos límite).
  - Los 134 candidatos que aparecen SOLO en OpenStreetMap, marcados con
    claridad como "no confirmados" — nunca se presentan como si fueran
    parte del directorio oficial.

No se fusiona ni se descarta nada de los datos originales: cada fila indica
de dónde salió (columna 'fuente') y qué tan confirmada está (columna
'estado_confirmacion'). Los posibles duplicados detectados dentro del propio
oficial (03_limpiar_y_normalizar.py) se conservan tal cual, sin resolver
automáticamente.

Atribución obligatoria (por la licencia ODbL de OpenStreetMap), en cualquier
lugar donde se muestre o publique este dataset:
  "Datos de alojamientos no oficiales: © colaboradores de OpenStreetMap,
   licencia ODbL. https://www.openstreetmap.org/copyright"

Uso:
    python scripts/07_generar_master.py
"""

from pathlib import Path

import pandas as pd

OFICIAL_PATH = Path(__file__).resolve().parent.parent / "data" / "processed" / "alojamientos_oficial_clean.csv"
OSM_PATH = Path(__file__).resolve().parent.parent / "data" / "raw" / "alojamientos_osm_raw.csv"
COMPARACION_PATH = Path(__file__).resolve().parent.parent / "data" / "processed" / "comparacion_fuentes.csv"
SALIDA_PATH = Path(__file__).resolve().parent.parent / "data" / "processed" / "alojamientos_master_clean.csv"
REPORTE_PATH = Path(__file__).resolve().parent.parent / "data" / "processed" / "reporte_master.txt"


def main():
    faltantes = [p for p in (OFICIAL_PATH, OSM_PATH, COMPARACION_PATH) if not p.exists()]
    if faltantes:
        print("Faltan archivos previos, corré antes:")
        for p in faltantes:
            print(f"  - {p.name}")
        return

    oficial = pd.read_csv(OFICIAL_PATH, dtype=str, keep_default_na=False)
    osm = pd.read_csv(OSM_PATH, dtype=str, keep_default_na=False)
    comparacion = pd.read_csv(COMPARACION_PATH, dtype=str, keep_default_na=False)

    osm = osm[osm["nombre_publicado"].str.strip() != ""].reset_index(drop=True)
    osm_unico = osm.drop_duplicates(subset="nombre_publicado").set_index("nombre_publicado")

    # --- Bloque 1: las 62 del oficial, enriquecidas con lat/lon si coinciden con OSM ---
    comparacion_oficial = comparacion[comparacion["en_oficial"] == "si"].set_index("nombre")

    filas_oficial = []
    for _, fila in oficial.iterrows():
        info_cruce = comparacion_oficial.loc[fila["nombre"]] if fila["nombre"] in comparacion_oficial.index else None
        coincide_osm = info_cruce is not None and info_cruce["en_osm"] == "si"

        lat, lon, nombre_osm_relacionado = "", "", ""
        if coincide_osm:
            nombre_osm_relacionado = info_cruce["mejor_candidato_osm"]
            if nombre_osm_relacionado in osm_unico.index:
                lat = osm_unico.loc[nombre_osm_relacionado, "latitud"]
                lon = osm_unico.loc[nombre_osm_relacionado, "longitud"]

        estado = "Confirmado en directorio oficial"
        if coincide_osm:
            estado += " y coincide con OpenStreetMap"

        filas_oficial.append({
            "nombre": fila["nombre"],
            "categoria": fila["categoria"],
            "direccion": fila["direccion"],
            "telefonos": fila["telefonos"],
            "telefonos_notas": fila["telefonos_notas"],
            "email": fila["email"],
            "instagram": fila["instagram"],
            "web": fila["web"],
            "etiquetas": fila["etiquetas"],
            "latitud": lat,
            "longitud": lon,
            "fuente": "oficial+osm" if coincide_osm else "oficial",
            "estado_confirmacion": estado,
            "nombre_relacionado_osm": nombre_osm_relacionado,
            "posible_duplicado": fila["posible_duplicado"],
            "url_origen": fila["url_origen"],
            "fecha_extraccion": fila["fecha_extraccion"],
        })

    # --- Bloque 2: candidatos que están SOLO en OSM (nunca confirmados) ---
    comparacion_solo_osm = comparacion[(comparacion["en_oficial"] == "no") & (comparacion["en_osm"] == "si")]

    filas_osm = []
    for _, fila in comparacion_solo_osm.iterrows():
        nombre = fila["nombre"]
        if nombre not in osm_unico.index:
            continue
        datos_osm = osm_unico.loc[nombre]
        filas_osm.append({
            "nombre": nombre,
            "categoria": datos_osm["categoria_publicada"],
            "direccion": datos_osm["direccion_raw"],
            "telefonos": datos_osm["telefonos_raw"],
            "telefonos_notas": "",
            "email": datos_osm["email_raw"],
            "instagram": datos_osm["instagram_raw"],
            "web": datos_osm["web_raw"],
            "etiquetas": datos_osm["etiquetas_raw"],
            "latitud": datos_osm["latitud"],
            "longitud": datos_osm["longitud"],
            "fuente": "solo_openstreetmap",
            "estado_confirmacion": "Candidato no confirmado (aparece solo en OpenStreetMap)",
            "nombre_relacionado_osm": "",
            "posible_duplicado": "",
            "url_origen": datos_osm["url_origen"],
            "fecha_extraccion": datos_osm["fecha_extraccion"],
        })

    df_master = pd.concat([pd.DataFrame(filas_oficial), pd.DataFrame(filas_osm)], ignore_index=True)
    SALIDA_PATH.parent.mkdir(parents=True, exist_ok=True)
    df_master.to_csv(SALIDA_PATH, index=False, encoding="utf-8")

    # --- Reporte resumen ---
    conteo_estado = df_master["estado_confirmacion"].value_counts()
    lineas = []
    lineas.append("Reporte del dataset maestro — alojamientos_master_clean.csv")
    lineas.append(f"Total de filas: {len(df_master)}")
    lineas.append("")
    lineas.append("== Por estado de confirmación ==")
    for estado, cant in conteo_estado.items():
        lineas.append(f"  {cant:3d}  {estado}")
    lineas.append("")
    lineas.append("RECORDATORIO para cualquier presentación de este dataset:")
    lineas.append("  - 'Candidato no confirmado' NO significa 'no habilitado'. Solo significa")
    lineas.append("    que no está en el directorio oficial de la Secretaría de Turismo.")
    lineas.append("  - Los datos de OpenStreetMap requieren atribución obligatoria:")
    lineas.append('    "Datos © colaboradores de OpenStreetMap, licencia ODbL"')
    lineas.append("    https://www.openstreetmap.org/copyright")
    lineas.append("  - Las filas con 'posible_duplicado' no vacío requieren revisión manual,")
    lineas.append("    no fueron fusionadas automáticamente.")

    reporte = "\n".join(lineas)
    print(reporte)
    REPORTE_PATH.write_text(reporte, encoding="utf-8")
    print(f"\nDataset maestro guardado en {SALIDA_PATH}")
    print(f"Reporte guardado en {REPORTE_PATH}")


if __name__ == "__main__":
    main()
