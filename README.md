# Alojamientos Villa de Merlo

Proyecto de portfolio: scraping, diagnóstico, limpieza y cruce de fuentes
para consolidar un dataset de alojamientos turísticos de Villa de Merlo,
San Luis, Argentina.

## Objetivo

Convertir el directorio oficial (publicado como páginas web individuales,
sin descarga en CSV) en un dataset limpio y trazable, y compararlo contra
una fuente abierta independiente (OpenStreetMap) para medir qué tan
completo está el directorio público — documentando cada paso para que el
proceso sea auditable de punta a punta.

## Reglas de oro

- **Los CSV crudos nunca se modifican.** `data/raw/*.csv` son capturas
  fieles de cada fuente en su fecha de extracción. Toda limpieza o
  corrección vive en scripts separados que generan archivos nuevos, con
  su propio reporte de qué cambió y por qué.
- **Nunca se fusionan ni se borran fichas automáticamente por parecerse.**
  Los posibles duplicados —dentro de una misma fuente o entre fuentes— se
  **marcan** para revisión manual, nunca se resuelven solos.
- **"No aparece en el oficial" no es "no habilitado".** Un alojamiento que
  solo aparece en OpenStreetMap puede faltar en el directorio oficial por
  desactualización, o el dato de OSM puede estar viejo o mal cargado. El
  dataset lo señala como candidato a revisar, nunca como conclusión.

## Fuentes

| Fuente | Qué es | Cobertura obtenida |
|---|---|---|
| Directorio oficial | Secretaría de Turismo de Villa de Merlo, https://villademerlo.tur.ar/alojamientos/ | 62 fichas (5 páginas, sin descarga directa) |
| OpenStreetMap | Mapa colaborativo abierto, vía Overpass API (gratuita, sin API key) | 189 elementos (176 nombres únicos) dentro del área de Villa de Merlo |

Se descartó Google Places API (requiere alta de tarjeta de crédito) y
Merlo 360 (contenido con patrones de texto genérico/auto-generado, poco
confiable como fuente de datos reales).

**Atribución obligatoria** por la licencia ODbL de OpenStreetMap, en
cualquier lugar donde se muestre o publique este dataset:
> Datos de alojamientos no oficiales: © colaboradores de OpenStreetMap,
> licencia ODbL. https://www.openstreetmap.org/copyright

## Estructura del proyecto

```
merlo-alojamientos/
├─ data/
│  ├─ raw/            # Capturas crudas de cada fuente, nunca se editan a mano
│  └─ processed/       # Salidas limpias, comparaciones y reportes de cada paso
├─ scripts/
│  ├─ 01_extraer_directorio.py     # Scrapea el directorio oficial -> CSV crudo
│  ├─ 02_diagnostico.py            # Analiza el CSV oficial crudo, no lo modifica
│  ├─ 03_limpiar_y_normalizar.py   # Limpia el oficial + reporte antes/después
│  ├─ 04_extraer_osm.py            # Baja alojamientos de OpenStreetMap (Overpass API)
│  ├─ 05_diagnostico_osm.py        # Analiza el CSV de OSM crudo, no lo modifica
│  ├─ 06_cruzar_fuentes.py         # Compara oficial vs OSM por nombre
│  └─ 07_generar_master.py         # Arma el dataset consolidado final
└─ README.md
```

## Requisitos

```bash
pip install requests beautifulsoup4 pandas lxml
```

## Cómo correr el proyecto (en orden)

```bash
# 1. Extraer las fichas del directorio oficial (crudo, sin corregir nada)
python scripts/01_extraer_directorio.py
# -> data/raw/alojamientos_merlo_raw.csv

# 2. Diagnóstico del oficial: medir qué tan sucios están los datos reales
python scripts/02_diagnostico.py
# -> data/processed/reporte_diagnostico.txt

# 3. Limpieza y normalización del oficial
python scripts/03_limpiar_y_normalizar.py
# -> data/processed/alojamientos_oficial_clean.csv
# -> data/processed/reporte_limpieza.txt

# 4. Extraer alojamientos de OpenStreetMap (segunda fuente)
python scripts/04_extraer_osm.py
# -> data/raw/alojamientos_osm_raw.csv

# 5. Diagnóstico rápido de OSM
python scripts/05_diagnostico_osm.py
# -> data/processed/reporte_diagnostico_osm.txt

# 6. Cruzar oficial vs OSM por similitud de nombre
python scripts/06_cruzar_fuentes.py
# -> data/processed/comparacion_fuentes.csv
# -> data/processed/reporte_cruce_fuentes.txt

# 7. Consolidar el dataset final
python scripts/07_generar_master.py
# -> data/processed/alojamientos_master_clean.csv
# -> data/processed/reporte_master.txt
```

## Resultados del cruce de fuentes

De las 62 fichas oficiales, **35 coinciden con un registro en OpenStreetMap**
y 27 no tienen contraparte reconocible. Por el otro lado, OpenStreetMap
aporta **134 candidatos** que no están en el directorio oficial.

El primer intento de cruce (comparando nombres completos letra por letra)
solo encontraba 15 coincidencias, porque OSM casi siempre antepone el tipo
de alojamiento al nombre ("Cabañas Nona Olga" vs "Nona Olga" en el
oficial). Se corrigió comparando el núcleo del nombre (sin palabras de
rubro) más una métrica de superposición de palabras, lo que subió las
coincidencias reales de 15 a 35. Los 7 casos límite que quedaron cerca del
umbral se revisaron a mano uno por uno: ninguno resultó ser un duplicado
real.

| Estado en el dataset maestro | Filas |
|---|---|
| Confirmado en directorio oficial y coincide con OpenStreetMap | 35 |
| Confirmado en directorio oficial (OSM no lo tiene cargado) | 27 |
| Candidato no confirmado (aparece solo en OpenStreetMap) | 134 |
| **Total** | **196** |

## Diccionario de columnas — `alojamientos_master_clean.csv`

| Columna              | Descripción                                                              |
|-----------------------|---------------------------------------------------------------------------|
| nombre                | Nombre comercial publicado                                                |
| categoria             | Categoría publicada (Cabañas, Hotel, Vatt, etc. — o el tag `tourism` de OSM) |
| direccion             | Dirección tal como está publicada en la fuente                            |
| telefonos             | Uno o más números, separados por ` \| `, solo dígitos                     |
| telefonos_notas       | Aclaraciones que venían junto al teléfono (ej. nombre de contacto)        |
| email                 | Uno o más emails válidos, en minúsculas, separados por ` \| `              |
| instagram             | Handle de Instagram con `@`                                               |
| web                   | URL del sitio propio                                                      |
| etiquetas             | Etiquetas/amenidades (ej. Pileta, Accesible), unificadas                  |
| latitud / longitud    | Coordenadas (solo cuando el dato viene de OSM o coincide con OSM)         |
| fuente                | `oficial`, `oficial+osm` o `solo_openstreetmap`                           |
| estado_confirmacion   | Texto explícito del nivel de confirmación de esa fila                     |
| nombre_relacionado_osm| Nombre con el que coincidió en OSM, si aplica                             |
| posible_duplicado     | Sospecha de duplicado interno (sin fusionar) detectada en la limpieza     |
| url_origen            | Ficha original (villademerlo.tur.ar) o link al elemento en OSM            |
| fecha_extraccion      | Fecha en que se capturó el dato crudo                                     |

## Qué falta (próximos pasos)

- Revisar a mano los casos marcados en `posible_duplicado` dentro del oficial
  (Ecos de las Sierras/Posada de las Sierras, Nona Olga/Nona Olga II,
  Complejo Calas/Complejo Entre Marte y la Luna).
- Armar un informe breve (una página) para presentar el hallazgo a la
  Secretaría de Turismo de Villa de Merlo, encuadrado como propuesta de
  mejora de calidad de datos del directorio público — no como fiscalización
  de negocios.
- Subir el proyecto a GitHub con este README como documentación principal.
