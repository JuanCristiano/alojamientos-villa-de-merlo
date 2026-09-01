"""
03_limpiar_y_normalizar.py

Paso 3 del proyecto "Alojamientos Villa de Merlo".
Lee data/raw/alojamientos_merlo_raw.csv (que NUNCA se modifica) y genera:
  - data/processed/alojamientos_oficial_clean.csv   (dataset limpio)
  - data/processed/reporte_limpieza.txt             (qué cambió y por qué)

Reglas de limpieza, basadas en el diagnóstico real (02_diagnostico.py):
  - Teléfonos: a veces vienen dos números pegados en un mismo campo,
    separados por distintos símbolos ('//', '/', o incluso con un segundo
    rótulo tipo "Telefono fijo:" adentro). En vez de partir por un símbolo
    fijo, se extrae cada corrida de dígitos por separado.
  - Nombres entre paréntesis junto a un teléfono (ej. "(Evelyn)") se
    guardan en una columna aparte, no se descartan.
  - Emails: se corrige el typo "gmail. com" -> "gmail.com", se recorta
    texto que quedó pegado después del email real, y se pasa a minúsculas.
  - Etiquetas: "Accesibilidad" se unifica con "Accesible" (mismo concepto).
  - Duplicados: NUNCA se fusionan ni se borran automáticamente. Solo se
    listan en el reporte para revisión manual.

Uso:
    python scripts/03_limpiar_y_normalizar.py
"""

import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd

RAW_PATH = Path(__file__).resolve().parent.parent / "data" / "raw" / "alojamientos_merlo_raw.csv"
CLEAN_PATH = Path(__file__).resolve().parent.parent / "data" / "processed" / "alojamientos_oficial_clean.csv"
REPORTE_PATH = Path(__file__).resolve().parent.parent / "data" / "processed" / "reporte_limpieza.txt"

UMBRAL_SIMILITUD_NOMBRE = 0.85

# Mapeo de etiquetas equivalentes -> forma canónica.
ETIQUETAS_CANONICAS = {
    "accesibilidad": "Accesible",
    "accesible": "Accesible",
}

PHONE_NUM_RE = re.compile(r"(\+?\d[\d\s\-]{6,}\d)")
PAREN_RE = re.compile(r"\(([^)]+)\)")
EMAIL_EXTRACT_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


def normalizar_para_comparar(texto: str) -> str:
    if not isinstance(texto, str):
        return ""
    texto = texto.lower().strip()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto)


def limpiar_telefonos(crudo: str) -> tuple[str, str]:
    """Devuelve (telefonos_limpios, notas). No asume un separador fijo entre
    números: extrae cada corrida de dígitos como un número independiente,
    sin importar si el original los separaba con '//', '/', un rótulo
    repetido, o nada. Los nombres entre paréntesis se guardan como nota."""
    if not crudo or not crudo.strip():
        return "", ""

    notas = [n.strip() for n in PAREN_RE.findall(crudo) if n.strip()]
    texto_sin_notas = PAREN_RE.sub(" ", crudo)

    numeros = []
    for m in PHONE_NUM_RE.finditer(texto_sin_notas):
        digitos = re.sub(r"\D", "", m.group(1))
        if len(digitos) >= 8:  # descarta ruido corto que no sea un teléfono real
            numeros.append(digitos)

    numeros = list(dict.fromkeys(numeros))  # dedupe, conserva orden
    return " | ".join(numeros), " | ".join(dict.fromkeys(notas))


def limpiar_email(crudo: str) -> str:
    """Corrige el typo 'dominio. com' -> 'dominio.com', descarta texto pegado
    después del email real, y pasa todo a minúsculas."""
    if not crudo or not crudo.strip():
        return ""

    emails = []
    for parte in crudo.split("|"):
        parte = parte.strip()
        if not parte:
            continue
        # typo típico: espacio entre el punto y el TLD ("gmail. com")
        parte = re.sub(r"\.\s+(?=[A-Za-z]{2,4}\b)", ".", parte)
        m = EMAIL_EXTRACT_RE.search(parte)
        if m:
            emails.append(m.group(0).lower())

    return " | ".join(dict.fromkeys(emails))


def limpiar_instagram(crudo: str) -> str:
    if not crudo or not crudo.strip():
        return ""
    handles = []
    for parte in crudo.split("|"):
        parte = parte.strip()
        if not parte:
            continue
        if not parte.startswith("@"):
            parte = "@" + parte
        handles.append(parte)
    return " | ".join(dict.fromkeys(handles))


def limpiar_web(crudo: str) -> str:
    if not crudo or not crudo.strip():
        return ""
    urls = []
    for parte in crudo.split("|"):
        parte = parte.strip()
        if not parte:
            continue
        if not re.match(r"^https?://", parte, re.IGNORECASE):
            parte = "http://" + parte
        urls.append(parte)
    return " | ".join(dict.fromkeys(urls))


def limpiar_etiquetas(crudo: str) -> str:
    if not crudo or not crudo.strip():
        return ""
    etiquetas = []
    for parte in crudo.split("|"):
        parte = parte.strip()
        if not parte:
            continue
        canonica = ETIQUETAS_CANONICAS.get(parte.lower(), parte)
        etiquetas.append(canonica)
    return " | ".join(dict.fromkeys(etiquetas))


def detectar_duplicados(df: pd.DataFrame) -> dict:
    """Devuelve {indice_fila: 'texto explicando la sospecha'} SOLO para reporte.
    Nunca se usa para borrar ni fusionar filas."""
    sospechas: dict[int, list[str]] = {}

    nombres_norm = df["nombre_publicado"].fillna("").map(normalizar_para_comparar)
    for i in range(len(df)):
        for j in range(i + 1, len(df)):
            ratio = SequenceMatcher(None, nombres_norm.iloc[i], nombres_norm.iloc[j]).ratio()
            if ratio >= UMBRAL_SIMILITUD_NOMBRE:
                texto = f"nombre parecido a '{df['nombre_publicado'].iloc[j]}' (similitud {ratio:.2f})"
                sospechas.setdefault(i, []).append(texto)
                texto_inv = f"nombre parecido a '{df['nombre_publicado'].iloc[i]}' (similitud {ratio:.2f})"
                sospechas.setdefault(j, []).append(texto_inv)

    direcciones_norm = df["direccion_raw"].fillna("").map(normalizar_para_comparar)
    for direccion in direcciones_norm[direcciones_norm != ""].unique():
        indices = df.index[direcciones_norm == direccion].tolist()
        if len(indices) > 1:
            nombres = df.loc[indices, "nombre_publicado"].tolist()
            for idx in indices:
                otros = [n for n in nombres if n != df.loc[idx, "nombre_publicado"]]
                texto = f"misma dirección que {otros}"
                sospechas.setdefault(idx, []).append(texto)

    return {idx: " ; ".join(textos) for idx, textos in sospechas.items()}


def main():
    if not RAW_PATH.exists():
        print(f"No encuentro {RAW_PATH}. ¿Corriste 01_extraer_directorio.py?")
        return

    df = pd.read_csv(RAW_PATH, dtype=str, keep_default_na=False)

    cambios = []  # (nombre, campo, antes, despues) solo si cambió algo

    def procesar(campo_origen, campo_destino, funcion):
        resultados = []
        for _, fila in df.iterrows():
            antes = fila.get(campo_origen, "")
            despues = funcion(antes)
            if despues != antes:
                cambios.append((fila["nombre_publicado"], campo_destino, antes, despues))
            resultados.append(despues)
        return resultados

    telefonos_y_notas = df["telefonos_raw"].map(limpiar_telefonos)
    telefonos_limpios = [t for t, _ in telefonos_y_notas]
    telefonos_notas = [n for _, n in telefonos_y_notas]
    for nombre, antes, despues in zip(df["nombre_publicado"], df["telefonos_raw"], telefonos_limpios):
        if despues != antes:
            cambios.append((nombre, "telefonos", antes, despues))

    df_limpio = pd.DataFrame({
        "nombre": df["nombre_publicado"].str.strip(),
        "categoria": df["categoria_publicada"].str.strip(),
        "direccion": df["direccion_raw"].str.strip(),
        "telefonos": telefonos_limpios,
        "telefonos_notas": telefonos_notas,
        "email": procesar("email_raw", "email", limpiar_email),
        "instagram": procesar("instagram_raw", "instagram", limpiar_instagram),
        "web": procesar("web_raw", "web", limpiar_web),
        "etiquetas": procesar("etiquetas_raw", "etiquetas", limpiar_etiquetas),
        "url_origen": df["url_origen"],
        "fecha_extraccion": df["fecha_extraccion"],
    })

    sospechas_duplicados = detectar_duplicados(df)
    df_limpio["posible_duplicado"] = [
        sospechas_duplicados.get(i, "") for i in range(len(df_limpio))
    ]

    CLEAN_PATH.parent.mkdir(parents=True, exist_ok=True)
    df_limpio.to_csv(CLEAN_PATH, index=False, encoding="utf-8")

    # --- Reporte antes/después ---
    lineas = []
    lineas.append(f"Reporte de limpieza — {len(df)} fichas procesadas")
    lineas.append(f"Salida: {CLEAN_PATH}")
    lineas.append("")
    lineas.append(f"== Cambios aplicados por campo ({len(cambios)} en total) ==")
    for nombre, campo, antes, despues in cambios:
        lineas.append(f"  [{campo}] {nombre}")
        lineas.append(f"    antes:   '{antes}'")
        lineas.append(f"    después: '{despues}'")
    lineas.append("")
    lineas.append("== Posibles duplicados (NO fusionados — requieren revisión manual) ==")
    if sospechas_duplicados:
        for idx, texto in sospechas_duplicados.items():
            lineas.append(f"  {df_limpio.loc[idx, 'nombre']}: {texto}")
    else:
        lineas.append("  Ninguno.")

    reporte = "\n".join(lineas)
    print(reporte)
    REPORTE_PATH.write_text(reporte, encoding="utf-8")
    print(f"\n(Reporte también guardado en {REPORTE_PATH})")
    print(f"CSV limpio guardado en {CLEAN_PATH}")


if __name__ == "__main__":
    main()