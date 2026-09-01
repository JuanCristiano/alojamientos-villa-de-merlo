"""
02_diagnostico.py

Paso 2 del proyecto "Alojamientos Villa de Merlo".
Este script SOLO LEE data/raw/alojamientos_merlo_raw.csv y genera un reporte.
No modifica el CSV original ni escribe ningún dato "corregido" todavía.
El objetivo es entender qué tan sucios están los datos reales antes de
escribir las reglas de limpieza en 03_limpiar_y_normalizar.py.

Uso:
    python scripts/02_diagnostico.py

Salida:
    - Imprime el resumen en pantalla
    - Guarda el mismo resumen en data/processed/reporte_diagnostico.txt
"""

import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd

RAW_PATH = Path(__file__).resolve().parent.parent / "data" / "raw" / "alojamientos_merlo_raw.csv"
REPORTE_PATH = Path(__file__).resolve().parent.parent / "data" / "processed" / "reporte_diagnostico.txt"

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Umbral de similitud de nombre para marcar dos fichas como "posible duplicado".
# 0.85 es exigente a propósito: mejor que se nos escape algún duplicado real
# a que marquemos como duplicados dos alojamientos distintos.
UMBRAL_SIMILITUD_NOMBRE = 0.85


def normalizar_para_comparar(texto: str) -> str:
    """Minúsculas y sin tildes, solo para COMPARAR nombres/direcciones entre sí.
    Esto no toca el dato original en ningún CSV, es únicamente para detectar duplicados."""
    if not isinstance(texto, str):
        return ""
    texto = texto.lower().strip()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"\s+", " ", texto)
    return texto


def seccion_vacios(df: pd.DataFrame, lineas: list[str]) -> None:
    lineas.append("== 1. Campos vacíos por columna ==")
    total = len(df)
    for col in df.columns:
        if col in ("url_origen", "fecha_extraccion"):
            continue
        vacios = (df[col].isna() | (df[col].astype(str).str.strip() == "")).sum()
        pct = (vacios / total * 100) if total else 0
        lineas.append(f"  {col:22s}: {vacios:3d} / {total} vacíos ({pct:.0f}%)")
    lineas.append("")


def seccion_categorias(df: pd.DataFrame, lineas: list[str]) -> None:
    lineas.append("== 2. Categorías publicadas (valores únicos y conteo) ==")
    conteo = df["categoria_publicada"].fillna("(vacío)").value_counts()
    for valor, cant in conteo.items():
        lineas.append(f"  {valor:20s}: {cant}")
    lineas.append("")

    lineas.append("== 3. Etiquetas publicadas (valores únicos, separadas por ' | ') ==")
    todas = []
    for val in df["etiquetas_raw"].dropna():
        todas.extend(t.strip() for t in val.split("|") if t.strip())
    conteo_etq = pd.Series(todas).value_counts() if todas else pd.Series(dtype=int)
    for valor, cant in conteo_etq.items():
        lineas.append(f"  {valor:20s}: {cant}")
    lineas.append("")


def seccion_telefonos(df: pd.DataFrame, lineas: list[str]) -> None:
    lineas.append("== 4. Formatos de teléfono encontrados ==")
    formatos = {}
    total_numeros = 0
    numeros_sospechosos = []

    for _, fila in df.iterrows():
        crudo = fila.get("telefonos_raw", "")
        if not isinstance(crudo, str) or not crudo.strip():
            continue
        for numero in crudo.split("|"):
            numero = numero.strip()
            if not numero:
                continue
            total_numeros += 1
            solo_digitos = re.sub(r"\D", "", numero)
            forma = "con espacios/símbolos" if numero != solo_digitos else "solo dígitos"
            clave = f"{forma}, {len(solo_digitos)} dígitos"
            formatos[clave] = formatos.get(clave, 0) + 1
            # Un celular argentino con característica suele tener 10 u 11 dígitos.
            # Marcamos como sospechoso lo que se aleja mucho de ese rango.
            if len(solo_digitos) < 8 or len(solo_digitos) > 13:
                numeros_sospechosos.append((fila["nombre_publicado"], numero))

    lineas.append(f"  Total de números encontrados: {total_numeros}")
    for forma, cant in sorted(formatos.items(), key=lambda x: -x[1]):
        lineas.append(f"    {forma:35s}: {cant}")

    if numeros_sospechosos:
        lineas.append("  Números con cantidad de dígitos rara (revisar a mano):")
        for nombre, numero in numeros_sospechosos:
            lineas.append(f"    {nombre}: '{numero}'")
    lineas.append("")


def seccion_emails(df: pd.DataFrame, lineas: list[str]) -> None:
    lineas.append("== 5. Emails con formato inválido ==")
    invalidos = []
    con_mayusculas = []

    for _, fila in df.iterrows():
        crudo = fila.get("email_raw", "")
        if not isinstance(crudo, str) or not crudo.strip():
            continue
        for email in crudo.split("|"):
            email = email.strip()
            if not email:
                continue
            if not EMAIL_RE.match(email):
                invalidos.append((fila["nombre_publicado"], email))
            elif email != email.lower():
                con_mayusculas.append((fila["nombre_publicado"], email))

    if invalidos:
        for nombre, email in invalidos:
            lineas.append(f"  INVÁLIDO -> {nombre}: '{email}'")
    else:
        lineas.append("  Ninguno con formato claramente inválido.")

    lineas.append(f"  Emails con mayúsculas (candidatos a normalizar a minúsculas): {len(con_mayusculas)}")
    for nombre, email in con_mayusculas:
        lineas.append(f"    {nombre}: '{email}'")
    lineas.append("")


def seccion_duplicados(df: pd.DataFrame, lineas: list[str]) -> None:
    lineas.append("== 6. Posibles duplicados dentro del propio directorio oficial ==")
    lineas.append(f"  (comparando nombres normalizados, umbral de similitud >= {UMBRAL_SIMILITUD_NOMBRE})")

    nombres_norm = df["nombre_publicado"].fillna("").map(normalizar_para_comparar)
    encontrados = []

    for i in range(len(df)):
        for j in range(i + 1, len(df)):
            ratio = SequenceMatcher(None, nombres_norm.iloc[i], nombres_norm.iloc[j]).ratio()
            if ratio >= UMBRAL_SIMILITUD_NOMBRE:
                encontrados.append((df["nombre_publicado"].iloc[i], df["nombre_publicado"].iloc[j], ratio))

    if encontrados:
        for a, b, ratio in encontrados:
            lineas.append(f"  '{a}'  ~=  '{b}'   (similitud {ratio:.2f})")
    else:
        lineas.append("  No se encontraron pares de nombres sospechosamente parecidos.")

    # También chequeamos direcciones idénticas con nombres distintos:
    # eso puede indicar dos fichas del mismo predio (ej. una vieja sin dar de baja).
    direcciones_norm = df["direccion_raw"].fillna("").map(normalizar_para_comparar)
    direcciones_no_vacias = direcciones_norm[direcciones_norm != ""]
    repetidas = direcciones_no_vacias[direcciones_no_vacias.duplicated(keep=False)]

    lineas.append("")
    lineas.append("  Direcciones idénticas compartidas por más de una ficha:")
    if repetidas.empty:
        lineas.append("  Ninguna.")
    else:
        for direccion in repetidas.unique():
            nombres = df.loc[direcciones_norm == direccion, "nombre_publicado"].tolist()
            lineas.append(f"    '{direccion}' -> {nombres}")
    lineas.append("")


def main():
    if not RAW_PATH.exists():
        print(f"No encuentro {RAW_PATH}. ¿Corriste primero 01_extraer_directorio.py?")
        return

    df = pd.read_csv(RAW_PATH, dtype=str, keep_default_na=False)

    lineas = []
    lineas.append(f"Reporte de diagnóstico — data/raw/alojamientos_merlo_raw.csv")
    lineas.append(f"Total de fichas cargadas: {len(df)} (esperado: 62)")
    lineas.append("")

    seccion_vacios(df, lineas)
    seccion_categorias(df, lineas)
    seccion_telefonos(df, lineas)
    seccion_emails(df, lineas)
    seccion_duplicados(df, lineas)

    reporte = "\n".join(lineas)
    print(reporte)

    REPORTE_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORTE_PATH.write_text(reporte, encoding="utf-8")
    print(f"\n(Reporte también guardado en {REPORTE_PATH})")


if __name__ == "__main__":
    main()