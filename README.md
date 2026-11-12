<div align="center">

# Visor Universal

**Un lector de libros y documentos hecho para leer de oído y con los dedos.**

Abre veinticuatro familias de formatos, deduce la estructura de los que no la
traen, lee en voz alta y exporta a braille, a DAISY y a audio. Pensado desde el
primer día para manejarse con el teclado y con lector de pantalla (NVDA, JAWS,
Narrador) en Windows.

[![Última versión](https://img.shields.io/github/v/release/hxebolax/VisorUniversal?label=versi%C3%B3n)](https://github.com/hxebolax/VisorUniversal/releases/latest)
[![Licencia: GPL v3](https://img.shields.io/badge/licencia-GPL%20v3-blue.svg)](LICENSE)
![Windows 10 y 11](https://img.shields.io/badge/Windows-10%20%7C%2011-0078D6)
![Python](https://img.shields.io/badge/Python-3.13%2B-3776AB)

[**Descargar**](https://github.com/hxebolax/VisorUniversal/releases/latest) ·
[Manual](data/idiomas/es/docs/MANUAL_USUARIO.md) ·
[Novedades](NOVEDADES.md) ·
[Documento técnico](LEEME.md) ·
[Informar de un fallo](https://github.com/hxebolax/VisorUniversal/issues)

</div>

---

## Índice

- [Qué es](#qué-es)
- [Qué vas a encontrar](#qué-vas-a-encontrar)
- [Descargar e instalar](#descargar-e-instalar)
- [Primeros pasos](#primeros-pasos)
- [Privacidad](#privacidad)
- [Para programadores](#para-programadores)
- [Colaborar](#colaborar)
- [Licencia y créditos](#licencia-y-créditos)
- [In English](#in-english)

---

## Qué es

El Visor Universal es un lector de escritorio para Windows que convierte
cualquier documento —un EPUB, un PDF escaneado, un Word de hace veinte años, un
libro DAISY, una partitura, un cómic— en un texto que **se recorre igual que una
página web con el lector de pantalla**: por encabezados, enlaces, tablas, listas,
notas, páginas o imágenes, con una sola tecla.

Lo que el documento no trae, el programa lo deduce: el índice de un PDF sin
etiquetas, los títulos de un `.txt`, las tablas de una hoja de cálculo, el texto
de una página escaneada. Y lo que no se puede leer como texto —una fórmula, un
gráfico, una partitura— se cuenta en palabras y se escribe en braille.

Es **portable**: se descomprime en una carpeta (o en un pendrive) y funciona, sin
instalar nada. Tus ajustes, marcadores y notas viajan con él.

### Para quién es

- Personas **ciegas o con baja visión** que leen con lector de pantalla, línea
  braille o voz sintética.
- **Estudiantes y profesionales** que necesitan estudiar con muchos libros a la
  vez: buscar en todos, marcar, anotar, sacar la bibliografía y el cuaderno de
  estudio.
- Quien tiene una **biblioteca grande** (por ejemplo de calibre) y quiere
  consultarla, buscar dentro de los libros y ordenarla sin malabares.

---

## Qué vas a encontrar

### Formatos

| Familia | Extensiones |
|---|---|
| Libros electrónicos | EPUB 2 y 3, FictionBook (`.fb2`), Kindle sin DRM (`.kfx`, `.azw3`, `.azw`, `.mobi`, `.prc`…) |
| PDF | Accesibles (se navegan como un EPUB), sin etiquetas (se deduce la estructura) y **escaneados con OCR** |
| Office | Word, Excel y PowerPoint modernos **y de 97** (`.doc`, `.xls`, `.ppt`), LibreOffice (`.odt`, `.ods`, `.odp`), RTF |
| Audiolibros | DAISY 2.02 y 3, con texto, con grabación o con las dos cosas sincronizadas |
| Web y correo | HTML (se queda **solo el artículo**), `.mht`, `.eml`, y **traer una página de internet** por su dirección |
| Ayuda de Windows | `.chm` y el antiguo `.hlp`, con sus imágenes |
| Digitalizaciones | DjVu, con su texto o reconociéndolo |
| Otros | Partituras MusicXML, cómics (`.cbz`, `.cbr`, `.cb7`), braille `.bra`, texto y Markdown |

### Leer y moverse

- **Navegación de una sola tecla**: `H` encabezado, `T` tabla, `K` enlace, `G`
  imagen, `L` lista, `N` nota, `P` página… y con `Mayús`, hacia atrás.
- **Índice siempre disponible** (`Control+T`), aunque el documento no lo traiga.
- **Pestañas**: varios documentos a la vez, y se recuerda por dónde ibas en cada uno.
- **Sonidos** que anuncian lo que hay sin palabras (un encabezado, un enlace, una
  imagen), y un **modo lectura** para no oír nada que no sea el texto.
- Ritmo de lectura y **tiempo restante** estimados.

### Voz y braille

- **Lectura en voz alta** con las voces del sistema (SAPI 5 y OneCore), que
  cambian solas con el idioma del texto y de tono en los diálogos.
- **Motores de voz instalables** como paquetes (`.motorvoz`): eSpeak NG,
  RHVoice, Eloquence, Vocalizer y otros.
- **Exportar a braille** (`.brf` y `.pef`) siguiendo las normas de la Comisión
  Braille Española: **matemáticas** (Código Matemático Unificado), **química** y
  **musicografía** braille.
- **Exportar a DAISY** y **a audio MP3**, con diccionario de pronunciación.

### Biblioteca

- **Todos tus libros en una lista**, con las columnas que elijas, agrupados por
  colección, autor, serie, etiqueta, editorial, idioma, formato o estado de lectura.
- **Importa bibliotecas de calibre enteras** con todos sus datos (autores, series,
  etiquetas, sinopsis, columnas propias) y las mantiene al día. Probado con
  bibliotecas de casi doscientos mil libros.
- **Busca dentro de todos los libros** a la vez, y abre cada resultado en su punto exacto.
- **Fichas a la carta**: eliges qué datos salen y en qué orden, y las exportas a
  texto o CSV.
- **Libros similares**: de la misma serie, del mismo autor, colección, etiqueta o
  editorial, con una tecla.
- **Bibliografía** en ISO 690, APA o MLA, exportable a BibTeX y RIS (Zotero,
  Mendeley, EndNote).
- **Sincronización sin servidor** entre equipos, mediante una carpeta que ya
  sincronices tú (Dropbox, OneDrive, un pendrive).

### Estudiar

- **Marcadores, notas y resaltados**, con su cuaderno de estudio por temas.
- **Copiar con la cita hecha**, **repasar lo marcado** y **practicar** con
  ejercicios sobre el propio documento.
- **Palabras relacionadas**: búsqueda por significado aprendida de tu propia
  biblioteca, sin conexión.

### Inteligencia artificial (opcional)

- Describir imágenes, resumir capítulos, preguntar sobre el documento y definir
  palabras, con un servicio de tu elección **o con un modelo instalado en tu
  propio equipo**. El programa funciona entero sin ella.

### Accesibilidad, de verdad

- **`Control+F1` explica cualquier control** de cualquier ventana: qué es, qué
  consigue y qué conviene poner. Más de doscientos, comprobados a máquina.
- **`Mayús+F1`** enseña todas las teclas, generadas del propio programa.
- Letras de acceso sin repetir, etiquetas en todos los controles, listas que
  anuncian su estado y progreso hablado en todo lo que tarda.
- Recorrido guiado la primera vez, y **teclas globales** opcionales.

### Idiomas

Español, inglés, francés, italiano y portugués, con un editor accesible para
traducir a otros.

---

## Descargar e instalar

1. Descarga el ZIP de la **[última versión](https://github.com/hxebolax/VisorUniversal/releases/latest)**
   (`VisorUniversal_v<versión>.zip`).
2. Descomprímelo donde quieras: el escritorio, `Documentos` o un pendrive.
3. Abre `VisorUniversal.exe`.

No hace falta instalar nada más: el programa trae dentro su reconocimiento de
texto (Tesseract), su 7-Zip y los componentes de Visual C++ que necesita.

**Requisitos:** Windows 10 u 11 de 64 bits.

### Actualizaciones

El programa comprueba al arrancar si hay una versión nueva (`Ayuda → Buscar
actualizaciones` para hacerlo a mano) y la instala en caliente: descarga,
comprueba, se cierra y vuelve a abrirse ya actualizado, **sin tocar tus ajustes,
marcadores ni notas**.

Cada versión se publica en **dos sitios**: el servidor del autor y las
[releases de GitHub](https://github.com/hxebolax/VisorUniversal/releases). En
`Opciones → Avanzado` eliges dónde buscarlas: en uno, en otro, en los dos (lo de
fábrica: si uno falla se usa el otro) o en una dirección personalizada. Venga de
donde venga, el paquete se comprueba con su resumen **SHA-256** y con la
**firma Ed25519** del autor: un paquete no firmado no se instala.

---

## Primeros pasos

| Tecla | Qué hace |
|---|---|
| `Control+O` | Abrir un documento |
| `Control+Mayús+B` | Biblioteca |
| `Control+T` | Índice del documento |
| `H` / `Mayús+H` | Encabezado siguiente / anterior |
| `F7` | Lista de elementos (encabezados, enlaces, tablas…) |
| `Control+F` | Buscar |
| `Control+M` | Poner un marcador |
| `F1` | Manual |
| `Mayús+F1` | Todas las teclas |
| `Control+F1` | Qué es el control en el que estás |

El [manual](data/idiomas/es/docs/MANUAL_USUARIO.md) cuenta qué hace cada cosa y
con qué tecla, y [NOVEDADES.md](NOVEDADES.md) lo que trae cada versión.

---

## Privacidad

- **No hay cuenta, ni telemetría, ni anuncios.**
- Lo único que el programa pregunta a internet por su cuenta es **si hay versión
  nueva**, y se puede apagar.
- La **inteligencia artificial** es opcional y solo se usa cuando tú lo pides,
  con el servicio que elijas o con un modelo local.
- Tus ajustes, tu biblioteca, tus marcadores y tus notas se guardan en la carpeta
  `data`, junto al programa, y en ningún otro sitio.

---

## Para programadores

El Visor Universal está escrito en **Python** con interfaz **wxPython**. Todo el
código, los comentarios, la interfaz y la documentación están en español, y los
textos de la interfaz pasan por `gettext` para poder traducirse.

### Requisitos

- Windows 10 u 11 de 64 bits.
- Python 3.13 o posterior, de 64 bits (se desarrolla con 3.15). Las compilaciones
  «sin GIL» no sirven: wxPython no las admite.
- Git.

### Puesta en marcha

```bash
git clone https://github.com/hxebolax/VisorUniversal.git
```

```bash
cd VisorUniversal
```

```bash
VisorUniversal.bat
```

`VisorUniversal.bat` es un menú accesible que lo hace todo:

| Opción | Qué hace |
|---|---|
| 1 | Elige la versión de Python, crea el entorno virtual en `entorno\` e instala los requisitos |
| 2 | Ejecuta el programa desde el código fuente |
| 3 | Compila el ejecutable con cx_Freeze en `build\VisorUniversal\` |
| 4 | Abre la carpeta del ejecutable compilado |
| 5 | Reinstala o actualiza los requisitos |
| 6 | Limpia compilaciones, caché y temporales |
| 7 | Comprueba la instalación |
| 8 | Elimina el entorno virtual |
| 9 | Prepara el paquete de actualización (ZIP firmado + `version.json`) |
| T | Editor accesible de traducciones |
| F | Estado de la firma de las actualizaciones |
| P | Batería de pruebas |

A mano, sin el menú:

```bash
python -m venv entorno
```

```bash
entorno\Scripts\python.exe -m pip install -r requirements.txt
```

```bash
entorno\Scripts\python.exe src\main.py
```

### Componentes externos

No están en el repositorio porque son binarios de terceros, pero se preparan con
un guion cada uno, que los deja donde el programa y la compilación los buscan:

| Componente | Para qué | Cómo |
|---|---|---|
| Tesseract | Reconocer texto en escaneados | `python herramientas/tesseract_portable.py` |
| 7-Zip | Abrir cómics RAR y 7z | `python herramientas/siete_zip_portable.py` |
| Motores de voz | Paquetes `.motorvoz` | `python plugins_voz/crear_paquetes.py` (ver [plugins_voz/fuentes/LEEME.md](plugins_voz/fuentes/LEEME.md)) |

Sin ellos el programa funciona igual; solo falta lo que cada uno aporta.
`basskit`, la biblioteca de audio para los DAISY grabados, va en `dependencias/`
y se instala con los requisitos.

### Pruebas y comprobaciones

```bash
entorno\Scripts\python.exe -m pytest
```

Más de mil cien pruebas. Además, unas herramientas que revisan el código y fallan
si algo se ha quedado a medias:

| Herramienta | Qué comprueba |
|---|---|
| `herramientas/revisar_ayuda.py` | Que **todos** los controles tengan su explicación de `Control+F1` |
| `herramientas/revisar_accesible.py` | Que todos los controles tengan un nombre que anunciar |
| `herramientas/revisar_menus.py` | Que no se repitan letras de acceso, en ningún idioma |
| `herramientas/revisar_opciones.py` | Que cada opción se guarde, se cargue y la use alguien |
| `herramientas/revisar_traducciones.py` | Variables, atajos y letras de acceso en las traducciones |
| `herramientas/revisar_textos.py` | Que ningún texto nombre algo que ya no existe |

### Organización

```text
src/
  main.py            Arranque, con red de seguridad e instancia única
  version.py         Versión, autoría, direcciones de actualización y clave pública
  formatos/          Un módulo por formato: cada uno convierte su archivo en un Documento
  nucleo/            Lo que no es interfaz: documento, biblioteca, voz, braille,
                     DAISY, IA, configuración, actualizaciones...
  interfaz/          Ventana principal, lector, diálogos y ayudas de Control+F1
pruebas/             Batería de pytest y sus archivos de muestra
herramientas/        Revisores, traducción, empaquetado, firma y preparación de binarios
plugins_voz/         Adaptadores de los motores de voz y el guion que arma los paquetes
data/idiomas/        Traducciones (.po/.mo) y el manual
data/sonidos/        Sonidos del programa
dependencias/        Ruedas que no están en PyPI
```

[LEEME.md](LEEME.md) es el documento técnico: cómo está hecho cada formato, las
decisiones de diseño y **por qué**, y lo que se midió para tomarlas.
[CREAR_MOTOR_DE_VOZ.md](data/idiomas/es/docs/CREAR_MOTOR_DE_VOZ.md) explica paso a
paso cómo hacer un paquete de voz.

### Publicar una versión

1. Cambia `VERSION` en `src/version.py` y escribe su apartado `## <versión>` en
   `NOVEDADES.md` (de ahí salen las notas que ve quien actualiza).
2. Compila (opción 3) y prepara el paquete (opción 9): quedan en `build/` el ZIP
   y el `version.json` **firmado**.
3. Sube los dos archivos al servidor y crea una release de GitHub con la etiqueta
   `v<versión>` y esos mismos dos archivos adjuntos.

La firma usa una clave privada Ed25519 que **no está en el repositorio** (vive en
`herramientas/claves/`, ignorada por Git). Sin ella se puede compilar y probar,
pero no publicar paquetes que acepten las copias ya instaladas.

---

## Colaborar

Las colaboraciones son bienvenidas: informes de fallos, ideas, traducciones y
código.

- **Fallos e ideas**: abre una [incidencia](https://github.com/hxebolax/VisorUniversal/issues)
  contando qué hacías, qué esperabas y qué pasó, con la versión del programa y,
  si puedes, el registro (`Ayuda → Ver registro de la aplicación`).
- **Traducciones**: el editor accesible (opción T del menú) trabaja sobre
  `data/idiomas/<código>/LC_MESSAGES/visor.po`; también sirve Poedit.
- **Código**: haz un *fork*, crea una rama y abre una *pull request*. Antes de
  enviarla:
  - escribe en español, como el resto del proyecto, y explica en los
    comentarios **por qué**, no solo qué;
  - todo control nuevo lleva su etiqueta, su letra de acceso sin repetir y su
    explicación de `Control+F1` en `src/interfaz/ayuda_control.py`;
  - todo lo que tarde va en otro hilo, con progreso hablado y forma de pararlo;
  - pasa `pytest` y los revisores de `herramientas/`.

---

## Licencia y créditos

Copyright © 2026 Héctor J. Benítez Corredera.

El Visor Universal es software libre: puedes redistribuirlo y modificarlo según
los términos de la [Licencia Pública General de GNU, versión 3](LICENSE).

Usa, entre otros, [wxPython](https://wxpython.org),
[lxml](https://lxml.de), [pypdfium2](https://github.com/pypdfium2-team/pypdfium2),
[pdfplumber](https://github.com/jsvine/pdfplumber),
[Tesseract](https://github.com/tesseract-ocr/tesseract),
[7-Zip](https://www.7-zip.org) y [BASS](https://www.un4seen.com) (gratuito para
uso no comercial). Cada componente conserva su propia licencia.

Si te resulta útil, puedes
[invitar al autor a un café](https://www.paypal.com/paypalme/hjbcdonaciones).

---

## In English

**Visor Universal** is a portable, screen-reader-first document reader for
Windows 10 and 11. It opens EPUB, PDF (including scanned PDFs, via OCR), Kindle
without DRM, Word/Excel/PowerPoint (modern and 97), LibreOffice, DAISY, HTML,
CHM/HLP, DjVu, MusicXML, comics and more, and makes all of them navigable with
single-key commands like a web page in NVDA or JAWS. It reads aloud, exports to
Spanish braille (including maths, chemistry and music), DAISY and MP3, and
manages large libraries — including whole calibre libraries — with full-text
search across every book.

The interface is available in Spanish, English, French, Italian and Portuguese.
The source code, comments and documentation are in Spanish. Download the latest
version from the [releases page](https://github.com/hxebolax/VisorUniversal/releases/latest).
Licensed under the GPL v3.
