"""
01_extraer_directorio.py

Paso 1 del proyecto "Alojamientos Villa de Merlo".
Objetivo único de este script: bajar las fichas del directorio oficial
TAL COUAL están publicadas, sin limpiar ni corregir nada todavía.

Regla de oro: este script NUNCA debe "arreglar" un dato. Si un teléfono
viene mal escrito o un email tiene mayúsculas raras, eso se guarda así,
crudo, en data/raw/alojamientos_merlo_raw.csv. La limpieza es
responsabilidad exclusiva de 02_limpiar_y_normalizar.py.

Uso:
    python scripts/01_extraer_directorio.py
"""

import csv
import datetime as dt
import re
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://villademerlo.tur.ar/alojamientos/"
DETAIL_URL_RE = re.compile(r"^https://villademerlo\.tur\.ar/alojamiento/[^/]+/$")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; MerloAlojamientosBot/1.0; "
        "proyecto de portfolio, uso educativo)"
    )
}

# El sitio no usa una estructura consistente: a veces cada dato (teléfono,
# instagram, email, web) va en su propio <li>, y a veces vienen todos pegados
# en un único bloque de texto. Por eso no buscamos "el <li> que arranca con
# Instagram:", sino que ubicamos la POSICIÓN de cada rótulo dentro del bloque
# completo y cortamos el texto entre rótulo y rótulo. Esto funciona sea cual
# sea la estructura HTML de origen.
DIRECCION_LABEL_RE = re.compile(r"^Direcci[oó]n\s*:", re.IGNORECASE)

INFO_LABEL_RE = re.compile(
    r"(?P<telefono>Cel\.?|Celular|Tel(?:é|e)fono\.?|Tel\.?|Whatsapp|Contacto)\s*:"
    r"|(?P<instagram>Instagram)\s*:"
    r"|(?P<email>Correo(?:\s*electr[oó]nico)?)\s*:"
    r"|(?P<web>P[aá]gina(?:\s*web)?)\s*:",
    re.IGNORECASE,
)

# Links que NO cuentan como "la web propia" del alojamiento (son de contacto,
# no del sitio del negocio).
NO_ES_WEB_PROPIA = ("wa.me", "instagram.com", "mailto:", "tel:", "facebook.com")

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "data" / "raw" / "alojamientos_merlo_raw.csv"

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
]


class PaginaInexistente(Exception):
    """Se lanza cuando una página de listado no existe (404): significa que ya no hay más páginas."""


def get_soup(url: str) -> BeautifulSoup:
    """Descarga una URL y devuelve el HTML parseado. Reintenta una vez si falla."""
    for intento in range(2):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
            if resp.status_code == 404:
                raise PaginaInexistente(url)
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "lxml")
        except PaginaInexistente:
            raise
        except requests.RequestException as e:
            if intento == 1:
                raise
            print(f"  aviso: falló {url} ({e}), reintentando...")
            time.sleep(2)


def get_listing_urls() -> list[str]:
    """Recorre las páginas del listado (1 a N) y junta todas las URLs de ficha, sin duplicar."""
    urls: list[str] = []
    vistos = set()
    page = 1

    while True:
        page_url = BASE_URL if page == 1 else urljoin(BASE_URL, f"page/{page}/")
        print(f"Listado página {page}: {page_url}")
        try:
            soup = get_soup(page_url)
        except PaginaInexistente:
            print(f"  página {page} no existe (404): fin del listado.")
            break

        encontrados_en_pagina = 0
        for a in soup.find_all("a", href=True):
            href = a["href"].split("?")[0]
            if DETAIL_URL_RE.match(href) and href not in vistos:
                vistos.add(href)
                urls.append(href)
                encontrados_en_pagina += 1

        # Si la página no trajo ninguna ficha nueva, asumimos que ya no hay más páginas.
        if encontrados_en_pagina == 0:
            break

        page += 1
        time.sleep(1)  # ser respetuosos con el servidor

    return urls


def parse_campos_desde_bloque(bloque: str) -> dict:
    """Dado un bloque de texto tipo 'Calle 123 Cel.: 555 Instagram: @x Correo: a@b.com',
    separa cada campo usando la POSICIÓN de sus rótulos dentro del texto. No asume que
    cada dato venga en su propio <li>: funciona igual si todo vino pegado en una sola línea."""
    matches = list(INFO_LABEL_RE.finditer(bloque))
    direccion = bloque[: matches[0].start()].strip() if matches else bloque.strip()

    valores = {"telefono": [], "instagram": [], "email": [], "web": []}
    for i, m in enumerate(matches):
        campo = m.lastgroup
        inicio = m.end()
        fin = matches[i + 1].start() if i + 1 < len(matches) else len(bloque)
        valor = bloque[inicio:fin].strip(" :|")
        if valor:
            valores[campo].append(valor)

    return {
        "direccion_raw": direccion,
        "telefonos_raw": " | ".join(dict.fromkeys(valores["telefono"])),
        "instagram_raw": " | ".join(dict.fromkeys(valores["instagram"])),
        "email_raw": " | ".join(dict.fromkeys(valores["email"])),
        "web_raw": " | ".join(dict.fromkeys(valores["web"])),
    }


def parse_detail(url: str) -> dict:
    """Extrae los campos de una ficha individual, sin normalizar nada."""
    soup = get_soup(url)

    nombre = soup.find("h1")
    nombre_publicado = nombre.get_text(strip=True) if nombre else ""

    contenedor = soup.find("div", class_=re.compile("entry-summary|product-summary|summary")) or soup

    # El sitio a veces repite el mismo bloque de info en más de un <li>
    # (uno completo y otro corto, solo con la dirección). Nos quedamos con
    # el <li> que arranca con "Dirección:" y tiene MÁS texto, porque ese
    # es el que trae todos los campos.
    candidatos = [
        li for li in contenedor.find_all("li")
        if DIRECCION_LABEL_RE.match(li.get_text(" ", strip=True))
    ]

    if candidatos:
        li_info = max(candidatos, key=lambda li: len(li.get_text(strip=True)))
        bloque_completo = DIRECCION_LABEL_RE.sub("", li_info.get_text(" ", strip=True), count=1).strip()
    else:
        li_info = None
        bloque_completo = ""

    campos = parse_campos_desde_bloque(bloque_completo)

    # Si dentro de ese <li> hay un link que no es de whatsapp/instagram/mail/tel,
    # es la web propia del alojamiento: la usamos en vez del texto plano,
    # porque suele venir mejor formada (con protocolo, sin typos de mayúsculas raras).
    if li_info is not None:
        for a in li_info.find_all("a", href=True):
            href = a["href"]
            if not any(dominio in href for dominio in NO_ES_WEB_PROPIA):
                campos["web_raw"] = href
                break

    # Categoría y etiquetas: WooCommerce las expone como links a
    # /categoria-producto/... y /etiqueta-producto/...
    categoria_links = soup.find_all("a", href=re.compile(r"/categoria-producto/"))
    categoria_publicada = categoria_links[0].get_text(strip=True) if categoria_links else ""

    etiqueta_links = soup.find_all("a", href=re.compile(r"/etiqueta-producto/"))
    etiquetas_raw = " | ".join(dict.fromkeys(a.get_text(strip=True) for a in etiqueta_links))

    return {
        "nombre_publicado": nombre_publicado,
        "categoria_publicada": categoria_publicada,
        "direccion_raw": campos["direccion_raw"],
        "telefonos_raw": campos["telefonos_raw"],
        "email_raw": campos["email_raw"],
        "instagram_raw": campos["instagram_raw"],
        "web_raw": campos["web_raw"],
        "etiquetas_raw": etiquetas_raw,
        "url_origen": url,
        "fecha_extraccion": dt.date.today().isoformat(),
        "fuente": "oficial_villademerlo",
    }


def main():
    print("Paso 1: relevando URLs de fichas desde el listado oficial...")
    urls = get_listing_urls()
    print(f"Se encontraron {len(urls)} fichas únicas.\n")

    filas = []
    for i, url in enumerate(urls, start=1):
        print(f"[{i}/{len(urls)}] {url}")
        try:
            filas.append(parse_detail(url))
        except Exception as e:
            print(f"  ERROR extrayendo {url}: {e}")
        time.sleep(1)  # pausa entre fichas para no sobrecargar el sitio

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(filas)

    print(f"\nListo. {len(filas)} fichas guardadas en {OUTPUT_PATH}")
    print("Verificación pendiente: confirmar que sean 62 filas y que ninguna")
    print("quedó con url_origen vacía antes de pasar a la limpieza.")


if __name__ == "__main__":
    main()
