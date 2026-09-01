"""
05_diagnostico_osm.py

Diagnóstico rápido de data/raw/alojamientos_osm_raw.csv, antes de cruzarlo
con el directorio oficial. Solo lee, no modifica nada.

Objetivo puntual: entender si los 189 elementos son 189 negocios distintos,
o si hay ruido típico de OSM (unidades sueltas de un mismo complejo,
elementos sin nombre, etc.) que conviene filtrar antes de cruzar fuentes.

Uso:
    python scripts/05_diagnostico_osm.py
"""

from pathlib import Path

import pandas as pd

RAW_PATH = Path(__file__).resolve().parent.parent / "data" / "raw" / "alojamientos_osm_raw.csv"
REPORTE_PATH = Path(__file__).resolve().parent.parent / "data" / "processed" / "reporte_diagnostico_osm.txt"


def main():
    if not RAW_PATH.exists():
        print(f"No encuentro {RAW_PATH}. ¿Corriste 04_extraer_osm.py?")
        return

    df = pd.read_csv(RAW_PATH, dtype=str, keep_default_na=False)
    lineas = []

    lineas.append(f"Reporte de diagnóstico — data/raw/alojamientos_osm_raw.csv")
    lineas.append(f"Total de elementos: {len(df)}")
    lineas.append("")

    lineas.append("== 1. Elementos por tipo (tag 'tourism' de OSM) ==")
    conteo_tipo = df["categoria_publicada"].replace("", "(sin tipo)").value_counts()
    for tipo, cant in conteo_tipo.items():
        lineas.append(f"  {tipo:20s}: {cant}")
    lineas.append("")

    sin_nombre = df[df["nombre_publicado"].str.strip() == ""]
    lineas.append(f"== 2. Elementos sin nombre cargado: {len(sin_nombre)} ==")
    for _, fila in sin_nombre.iterrows():
        lineas.append(f"  tipo={fila['categoria_publicada']:15s} osm_id={fila['osm_id']}  {fila['url_origen']}")
    lineas.append("")

    con_nombre = df[df["nombre_publicado"].str.strip() != ""]
    nombres_repetidos = con_nombre["nombre_publicado"].value_counts()
    nombres_repetidos = nombres_repetidos[nombres_repetidos > 1]
    lineas.append(f"== 3. Nombres que se repiten exactamente ({len(nombres_repetidos)} nombres) ==")
    lineas.append("  (posible señal de unidades sueltas de un mismo complejo cargadas por separado)")
    for nombre, cant in nombres_repetidos.items():
        lineas.append(f"  '{nombre}': aparece {cant} veces")
    lineas.append("")

    lineas.append("== 4. Campos vacíos (sobre el total) ==")
    total = len(df)
    for col in ["direccion_raw", "telefonos_raw", "email_raw", "web_raw"]:
        vacios = (df[col].str.strip() == "").sum()
        pct = (vacios / total * 100) if total else 0
        lineas.append(f"  {col:15s}: {vacios:3d} / {total} vacíos ({pct:.0f}%)")
    lineas.append("")

    nombres_unicos = con_nombre["nombre_publicado"].nunique()
    lineas.append(f"== 5. Resumen ==")
    lineas.append(f"  Elementos totales:        {len(df)}")
    lineas.append(f"  Con nombre:                {len(con_nombre)}")
    lineas.append(f"  Nombres ÚNICOS con nombre: {nombres_unicos}")
    lineas.append("  (esta última cifra es la que de verdad importa para comparar contra las 62 oficiales)")

    reporte = "\n".join(lineas)
    print(reporte)

    REPORTE_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORTE_PATH.write_text(reporte, encoding="utf-8")
    print(f"\n(Reporte también guardado en {REPORTE_PATH})")


if __name__ == "__main__":
    main()
