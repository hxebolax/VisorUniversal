# -*- coding: utf-8 -*-
"""Genera un documento de muestra de **cada formato** que el programa abre.

Queda en ``adjuntos/documentos_muestra``, repartido por subcarpetas. Sirve para
tres cosas que no se pueden hacer sin él:

1. **Probar a mano.** Abrir el programa y pasar por los veinticuatro formatos
   uno detrás de otro, para ver si alguno se ha estropeado, sin tener que
   buscarse los archivos por el disco.
2. **Comparar.** Todos los documentos dicen **lo mismo**: el mismo título, los
   mismos apartados, la misma tabla, la misma lista y la misma cita. Así, lo
   que cambie de un formato a otro es cosa del formato y no del contenido, que
   es justo lo que hay que ver.
3. **Enseñar qué se abre.** Un formato que se puede abrir y del que no hay
   ningún archivo a mano es un formato del que nadie se acuerda.

**Lo que se genera y lo que se copia.** Casi todo se escribe aquí, byte a byte
—los ZIP con XML dentro, el PDF, el MOBI, el correo, el braille—, y sale en
español y con el mismo texto. Tres formatos no se pueden fabricar sin el
programa que los inventó, y para esos se copia una muestra de verdad de las que
ya están en ``adjuntos``: se dice de dónde sale cada una en el LEEME que
acompaña a la carpeta.

Uso::

    python herramientas/documentos_muestra.py
"""

from __future__ import annotations

import base64
import shutil
import struct
import subprocess
import sys
import tarfile
import zipfile
import zlib
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

DESTINO = RAIZ / "adjuntos" / "documentos_muestra"

TITULO = "El vencejo común"
AUTOR = "Visor Universal"

#: El texto que llevan todos, en el mismo orden. Es un documento corto y de
#: verdad —con sus apartados, su lista, su tabla y su cita—, no un «hola mundo»:
#: lo que se quiere comprobar es si el formato conserva la **estructura**, y un
#: párrafo suelto no tiene ninguna.
APARTADOS = [
    ("Qué es", [
        "El vencejo común (Apus apus) es un ave que pasa casi toda su vida en "
        "el aire. Come, bebe, se aparea y duerme volando.",
        "Solo se posa para criar. Un vencejo joven puede pasar diez meses "
        "seguidos sin tocar el suelo.",
    ]),
    ("Cómo se reconoce", [
        "Se distingue de la golondrina por tres cosas:",
    ]),
    ("Dónde y cuándo", [
        "Llega a la península a finales de abril y se marcha en agosto. "
        "Inverna en el África subsahariana.",
    ]),
]

LISTA = ["Las alas en forma de hoz, muy estrechas.",
         "El vuelo, que no da aletazos cortos sino planeos largos.",
         "El chillido agudo, que se oye antes de ver al pájaro."]

TABLA = [["Especie", "Envergadura", "Peso"],
         ["Vencejo común", "42 cm", "40 g"],
         ["Vencejo real", "57 cm", "100 g"],
         ["Golondrina", "33 cm", "20 g"]]

CITA = ("Se ha calculado que un vencejo común recorre dos millones de "
        "kilómetros a lo largo de su vida.")

NOTA = "Los datos de envergadura y peso son de la Guía de aves de la SEO."


# ---------------------------------------------------------------------------
# Piezas comunes
# ---------------------------------------------------------------------------

def texto_plano(encabezados_en_mayusculas: bool = True) -> str:
    """El documento como texto corrido, que es la base de casi todos.

    Los encabezados van en mayúsculas porque en texto plano no hay otra forma de
    marcarlos.  Para el braille no: allí cada mayúscula lleva delante su propio
    signo, y un título entero en mayúsculas se lee con un signo por letra.
    """
    lineas = [TITULO, AUTOR, ""]
    for numero, (encabezado, parrafos) in enumerate(APARTADOS):
        lineas.append(encabezado.upper() if encabezados_en_mayusculas
                      else encabezado)
        lineas.append("")
        lineas.extend(parrafos)
        if numero == 1:
            lineas.append("")
            lineas.extend("- " + punto for punto in LISTA)
        if numero == 2:
            lineas.append("")
            lineas.extend("\t".join(fila) for fila in TABLA)
            lineas.append("")
            lineas.append("«%s»" % CITA)
        lineas.append("")
    lineas.append(NOTA)
    return "\n".join(lineas) + "\n"


def cuerpo_html() -> str:
    """El documento en HTML, con encabezados, lista, tabla y cita de verdad."""
    partes = ["<h1>%s</h1>" % TITULO, "<p><em>%s</em></p>" % AUTOR]
    for numero, (encabezado, parrafos) in enumerate(APARTADOS):
        partes.append("<h2>%s</h2>" % encabezado)
        partes.extend("<p>%s</p>" % parrafo for parrafo in parrafos)
        if numero == 1:
            partes.append("<ul>%s</ul>"
                          % "".join("<li>%s</li>" % punto for punto in LISTA))
        if numero == 2:
            partes.append("<table><caption>Comparación</caption>"
                          "<thead><tr>%s</tr></thead><tbody>%s</tbody></table>"
                          % ("".join("<th>%s</th>" % celda for celda in TABLA[0]),
                             "".join("<tr>%s</tr>"
                                     % "".join("<td>%s</td>" % celda
                                               for celda in fila)
                                     for fila in TABLA[1:])))
            partes.append("<blockquote><p>%s</p></blockquote>" % CITA)
    partes.append("<p><small>%s</small></p>" % NOTA)
    return "\n".join(partes)


def pagina_html(xhtml: bool = False) -> str:
    """Una página completa, en HTML5 o en XHTML."""
    if xhtml:
        return ('<?xml version="1.0" encoding="utf-8"?>\n'
                '<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="es">'
                '<head><meta charset="utf-8"/><title>%s</title></head>'
                '<body>%s</body></html>\n' % (TITULO, cuerpo_html()))
    return ('<!DOCTYPE html>\n<html lang="es"><head><meta charset="utf-8">'
            '<title>%s</title></head><body>%s</body></html>\n'
            % (TITULO, cuerpo_html()))


def imagen_png(numero: int = 1) -> bytes:
    """Un PNG de verdad, pequeño, para los cómics y las portadas."""
    ancho = alto = 96

    def trozo(clase: bytes, datos: bytes) -> bytes:
        return (struct.pack(">I", len(datos)) + clase + datos
                + struct.pack(">I", zlib.crc32(clase + datos)))

    filas = []
    for fila in range(alto):
        pixeles = bytearray()
        for columna in range(ancho):
            pixeles.extend(((columna * 2 + numero * 20) % 256,
                            (fila * 2 + numero * 10) % 256,
                            128))
        # Cada fila del PNG lleva delante un byte que dice cómo se ha filtrado;
        # cero es «tal cual», que es lo que hace falta aquí.
        filas.append(bytes([0]) + bytes(pixeles))
    firma = bytes([0x89]) + b"PNG\r\n\x1a\n"
    return (firma
            + trozo(b"IHDR", struct.pack(">IIBBBBB", ancho, alto, 8, 2, 0, 0, 0))
            + trozo(b"IDAT", zlib.compress(b"".join(filas), 9))
            + trozo(b"IEND", b""))


def escribir(ruta: Path, datos) -> Path:
    """Escribe un archivo y dice lo que ocupa."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(datos, str):
        ruta.write_text(datos, encoding="utf-8")
    else:
        ruta.write_bytes(datos)
    return ruta


# ---------------------------------------------------------------------------
# Texto y web
# ---------------------------------------------------------------------------

def hacer_texto(carpeta: Path) -> list:
    """Los seis que el programa trata como texto plano, y el Markdown."""
    plano = texto_plano()
    marcado = ["# %s" % TITULO, "", "*%s*" % AUTOR, ""]
    for numero, (encabezado, parrafos) in enumerate(APARTADOS):
        marcado.append("## %s" % encabezado)
        marcado.append("")
        for parrafo in parrafos:
            marcado.extend([parrafo, ""])
        if numero == 1:
            marcado.extend(["- " + punto for punto in LISTA] + [""])
        if numero == 2:
            marcado.append("| " + " | ".join(TABLA[0]) + " |")
            marcado.append("|" + "---|" * len(TABLA[0]))
            for fila in TABLA[1:]:
                marcado.append("| " + " | ".join(fila) + " |")
            marcado.extend(["", "> " + CITA, ""])
    marcado.append("*%s*" % NOTA)
    md = "\n".join(marcado) + "\n"
    return [escribir(carpeta / "vencejo.txt", plano),
            escribir(carpeta / "vencejo.text", plano),
            escribir(carpeta / "vencejo.md", md),
            escribir(carpeta / "vencejo.markdown", md),
            escribir(carpeta / "registro.log", plano),
            escribir(carpeta / "leeme.nfo", plano)]


def hacer_web(carpeta: Path) -> list:
    """Las cuatro extensiones que abre el analizador de páginas."""
    return [escribir(carpeta / "vencejo.html", pagina_html()),
            escribir(carpeta / "vencejo.htm", pagina_html()),
            escribir(carpeta / "vencejo.xhtml", pagina_html(xhtml=True)),
            escribir(carpeta / "vencejo.xml", pagina_html(xhtml=True))]


# ---------------------------------------------------------------------------
# Libros
# ---------------------------------------------------------------------------

def hacer_epub(carpeta: Path) -> list:
    """Un EPUB 3 completo: envoltorio, metadatos, índice y dos capítulos.

    Se escribe a mano y no con el exportador del programa a propósito: así el
    archivo de muestra no depende de que el exportador esté bien, que es una de
    las cosas que se quieren comprobar con él.
    """
    ruta = carpeta / "vencejo.epub"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    capitulos = []
    for numero, (encabezado, parrafos) in enumerate(APARTADOS, start=1):
        cuerpo = ["<h1>%s</h1>" % encabezado]
        cuerpo.extend("<p>%s</p>" % parrafo for parrafo in parrafos)
        if numero == 2:
            cuerpo.append("<ul>%s</ul>"
                          % "".join("<li>%s</li>" % punto for punto in LISTA))
        if numero == 3:
            cuerpo.append("<table><thead><tr>%s</tr></thead><tbody>%s</tbody>"
                          "</table>"
                          % ("".join("<th>%s</th>" % c for c in TABLA[0]),
                             "".join("<tr>%s</tr>"
                                     % "".join("<td>%s</td>" % c for c in fila)
                                     for fila in TABLA[1:])))
            cuerpo.append("<blockquote><p>%s</p></blockquote>" % CITA)
            cuerpo.append('<figure><img src="portada.png" alt="Un vencejo en '
                          'vuelo, visto desde abajo."/>'
                          "<figcaption>Vencejo común en vuelo.</figcaption>"
                          "</figure>")
        capitulos.append((encabezado, "<?xml version='1.0' encoding='utf-8'?>"
                          '<html xmlns="http://www.w3.org/1999/xhtml" '
                          'xml:lang="es"><head><title>%s</title></head>'
                          "<body>%s</body></html>"
                          % (encabezado, "".join(cuerpo))))

    manifiesto = "".join(
        '<item id="c%d" href="c%d.xhtml" media-type="application/xhtml+xml"/>'
        % (numero, numero) for numero in range(1, len(capitulos) + 1))
    lomo = "".join('<itemref idref="c%d"/>' % numero
                   for numero in range(1, len(capitulos) + 1))
    opf = ("<?xml version='1.0' encoding='utf-8'?>"
           '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
           'unique-identifier="id" xml:lang="es"><metadata '
           'xmlns:dc="http://purl.org/dc/elements/1.1/">'
           '<dc:identifier id="id">visor-muestra-vencejo</dc:identifier>'
           "<dc:title>%s</dc:title><dc:creator>%s</dc:creator>"
           "<dc:language>es</dc:language>"
           '<meta property="dcterms:modified">2026-01-01T00:00:00Z</meta>'
           '<meta property="schema:accessMode">textual</meta>'
           '<meta property="schema:accessibilityFeature">structuralNavigation</meta>'
           '<meta property="schema:accessibilityFeature">alternativeText</meta>'
           '<meta property="schema:accessibilitySummary">Documento de muestra '
           "con encabezados, lista, tabla e imagen descrita.</meta>"
           "</metadata><manifest>"
           '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" '
           'properties="nav"/>'
           '<item id="img" href="portada.png" media-type="image/png"/>'
           "%s</manifest><spine>%s</spine></package>"
           % (TITULO, AUTOR, manifiesto, lomo))
    navegacion = ("<?xml version='1.0' encoding='utf-8'?>"
                  '<html xmlns="http://www.w3.org/1999/xhtml" '
                  'xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="es">'
                  "<head><title>Índice</title></head><body>"
                  '<nav epub:type="toc"><h1>Índice</h1><ol>%s</ol></nav>'
                  "</body></html>"
                  % "".join('<li><a href="c%d.xhtml">%s</a></li>'
                            % (numero, titulo)
                            for numero, (titulo, _cuerpo)
                            in enumerate(capitulos, start=1)))
    with zipfile.ZipFile(ruta, "w") as paquete:
        # El «mimetype» va primero y sin comprimir: lo dice la norma y es lo que
        # permite reconocer un EPUB por sus primeros bytes.
        paquete.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip",
                         compress_type=zipfile.ZIP_STORED)
        paquete.writestr("META-INF/container.xml",
                         "<?xml version='1.0' encoding='utf-8'?>"
                         '<container version="1.0" xmlns="urn:oasis:names:tc:'
                         'opendocument:xmlns:container"><rootfiles>'
                         '<rootfile full-path="OEBPS/content.opf" '
                         'media-type="application/oebps-package+xml"/>'
                         "</rootfiles></container>")
        paquete.writestr("OEBPS/content.opf", opf)
        paquete.writestr("OEBPS/nav.xhtml", navegacion)
        paquete.writestr("OEBPS/portada.png", imagen_png(3))
        for numero, (_titulo, cuerpo) in enumerate(capitulos, start=1):
            paquete.writestr("OEBPS/c%d.xhtml" % numero, cuerpo)
    return [ruta]


def hacer_fb2(carpeta: Path) -> list:
    """Un FictionBook, que es un solo XML con el libro entero dentro."""
    secciones = []
    for numero, (encabezado, parrafos) in enumerate(APARTADOS):
        cuerpo = ["<title><p>%s</p></title>" % encabezado]
        cuerpo.extend("<p>%s</p>" % parrafo for parrafo in parrafos)
        if numero == 1:
            cuerpo.extend("<p>· %s</p>" % punto for punto in LISTA)
        if numero == 2:
            cuerpo.append("<cite><p>%s</p></cite>" % CITA)
        secciones.append("<section>%s</section>" % "".join(cuerpo))
    contenido = ("<?xml version='1.0' encoding='utf-8'?>"
                 '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0">'
                 "<description><title-info><genre>nonfiction</genre>"
                 "<author><first-name>Visor</first-name>"
                 "<last-name>Universal</last-name></author>"
                 "<book-title>%s</book-title><lang>es</lang></title-info>"
                 "</description><body>%s</body></FictionBook>"
                 % (TITULO, "".join(secciones)))
    return [escribir(carpeta / "vencejo.fb2", contenido)]


# ---------------------------------------------------------------------------
# Ofimática de ahora
# ---------------------------------------------------------------------------

_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_REL = "http://schemas.openxmlformats.org/package/2006/relationships"


def _tipos_ooxml(principal: str, tipo: str) -> str:
    """El «[Content_Types].xml» que todo paquete de Office lleva delante."""
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/'
            'content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxml'
            'formats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Default Extension="png" ContentType="image/png"/>'
            '<Override PartName="/%s" ContentType="%s"/>'
            "</Types>" % (principal, tipo))


def _relaciones(destino: str, tipo: str) -> str:
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="%s"><Relationship Id="rId1" Type="%s" '
            'Target="%s"/></Relationships>' % (_REL, tipo, destino))


def hacer_docx(carpeta: Path) -> list:
    """Un DOCX con encabezados de verdad, lista, tabla y cita."""
    cuerpo = ['<w:p><w:pPr><w:pStyle w:val="Title"/></w:pPr><w:r><w:t>%s</w:t>'
              "</w:r></w:p>" % TITULO]
    for numero, (encabezado, parrafos) in enumerate(APARTADOS):
        cuerpo.append('<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr>'
                      "<w:r><w:t>%s</w:t></w:r></w:p>" % encabezado)
        for parrafo in parrafos:
            cuerpo.append('<w:p><w:r><w:t xml:space="preserve">%s</w:t></w:r>'
                          "</w:p>" % parrafo)
        if numero == 1:
            for punto in LISTA:
                cuerpo.append('<w:p><w:pPr><w:pStyle w:val="ListParagraph"/>'
                              '<w:numPr><w:ilvl w:val="0"/>'
                              '<w:numId w:val="1"/></w:numPr></w:pPr>'
                              "<w:r><w:t>%s</w:t></w:r></w:p>" % punto)
        if numero == 2:
            filas = []
            for fila in TABLA:
                celdas = "".join(
                    "<w:tc><w:p><w:r><w:t>%s</w:t></w:r></w:p></w:tc>" % celda
                    for celda in fila)
                filas.append("<w:tr>%s</w:tr>" % celdas)
            cuerpo.append("<w:tbl>%s</w:tbl>" % "".join(filas))
            cuerpo.append('<w:p><w:pPr><w:pStyle w:val="Quote"/></w:pPr>'
                          "<w:r><w:t>%s</w:t></w:r></w:p>" % CITA)
    documento = ('<?xml version="1.0" encoding="UTF-8"?>'
                 '<w:document xmlns:w="%s"><w:body>%s</w:body></w:document>'
                 % (_W, "".join(cuerpo)))
    ruta = carpeta / "vencejo.docx"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED) as paquete:
        paquete.writestr("[Content_Types].xml", _tipos_ooxml(
            "word/document.xml",
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document.main+xml"))
        paquete.writestr("_rels/.rels", _relaciones(
            "word/document.xml",
            "http://schemas.openxmlformats.org/officeDocument/2006/"
            "relationships/officeDocument"))
        paquete.writestr("word/document.xml", documento)
    return [ruta, escribir(carpeta / "vencejo.docm", ruta.read_bytes())]


_OFFICE = "urn:oasis:names:tc:opendocument:xmlns:office:1.0"
_TEXTO = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
_TABLAS = "urn:oasis:names:tc:opendocument:xmlns:table:1.0"


def _paquete_odf(ruta: Path, tipo: str, contenido: str) -> Path:
    """Escribe un paquete de OpenDocument con su «mimetype» sin comprimir."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED) as paquete:
        paquete.writestr(zipfile.ZipInfo("mimetype"), tipo,
                         compress_type=zipfile.ZIP_STORED)
        paquete.writestr("META-INF/manifest.xml",
                         '<?xml version="1.0" encoding="UTF-8"?>'
                         '<manifest:manifest xmlns:manifest="urn:oasis:names:'
                         'tc:opendocument:xmlns:manifest:1.0" '
                         'manifest:version="1.3">'
                         '<manifest:file-entry manifest:full-path="/" '
                         'manifest:media-type="%s"/>'
                         '<manifest:file-entry manifest:full-path="content.xml" '
                         'manifest:media-type="text/xml"/>'
                         "</manifest:manifest>" % tipo)
        paquete.writestr("content.xml", contenido)
        paquete.writestr("meta.xml",
                         '<?xml version="1.0" encoding="UTF-8"?>'
                         '<office:document-meta xmlns:office="%s" '
                         'xmlns:dc="http://purl.org/dc/elements/1.1/">'
                         "<office:meta><dc:title>%s</dc:title>"
                         "<dc:creator>%s</dc:creator></office:meta>"
                         "</office:document-meta>" % (_OFFICE, TITULO, AUTOR))
    return ruta


def hacer_odt(carpeta: Path) -> list:
    """Un ODT con la misma estructura que el DOCX."""
    cuerpo = ['<text:h text:outline-level="1">%s</text:h>' % TITULO]
    for numero, (encabezado, parrafos) in enumerate(APARTADOS):
        cuerpo.append('<text:h text:outline-level="2">%s</text:h>' % encabezado)
        cuerpo.extend("<text:p>%s</text:p>" % parrafo for parrafo in parrafos)
        if numero == 1:
            cuerpo.append("<text:list>%s</text:list>"
                          % "".join("<text:list-item><text:p>%s</text:p>"
                                    "</text:list-item>" % punto
                                    for punto in LISTA))
        if numero == 2:
            filas = "".join(
                "<table:table-row>%s</table:table-row>"
                % "".join("<table:table-cell><text:p>%s</text:p>"
                          "</table:table-cell>" % celda for celda in fila)
                for fila in TABLA)
            cuerpo.append('<table:table table:name="Comparación">'
                          '<table:table-column table:number-columns-repeated="3"/>'
                          "%s</table:table>" % filas)
            cuerpo.append('<text:p text:style-name="Quotations">%s</text:p>'
                          % CITA)
    contenido = ('<?xml version="1.0" encoding="UTF-8"?>'
                 '<office:document-content xmlns:office="%s" xmlns:text="%s" '
                 'xmlns:table="%s" office:version="1.3"><office:body>'
                 "<office:text>%s</office:text></office:body>"
                 "</office:document-content>"
                 % (_OFFICE, _TEXTO, _TABLAS, "".join(cuerpo)))
    ruta = _paquete_odf(carpeta / "vencejo.odt",
                        "application/vnd.oasis.opendocument.text", contenido)
    return [ruta, escribir(carpeta / "vencejo.fodt", contenido)]


def hacer_rtf(carpeta: Path) -> list:
    """Un RTF, que es texto con marcas y sin envoltorio."""
    def limpio(texto: str) -> str:
        salida = []
        for letra in texto:
            if ord(letra) < 128:
                salida.append(letra.replace(chr(92), chr(92) * 2))
            else:
                salida.append(chr(92) + "u%d?" % ord(letra))
        return "".join(salida)

    partes = [r"{\rtf1\ansi\deff0{\fonttbl{\f0 Calibri;}}",
              r"\fs32\b " + limpio(TITULO) + r"\b0\fs22\par",
              r"\i " + limpio(AUTOR) + r"\i0\par\par"]
    for numero, (encabezado, parrafos) in enumerate(APARTADOS):
        partes.append(r"\fs28\b " + limpio(encabezado) + r"\b0\fs22\par")
        for parrafo in parrafos:
            partes.append(limpio(parrafo) + r"\par")
        if numero == 1:
            for punto in LISTA:
                partes.append(r"\bullet\tab " + limpio(punto) + r"\par")
        if numero == 2:
            for fila in TABLA:
                partes.append(limpio("\t".join(fila)) + r"\par")
            partes.append(r"\i " + limpio(CITA) + r"\i0\par")
        partes.append(r"\par")
    partes.append(limpio(NOTA) + r"\par}")
    # Cada trozo en su renglón: en RTF, una orden pegada a la letra que
    # sigue se lee como otra orden distinta, que no existe. El salto de
    # línea no significa nada dentro de un RTF y sirve de separador.
    return [escribir(carpeta / "vencejo.rtf", chr(10).join(partes))]


# ---------------------------------------------------------------------------
# Presentaciones y hojas
# ---------------------------------------------------------------------------

_P = "http://schemas.openxmlformats.org/presentationml/2006/main"
_A = "http://schemas.openxmlformats.org/drawingml/2006/main"


def _diapositiva_pptx(titulo: str, lineas: list) -> str:
    """Una diapositiva con su cuadro de título y su cuadro de contenido."""
    def cuadro(identificador: int, nombre: str, arriba: int, textos: list) -> str:
        parrafos = "".join(
            '<a:p><a:r><a:t>%s</a:t></a:r></a:p>' % texto for texto in textos)
        return ('<p:sp><p:nvSpPr><p:cNvPr id="%d" name="%s"/><p:cNvSpPr/>'
                "<p:nvPr/></p:nvSpPr><p:spPr><a:xfrm>"
                '<a:off x="685800" y="%d"/><a:ext cx="7772400" cy="1000000"/>'
                "</a:xfrm></p:spPr><p:txBody><a:bodyPr/><a:lstStyle/>%s"
                "</p:txBody></p:sp>" % (identificador, nombre, arriba, parrafos))

    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<p:sld xmlns:p="%s" xmlns:a="%s"><p:cSld><p:spTree>'
            '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/>'
            "</p:nvGrpSpPr><p:grpSpPr/>%s%s</p:spTree></p:cSld></p:sld>"
            % (_P, _A, cuadro(2, "Título", 300000, [titulo]),
               cuadro(3, "Contenido", 1600000, lineas)))


def hacer_pptx(carpeta: Path) -> list:
    """Una presentación con una diapositiva por apartado."""
    diapositivas = []
    for numero, (encabezado, parrafos) in enumerate(APARTADOS):
        lineas = list(parrafos)
        if numero == 1:
            lineas.extend(LISTA)
        if numero == 2:
            lineas.append(CITA)
        diapositivas.append(_diapositiva_pptx(encabezado, lineas))

    tipos = ['<?xml version="1.0" encoding="UTF-8"?>'
             '<Types xmlns="http://schemas.openxmlformats.org/package/2006/'
             'content-types">'
             '<Default Extension="rels" ContentType="application/vnd.openxml'
             'formats-package.relationships+xml"/>'
             '<Default Extension="xml" ContentType="application/xml"/>'
             '<Override PartName="/ppt/presentation.xml" ContentType='
             '"application/vnd.openxmlformats-officedocument.presentationml.'
             'presentation.main+xml"/>']
    for numero in range(1, len(diapositivas) + 1):
        tipos.append('<Override PartName="/ppt/slides/slide%d.xml" '
                     'ContentType="application/vnd.openxmlformats-officedocument.'
                     'presentationml.slide+xml"/>' % numero)
    tipos.append("</Types>")

    relaciones = ['<?xml version="1.0" encoding="UTF-8"?><Relationships '
                  'xmlns="%s">' % _REL]
    lista = []
    for numero in range(1, len(diapositivas) + 1):
        relaciones.append('<Relationship Id="rId%d" Type="http://schemas.'
                          'openxmlformats.org/officeDocument/2006/relationships/'
                          'slide" Target="slides/slide%d.xml"/>'
                          % (numero, numero))
        lista.append('<p:sldId id="%d" r:id="rId%d"/>' % (255 + numero, numero))
    relaciones.append("</Relationships>")

    presentacion = ('<?xml version="1.0" encoding="UTF-8"?>'
                    '<p:presentation xmlns:p="%s" xmlns:r="http://schemas.'
                    'openxmlformats.org/officeDocument/2006/relationships">'
                    "<p:sldIdLst>%s</p:sldIdLst></p:presentation>"
                    % (_P, "".join(lista)))

    ruta = carpeta / "vencejo.pptx"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED) as paquete:
        paquete.writestr("[Content_Types].xml", "".join(tipos))
        paquete.writestr("_rels/.rels", _relaciones(
            "ppt/presentation.xml",
            "http://schemas.openxmlformats.org/officeDocument/2006/"
            "relationships/officeDocument"))
        paquete.writestr("ppt/presentation.xml", presentacion)
        paquete.writestr("ppt/_rels/presentation.xml.rels", "".join(relaciones))
        for numero, contenido in enumerate(diapositivas, start=1):
            paquete.writestr("ppt/slides/slide%d.xml" % numero, contenido)
    return [ruta,
            escribir(carpeta / "vencejo.pptm", ruta.read_bytes()),
            escribir(carpeta / "vencejo.ppsx", ruta.read_bytes())]


_DRAW = "urn:oasis:names:tc:opendocument:xmlns:drawing:1.0"
_PRES = "urn:oasis:names:tc:opendocument:xmlns:presentation:1.0"


def hacer_odp(carpeta: Path) -> list:
    """La misma presentación en OpenDocument."""
    paginas = []
    for numero, (encabezado, parrafos) in enumerate(APARTADOS):
        lineas = list(parrafos)
        if numero == 1:
            lineas.extend(LISTA)
        if numero == 2:
            lineas.append(CITA)
        marcos = ['<draw:frame svg:x="1cm" svg:y="1cm" svg:width="20cm" '
                  'svg:height="2cm"><draw:text-box><text:p>%s</text:p>'
                  "</draw:text-box></draw:frame>" % encabezado]
        marcos.append('<draw:frame svg:x="1cm" svg:y="4cm" svg:width="20cm" '
                      'svg:height="10cm"><draw:text-box>%s</draw:text-box>'
                      "</draw:frame>"
                      % "".join("<text:p>%s</text:p>" % linea for linea in lineas))
        paginas.append('<draw:page draw:name="%s">%s</draw:page>'
                       % (encabezado, "".join(marcos)))
    contenido = ('<?xml version="1.0" encoding="UTF-8"?>'
                 '<office:document-content xmlns:office="%s" xmlns:text="%s" '
                 'xmlns:draw="%s" xmlns:presentation="%s" '
                 'xmlns:svg="urn:oasis:names:tc:opendocument:xmlns:svg-'
                 'compatible:1.0" office:version="1.3"><office:body>'
                 "<office:presentation>%s</office:presentation></office:body>"
                 "</office:document-content>"
                 % (_OFFICE, _TEXTO, _DRAW, _PRES, "".join(paginas)))
    ruta = _paquete_odf(carpeta / "vencejo.odp",
                        "application/vnd.oasis.opendocument.presentation",
                        contenido)
    return [ruta, escribir(carpeta / "vencejo.fodp", contenido)]


def hacer_xlsx(carpeta: Path) -> list:
    """Un libro con dos hojas: la comparación y las cifras del viaje."""
    hojas = [("Comparación", TABLA),
             ("El viaje", [["Etapa", "Kilómetros"],
                           ["Península a Sahel", "3500"],
                           ["Sahel a Congo", "2800"],
                           ["Vuelta", "6300"]])]
    compartidas = []
    indice = {}
    for _nombre, filas in hojas:
        for fila in filas:
            for celda in fila:
                if celda not in indice:
                    indice[celda] = len(compartidas)
                    compartidas.append(celda)
    tabla_cadenas = ('<?xml version="1.0" encoding="UTF-8"?>'
                     '<sst xmlns="http://schemas.openxmlformats.org/'
                     'spreadsheetml/2006/main" count="%d" uniqueCount="%d">%s'
                     "</sst>"
                     % (len(compartidas), len(compartidas),
                        "".join("<si><t>%s</t></si>" % texto
                                for texto in compartidas)))

    def hoja_xml(filas) -> str:
        renglones = []
        for numero, fila in enumerate(filas, start=1):
            celdas = "".join(
                '<c r="%s%d" t="s"><v>%d</v></c>'
                % (chr(ord("A") + columna), numero, indice[celda])
                for columna, celda in enumerate(fila))
            renglones.append('<row r="%d">%s</row>' % (numero, celdas))
        return ('<?xml version="1.0" encoding="UTF-8"?>'
                '<worksheet xmlns="http://schemas.openxmlformats.org/'
                'spreadsheetml/2006/main"><sheetData>%s</sheetData></worksheet>'
                % "".join(renglones))

    ruta = carpeta / "vencejo.xlsx"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tipos = ['<?xml version="1.0" encoding="UTF-8"?>'
             '<Types xmlns="http://schemas.openxmlformats.org/package/2006/'
             'content-types">'
             '<Default Extension="rels" ContentType="application/vnd.openxml'
             'formats-package.relationships+xml"/>'
             '<Default Extension="xml" ContentType="application/xml"/>'
             '<Override PartName="/xl/workbook.xml" ContentType="application/'
             'vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
             '<Override PartName="/xl/sharedStrings.xml" ContentType='
             '"application/vnd.openxmlformats-officedocument.spreadsheetml.'
             'sharedStrings+xml"/>']
    hojas_rel = ['<?xml version="1.0" encoding="UTF-8"?><Relationships '
                 'xmlns="%s"><Relationship Id="rIdS" Type="http://schemas.'
                 'openxmlformats.org/officeDocument/2006/relationships/'
                 'sharedStrings" Target="sharedStrings.xml"/>' % _REL]
    lista_hojas = []
    for numero, (nombre, _filas) in enumerate(hojas, start=1):
        tipos.append('<Override PartName="/xl/worksheets/sheet%d.xml" '
                     'ContentType="application/vnd.openxmlformats-officedocument.'
                     'spreadsheetml.worksheet+xml"/>' % numero)
        hojas_rel.append('<Relationship Id="rId%d" Type="http://schemas.'
                         'openxmlformats.org/officeDocument/2006/relationships/'
                         'worksheet" Target="worksheets/sheet%d.xml"/>'
                         % (numero, numero))
        lista_hojas.append('<sheet name="%s" sheetId="%d" r:id="rId%d"/>'
                           % (nombre, numero, numero))
    tipos.append("</Types>")
    hojas_rel.append("</Relationships>")
    libro = ('<?xml version="1.0" encoding="UTF-8"?>'
             '<workbook xmlns="http://schemas.openxmlformats.org/'
             'spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.'
             'org/officeDocument/2006/relationships"><sheets>%s</sheets>'
             "</workbook>" % "".join(lista_hojas))
    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED) as paquete:
        paquete.writestr("[Content_Types].xml", "".join(tipos))
        paquete.writestr("_rels/.rels", _relaciones(
            "xl/workbook.xml",
            "http://schemas.openxmlformats.org/officeDocument/2006/"
            "relationships/officeDocument"))
        paquete.writestr("xl/workbook.xml", libro)
        paquete.writestr("xl/_rels/workbook.xml.rels", "".join(hojas_rel))
        paquete.writestr("xl/sharedStrings.xml", tabla_cadenas)
        for numero, (_nombre, filas) in enumerate(hojas, start=1):
            paquete.writestr("xl/worksheets/sheet%d.xml" % numero, hoja_xml(filas))
    return [ruta, escribir(carpeta / "vencejo.xlsm", ruta.read_bytes())]


def hacer_ods(carpeta: Path) -> list:
    """El mismo libro en OpenDocument."""
    hojas = [("Comparación", TABLA),
             ("El viaje", [["Etapa", "Kilómetros"],
                           ["Península a Sahel", "3500"],
                           ["Sahel a Congo", "2800"],
                           ["Vuelta", "6300"]])]
    tablas = []
    for nombre, filas in hojas:
        renglones = "".join(
            "<table:table-row>%s</table:table-row>"
            % "".join('<table:table-cell office:value-type="string">'
                      "<text:p>%s</text:p></table:table-cell>" % celda
                      for celda in fila)
            for fila in filas)
        tablas.append('<table:table table:name="%s">'
                      '<table:table-column table:number-columns-repeated="%d"/>'
                      "%s</table:table>"
                      % (nombre, max(len(fila) for fila in filas), renglones))
    contenido = ('<?xml version="1.0" encoding="UTF-8"?>'
                 '<office:document-content xmlns:office="%s" xmlns:text="%s" '
                 'xmlns:table="%s" office:version="1.3"><office:body>'
                 "<office:spreadsheet>%s</office:spreadsheet></office:body>"
                 "</office:document-content>"
                 % (_OFFICE, _TEXTO, _TABLAS, "".join(tablas)))
    ruta = _paquete_odf(carpeta / "vencejo.ods",
                        "application/vnd.oasis.opendocument.spreadsheet",
                        contenido)
    return [ruta, escribir(carpeta / "vencejo.fods", contenido)]


# ---------------------------------------------------------------------------
# Cómics
# ---------------------------------------------------------------------------

PAGINAS_COMIC = 6


def hacer_comics(carpeta: Path) -> list:
    """El mismo cómic en las cuatro formas de empaquetarlo.

    El `.cb7` y el `.cbr` se hacen con programas de fuera —el 7-Zip que viaja
    con el visor y el WinRAR de quien lo tenga—, porque escribir un RAR es otra
    cosa que leerlo y aquí no hace falta.
    """
    carpeta.mkdir(parents=True, exist_ok=True)
    paginas = [("pagina%02d.png" % numero, imagen_png(numero))
               for numero in range(1, PAGINAS_COMIC + 1)]
    salidos = []

    cbz = carpeta / "vencejo.cbz"
    with zipfile.ZipFile(cbz, "w", zipfile.ZIP_DEFLATED) as paquete:
        for nombre, datos in paginas:
            paquete.writestr(nombre, datos)
    salidos.append(cbz)

    cbt = carpeta / "vencejo.cbt"
    with tarfile.open(cbt, "w") as paquete:
        for nombre, datos in paginas:
            info = tarfile.TarInfo(nombre)
            info.size = len(datos)
            paquete.addfile(info, __import__("io").BytesIO(datos))
    salidos.append(cbt)

    # Para los otros dos hace falta un programa que sepa escribirlos.
    import tempfile as _temporal

    with _temporal.TemporaryDirectory(prefix="comic-") as suelto:
        sueltas = Path(suelto)
        for nombre, datos in paginas:
            (sueltas / nombre).write_bytes(datos)
        siete = _siete_zip()
        if siete:
            destino = carpeta / "vencejo.cb7"
            if destino.exists():
                destino.unlink()
            subprocess.run([siete, "a", "-t7z", "-bso0", "-bsp0", str(destino),
                            str(sueltas / "*.png")], check=False)
            if destino.is_file():
                salidos.append(destino)
        winrar = _winrar()
        if winrar:
            destino = carpeta / "vencejo.cbr"
            if destino.exists():
                destino.unlink()
            subprocess.run([winrar, "a", "-m0", "-ep1", "-idq", str(destino)]
                           + [str(sueltas / nombre) for nombre, _d in paginas],
                           check=False)
            if destino.is_file():
                salidos.append(destino)
    return salidos


def _siete_zip() -> str:
    """El 7-Zip que viaja con el programa, o el que haya en el equipo."""
    propio = RAIZ / "data" / "bin" / "7z.exe"
    if propio.is_file():
        return str(propio)
    return shutil.which("7z") or shutil.which("7za") or ""


def _winrar() -> str:
    """El WinRAR de quien lo tenga. Sin él no se puede escribir un RAR."""
    for candidato in (r"C:{sep}Program Files{sep}WinRAR{sep}Rar.exe".format(sep=chr(92)),
                      r"C:{sep}Program Files (x86){sep}WinRAR{sep}Rar.exe".format(sep=chr(92))):
        if Path(candidato).is_file():
            return candidato
    return shutil.which("rar") or ""


# ---------------------------------------------------------------------------
# Correo guardado
# ---------------------------------------------------------------------------

def hacer_correo(carpeta: Path) -> list:
    """Un mensaje con su cuerpo en HTML, y la misma página como «.mht»."""
    from email.message import EmailMessage

    mensaje = EmailMessage()
    mensaje["Subject"] = TITULO
    mensaje["From"] = "Naturaleza <naturaleza@ejemplo.es>"
    mensaje["To"] = "quien lee <lector@ejemplo.es>"
    mensaje["Date"] = "Mon, 01 Jun 2026 09:15:00 +0200"
    mensaje.set_content(texto_plano())
    mensaje.add_alternative(pagina_html(), subtype="html")
    eml = escribir(carpeta / "vencejo.eml", mensaje.as_bytes())

    # Un «.mht» es una página web guardada como mensaje MIME: la propia página
    # y, en partes aparte, lo que llevara dentro.
    limite = "----=_Parte_Vencejo"
    partes = ["MIME-Version: 1.0",
              'Content-Type: multipart/related; boundary="%s"' % limite,
              "Subject: %s" % TITULO, "", "--" + limite,
              "Content-Type: text/html; charset=utf-8",
              "Content-Transfer-Encoding: 8bit",
              "Content-Location: https://ejemplo.es/vencejo.html", "",
              pagina_html().replace(
                  "</body>",
                  '<p><img src="vencejo.png" alt="Un vencejo en vuelo, visto '
                  'desde abajo."/></p></body>'),
              "--" + limite,
              "Content-Type: image/png",
              "Content-Transfer-Encoding: base64",
              "Content-Location: https://ejemplo.es/vencejo.png", "",
              base64.encodebytes(imagen_png(2)).decode("ascii"),
              "--" + limite + "--", ""]
    contenido = chr(10).join(partes)
    return [eml,
            escribir(carpeta / "vencejo.mht", contenido),
            escribir(carpeta / "vencejo.mhtml", contenido)]


# ---------------------------------------------------------------------------
# Música y braille
# ---------------------------------------------------------------------------

def hacer_musica(carpeta: Path) -> list:
    """Una partitura corta con acordes, matices y dos voces."""
    def nota(paso, octava, figura, extra=""):
        return ("<note><pitch><step>%s</step><octave>%d</octave></pitch>"
                "<duration>1</duration><voice>1</voice><type>%s</type>%s"
                "</note>" % (paso, octava, figura, extra))

    compases = []
    compases.append(
        '<measure number="1"><attributes><divisions>1</divisions>'
        "<key><fifths>0</fifths></key>"
        "<time><beats>4</beats><beat-type>4</beat-type></time>"
        "<clef><sign>G</sign><line>2</line></clef></attributes>"
        '<direction placement="below"><direction-type><dynamics><p/>'
        "</dynamics></direction-type></direction>"
        + nota("C", 4, "quarter",
               "<notations><articulations><staccato/></articulations>"
               "<technical><fingering>1</fingering></technical></notations>")
        + nota("E", 4, "quarter", "<chord/>".join(["", ""]))
        + nota("G", 4, "quarter")
        + nota("A", 4, "quarter")
        + "</measure>")
    compases.append(
        '<measure number="2">'
        + nota("C", 5, "half", '<notations><slur type="start"/></notations>')
        + nota("B", 4, "half", '<notations><slur type="stop"/></notations>')
        + "</measure>")
    xml = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 '
           'Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">'
           '<score-partwise version="4.0"><work><work-title>%s</work-title>'
           "</work><identification><creator type=\"composer\">%s</creator>"
           "</identification><part-list><score-part id=\"P1\">"
           "<part-name>Flauta</part-name></score-part></part-list>"
           '<part id="P1">%s</part></score-partwise>'
           % (TITULO, AUTOR, "".join(compases)))
    musicxml = escribir(carpeta / "vencejo.musicxml", xml)
    mxl = carpeta / "vencejo.mxl"
    with zipfile.ZipFile(mxl, "w", zipfile.ZIP_DEFLATED) as paquete:
        paquete.writestr("META-INF/container.xml",
                         '<?xml version="1.0" encoding="UTF-8"?><container>'
                         '<rootfiles><rootfile full-path="vencejo.musicxml" '
                         'media-type="application/vnd.recordare.musicxml+xml"/>'
                         "</rootfiles></container>")
        paquete.writestr("vencejo.musicxml", xml)
    return [musicxml, mxl]


def hacer_braille(carpeta: Path) -> list:
    """El mismo texto en un archivo «.bra» de los de la ONCE.

    Un `.bra` **no es un BRF**, aunque los dos sean braille en ocho bits: usan
    tablas distintas.  En el BRF las letras van en mayúsculas y el signo de
    mayúscula es un punto; en el BRA las letras van en minúsculas, el signo de
    mayúscula es ``{`` y el de número, ``#``.

    Así que el archivo se escribe **invirtiendo la propia tabla del lector**.
    Es la única manera de que la muestra sirva para lo que tiene que servir: si
    se escribiera con otra convención, abrirla daría un texto en mayúsculas y
    con los acentos rotos, y parecería un fallo del programa.
    """
    sys.path.insert(0, str(RAIZ / "src"))
    from formatos import braille as lector

    tabla = lector._TABLA_BRA_A_CP1252
    # De carácter en tinta a byte del archivo: la vuelta de la tabla que usa el
    # lector. Se recorre al revés para que, cuando dos bytes den la misma letra,
    # mande el primero, que es el corriente.
    inverso = {}
    for byte in range(255, -1, -1):
        inverso[bytes([tabla[byte]]).decode("cp1252", "replace")] = byte

    cifras = {cifra: letra for letra, cifra in zip("abcdefghij", "1234567890")}

    def renglon(texto: str) -> bytes:
        salida = bytearray()
        numero = False
        for letra in texto:
            if letra in cifras:
                if not numero:
                    salida.append(inverso["#"])
                    numero = True
                salida.append(inverso[cifras[letra]])
                continue
            numero = False
            if letra.isupper():
                salida.append(inverso["{"])
                letra = letra.lower()
            byte = inverso.get(letra)
            if byte is None:
                byte = inverso.get(" ", 32)
            salida.append(byte)
        return bytes(salida)

    lineas = [renglon(texto) for texto
              in texto_plano(encabezados_en_mayusculas=False).split(chr(10))]
    # Los archivos braille separan las líneas como los archivos de MS-DOS, que
    # es lo que espera una impresora braille y un anotador.
    fin_de_linea = bytes([13, 10])
    return [escribir(carpeta / "vencejo.bra",
                     fin_de_linea.join(lineas) + fin_de_linea)]


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

def hacer_pdf(carpeta: Path) -> list:
    """Un PDF de dos páginas, escrito byte a byte.

    Va sin etiquetar a propósito: es lo que es la inmensa mayoría de los PDF que
    circulan, y por tanto lo que hay que poder comprobar. El programa deduce sus
    encabezados midiendo el tamaño de la letra, así que los títulos van en un
    cuerpo mayor —que es justo el dato del que salen—.
    """
    def escapar_pdf(texto: str) -> str:
        salida = []
        for letra in texto:
            if letra in "()" + chr(92):
                salida.append(chr(92) + letra)
            elif ord(letra) < 128:
                salida.append(letra)
            else:
                # WinAnsi cubre el español; lo que no quepa se deja fuera antes
                # que meter un byte que el lector interprete como otra cosa.
                crudo = letra.encode("cp1252", "replace")
                salida.append(chr(92) + "%03o" % crudo[0])
        return "".join(salida)

    def pagina(renglones) -> bytes:
        partes = ["BT", "/F1 11 Tf", "14 TL", "1 0 0 1 60 760 Tm"]
        for cuerpo, texto in renglones:
            partes.append("/F%d %d Tf" % (1 if cuerpo <= 12 else 2, cuerpo))
            partes.append("%d TL" % (cuerpo + 4))
            partes.append("(%s) Tj T*" % escapar_pdf(texto))
        partes.append("ET")
        return "\n".join(partes).encode("cp1252", "replace")

    def cortar(texto: str, ancho: int = 78):
        renglones, actual = [], ""
        for palabra in texto.split():
            if len(actual) + len(palabra) + 1 > ancho:
                renglones.append(actual)
                actual = palabra
            else:
                actual = (actual + " " + palabra).strip()
        if actual:
            renglones.append(actual)
        return renglones

    primera = [(20, TITULO), (11, AUTOR), (11, "")]
    segunda = []
    for numero, (encabezado, parrafos) in enumerate(APARTADOS):
        destino = primera if numero == 0 else segunda
        destino.append((16, encabezado))
        for parrafo in parrafos:
            destino.extend((11, renglon) for renglon in cortar(parrafo))
        destino.append((11, ""))
        if numero == 1:
            destino.extend((11, "  - " + punto) for punto in LISTA)
            destino.append((11, ""))
        if numero == 2:
            for fila in TABLA:
                destino.append((11, "  %-16s %-14s %s" % tuple(fila)))
            destino.append((11, ""))
            destino.extend((11, renglon) for renglon in cortar("«%s»" % CITA))

    contenidos = [pagina(primera), pagina(segunda)]
    objetos = []
    objetos.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objetos.append(("<< /Type /Pages /Kids [%s] /Count %d >>"
                    % (" ".join("%d 0 R" % (3 + numero)
                                for numero in range(len(contenidos))),
                       len(contenidos))).encode("ascii"))
    for numero in range(len(contenidos)):
        objetos.append(("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
                        "/Resources << /Font << /F1 %d 0 R /F2 %d 0 R >> >> "
                        "/Contents %d 0 R >>"
                        % (3 + len(contenidos), 4 + len(contenidos),
                           3 + len(contenidos) + 2 + numero)).encode("ascii"))
    objetos.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
                   b"/Encoding /WinAnsiEncoding >>")
    objetos.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold "
                   b"/Encoding /WinAnsiEncoding >>")
    for contenido in contenidos:
        objetos.append(("<< /Length %d >>\nstream\n" % len(contenido)).encode("ascii")
                       + contenido + b"\nendstream")

    salida = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    posiciones = []
    for numero, cuerpo in enumerate(objetos, start=1):
        posiciones.append(len(salida))
        salida += ("%d 0 obj\n" % numero).encode("ascii") + cuerpo + b"\nendobj\n"
    inicio_tabla = len(salida)
    salida += ("xref\n0 %d\n" % (len(objetos) + 1)).encode("ascii")
    salida += b"0000000000 65535 f \n"
    for posicion in posiciones:
        salida += ("%010d 00000 n \n" % posicion).encode("ascii")
    salida += ("trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
               % (len(objetos) + 1, inicio_tabla)).encode("ascii")
    return [escribir(carpeta / "vencejo.pdf", bytes(salida))]


# ---------------------------------------------------------------------------
# DAISY
# ---------------------------------------------------------------------------

def hacer_daisy(carpeta: Path) -> list:
    """Un libro DAISY 3 de solo texto, con su índice navegable.

    Es el formato de las bibliotecas para personas ciegas. Va sin grabación:
    con texto basta para comprobar que la navegación por niveles funciona, que
    es lo propio del formato.
    """
    libro = carpeta / "vencejo_daisy"
    libro.mkdir(parents=True, exist_ok=True)
    puntos = []
    cuerpo = []
    for numero, (encabezado, parrafos) in enumerate(APARTADOS, start=1):
        identificador = "nivel%d" % numero
        puntos.append((identificador, encabezado))
        trozos = ['<h1 id="%s">%s</h1>' % (identificador, encabezado)]
        trozos.extend("<p>%s</p>" % parrafo for parrafo in parrafos)
        if numero == 2:
            trozos.append("<ul>%s</ul>"
                          % "".join("<li>%s</li>" % punto for punto in LISTA))
        if numero == 3:
            trozos.append("<blockquote><p>%s</p></blockquote>" % CITA)
        cuerpo.append('<level1 class="section">%s</level1>' % "".join(trozos))

    escribir(libro / "vencejo.xml",
             '<?xml version="1.0" encoding="utf-8"?>'
             '<!DOCTYPE dtbook PUBLIC "-//NISO//DTD dtbook 2005-3//EN" '
             '"http://www.daisy.org/z3986/2005/dtbook-2005-3.dtd">'
             '<dtbook xmlns="http://www.daisy.org/z3986/2005/dtbook/" '
             'version="2005-3" xml:lang="es"><head/><book>'
             "<frontmatter><doctitle>%s</doctitle><docauthor>%s</docauthor>"
             "</frontmatter><bodymatter>%s</bodymatter></book></dtbook>"
             % (TITULO, AUTOR, "".join(cuerpo)))

    puntos_xml = "".join(
        '<navPoint id="np%d" playOrder="%d"><navLabel><text>%s</text>'
        '</navLabel><content src="vencejo.xml#%s"/></navPoint>'
        % (numero, numero, titulo, identificador)
        for numero, (identificador, titulo) in enumerate(puntos, start=1))
    escribir(libro / "vencejo.ncx",
             '<?xml version="1.0" encoding="utf-8"?>'
             '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1" '
             'xml:lang="es"><head>'
             '<meta name="dtb:uid" content="visor-muestra-vencejo"/>'
             '<meta name="dtb:depth" content="1"/>'
             "</head><docTitle><text>%s</text></docTitle>"
             "<docAuthor><text>%s</text></docAuthor>"
             "<navMap>%s</navMap></ncx>" % (TITULO, AUTOR, puntos_xml))

    escribir(libro / "vencejo.opf",
             '<?xml version="1.0" encoding="utf-8"?>'
             '<package xmlns="http://openebook.org/namespaces/oeb-package/1.0/" '
             'unique-identifier="uid"><metadata><dc-metadata '
             'xmlns:dc="http://purl.org/dc/elements/1.1/">'
             "<dc:Title>%s</dc:Title><dc:Creator>%s</dc:Creator>"
             "<dc:Language>es</dc:Language>"
             '<dc:Identifier id="uid">visor-muestra-vencejo</dc:Identifier>'
             "</dc-metadata><x-metadata>"
             '<meta name="dtb:multimediaType" content="textNCX"/>'
             "</x-metadata></metadata><manifest>"
             '<item id="opf" href="vencejo.opf" media-type="text/xml"/>'
             '<item id="ncx" href="vencejo.ncx" media-type="application/x-dtbncx+xml"/>'
             '<item id="dtb" href="vencejo.xml" media-type="application/x-dtbook+xml"/>'
             '</manifest><spine><itemref idref="dtb"/></spine></package>'
             % (TITULO, AUTOR))
    # Algunos programas nombran el paquete con la extensión «.daisy». Es el
    # mismo archivo, y tener una copia deja comprobar que el programa lo
    # reconoce por lo que hay alrededor y no solo por cómo se llame.
    shutil.copy2(libro / "vencejo.opf", libro / "vencejo.daisy")
    return [libro / "vencejo.opf", libro / "vencejo.ncx",
            libro / "vencejo.daisy"]


# ---------------------------------------------------------------------------
# Kindle
# ---------------------------------------------------------------------------

def hacer_mobi(carpeta: Path) -> list:
    """Un MOBI de los antiguos, sin comprimir y sin protección.

    Un MOBI es **una base de datos de Palm** —de las de la agenda de 1998— con
    el libro dentro, partido en registros de cuatro kilobytes. Lo que hace falta
    entender es su cabecera: treinta y dos bytes de nombre, unos cuantos campos,
    el tipo (``BOOK``) y el creador (``MOBI``), cuántos registros hay y, para
    cada uno, en qué byte del archivo empieza.

    Se escribe **sin comprimir** porque lo que se quiere comprobar es que se
    abre y se lee, y porque así el archivo se puede mirar por dentro con
    cualquier editor.

    Los formatos nuevos de Kindle —AZW3 y KFX— no se generan: llevan dentro otra
    cosa completamente distinta y escribirlos sería un proyecto aparte. El
    programa sí los abre.
    """
    # En UTF-8, que es lo que la cabecera va a declarar: escribir en Latin-1 y
    # decir que es UTF-8 deja el libro lleno de interrogantes donde había tildes.
    texto = ("<html><body>" + cuerpo_html() + "</body></html>").encode("utf-8")
    trozo = 4096
    registros = [texto[inicio:inicio + trozo]
                 for inicio in range(0, len(texto), trozo)] or [b" "]

    titulo = TITULO.encode("utf-8")
    # Cabecera de PalmDoc: cómo está comprimido (1 = nada), cuánto ocupa el
    # texto entero, cuántos registros lo llevan y de qué tamaño.
    palmdoc = struct.pack(">HHIHHHH", 1, 0, len(texto), len(registros),
                          trozo, 0, 0)
    mobi = bytearray()
    mobi += struct.pack(">4sII", b"MOBI", 232, 2)      # marca, longitud, tipo
    mobi += struct.pack(">II", 65001, 0)               # UTF-8 y número único
    mobi += struct.pack(">I", 6)                       # versión del formato
    mobi += b"\xff" * 40                               # índices que no se usan
    mobi += struct.pack(">I", len(registros) + 1)      # primer registro no textual
    mobi += struct.pack(">I", 0)
    mobi += struct.pack(">II", len(palmdoc) + 232, len(titulo))  # dónde va el título
    mobi += struct.pack(">I", 0x0409)                  # idioma
    mobi += bytes(232 - len(mobi))
    cabecera = palmdoc + bytes(mobi) + titulo
    cabecera += bytes((4 - len(cabecera) % 4) % 4)

    todos = [cabecera] + registros

    # La cabecera de la base de datos: los primeros 78 bytes son fijos y el
    # último campo es cuántos registros vienen. Se escribe **una sola vez**;
    # duplicarlo desplaza toda la lista y el libro deja de abrirse.
    salida = bytearray(b"El vencejo".ljust(32, b"\x00"))
    salida += struct.pack(">HH", 0, 0)                 # atributos y versión
    salida += struct.pack(">III", 0, 0, 0)             # las tres fechas
    salida += struct.pack(">III", 0, 0, 0)             # modificación e info
    salida += b"BOOKMOBI"
    salida += struct.pack(">II", 0, 0)                 # semilla y siguiente lista
    salida += struct.pack(">H", len(todos))
    inicio = len(salida) + 8 * len(todos) + 2
    for numero, registro in enumerate(todos):
        salida += struct.pack(">IBBH", inicio, 0, 0, numero)
        inicio += len(registro)
    salida += b"\x00\x00"
    for registro in todos:
        salida += registro
    datos = bytes(salida)
    return [escribir(carpeta / "vencejo.mobi", datos),
            escribir(carpeta / "vencejo.prc", datos),
            escribir(carpeta / "vencejo.azw", datos)]


# ---------------------------------------------------------------------------
# Las extensiones que son el mismo formato con otro nombre
# ---------------------------------------------------------------------------

#: Cada entrada dice: de qué archivo se copia, con qué extensión nueva y por
#: qué. Son plantillas y variantes: por dentro son idénticas al original, y sin
#: una muestra de cada una nadie comprueba nunca que el programa las reparte
#: bien.
ALIAS = [
    ("04_ofimatica/vencejo.odt", ".ott", "plantilla de documento"),
    ("06_presentaciones/vencejo.odp", ".otp", "plantilla de presentación"),
    ("07_hojas/vencejo.ods", ".ots", "plantilla de hoja de cálculo"),
    ("05_ofimatica_antigua/harmless-clean.doc", ".dot", "plantilla de Word 97"),
    ("05_ofimatica_antigua/ragged.xls", ".xlt", "plantilla de Excel 97"),
    ("05_ofimatica_antigua/presentacion.ppt", ".pot", "plantilla de PowerPoint"),
    ("05_ofimatica_antigua/presentacion.ppt", ".pps",
     "presentación que se abre ya en marcha"),
    ("09_escaneos/muestra.djvu", ".djv", "la misma extensión, acortada"),
]


def hacer_alias(raiz: Path) -> list:
    """Copia cada muestra con las extensiones que son ese mismo formato."""
    salidos = []
    for relativa, extension, _explicacion in ALIAS:
        origen = raiz / relativa
        if not origen.is_file():
            continue
        destino = origen.with_suffix(extension)
        shutil.copy2(origen, destino)
        salidos.append(destino)
    return salidos


# ---------------------------------------------------------------------------
# Lo que se copia, porque no se puede fabricar aquí
# ---------------------------------------------------------------------------

#: Muestras de verdad que ya están en «adjuntos» y de dónde salen. Se copian en
#: vez de fabricarse porque su formato solo lo escribe el programa que lo
#: inventó: un `.doc` de Word, un `.hlp` de un compilador de ayuda de 1993 y un
#: `.chm` de HTML Help Workshop.
COPIAS = [
    ("05_ofimatica_antigua/harmless-clean.doc",
     "Estudio/oletools/tests/test-data/msodde/harmless-clean.doc",
     "Documento de Word 97 de las pruebas de oletools."),
    ("05_ofimatica_antigua/ragged.xls",
     "Estudio/xlrd/tests/samples/ragged.xls",
     "Libro de Excel 97 de las pruebas de xlrd, con filas de distinta longitud."),
    ("05_ofimatica_antigua/presentacion.ppt",
     "Estudio/oletools/tests/test-data/oleobj/embedded-simple-2007.ppt",
     "Presentación de PowerPoint 97 de las pruebas de oletools."),
    ("09_escaneos/muestra.djvu", None,
     "Escaneo en DjVu con su capa de texto."),
    ("12_ayuda/ayuda_windows.hlp", "Estudio/muestras/ayuda_windows.hlp",
     "Archivo de ayuda de Windows 3.1 sin comprimir."),
    ("12_ayuda/ayuda_faq.hlp", "Estudio/muestras/ayuda_faq.hlp",
     "Archivo de ayuda comprimido y con tabla de frases."),
    ("12_ayuda/7-zip.chm", None,
     "Manual de 7-Zip en CHM, el formato que sustituyó al «.hlp»."),
]


def hacer_djvu_sin_texto(raiz: Path) -> list:
    """El mismo escaneo, pero sin la capa de texto que trae dentro.

    Es el caso que de verdad cuesta: la mayoría de los DjVu llevan el texto que
    se reconoció al digitalizarlos, y de ahí se leen.  El que no lo lleva hay
    que reconocerlo aquí, descomprimiendo antes su capa en blanco y negro.

    Se deriva del otro en vez de traer un archivo distinto: los dos dicen lo
    mismo, así que lo único que cambia entre ellos es lo que se quiere probar.
    Los trozos de texto no se borran —eso movería todo lo demás de sitio—: se
    les cambia el nombre a ``FREE``, que es como el propio formato marca lo que
    hay que saltarse.
    """
    from formatos.djvu import trozos

    origen = raiz / "09_escaneos" / "muestra.djvu"
    if not origen.is_file():
        return []
    datos = bytearray(origen.read_bytes())
    for envoltorio in trozos(bytes(datos), 16, len(datos)):
        if envoltorio.nombre != b"FORM":
            continue
        for interno in trozos(bytes(datos), envoltorio.inicio + 4,
                              envoltorio.inicio + envoltorio.largo):
            if interno.nombre in (b"TXTz", b"TXTa"):
                datos[interno.inicio - 8:interno.inicio - 4] = b"FREE"
    destino = origen.with_name("muestra_sin_texto.djvu")
    destino.write_bytes(bytes(datos))
    return [destino]


def copiar_muestras(raiz: Path) -> list:
    """Trae las muestras que no se pueden fabricar. Dice cuáles ha encontrado."""
    salidos = []
    for relativa, origen, _explicacion in COPIAS:
        destino = raiz / relativa
        candidatos = []
        if origen:
            candidatos.append(RAIZ / "adjuntos" / origen)
        # Las que no dicen de dónde salen se buscan por su nombre.
        candidatos.append(RAIZ / "pruebas" / "datos" / destino.name)
        candidatos.extend((RAIZ / "adjuntos").rglob(destino.name))
        for candidato in candidatos:
            if candidato.is_file():
                destino.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(candidato, destino)
                salidos.append(destino)
                break
    return salidos


# ---------------------------------------------------------------------------
# Montarlo todo
# ---------------------------------------------------------------------------

CARPETAS = [
    ("01_libros", "Libros electrónicos", ["hacer_epub", "hacer_fb2", "hacer_mobi"]),
    ("02_texto", "Texto plano y Markdown", ["hacer_texto"]),
    ("03_web", "Páginas web", ["hacer_web"]),
    ("04_ofimatica", "Documentos de ofimática", ["hacer_docx", "hacer_odt",
                                                 "hacer_rtf"]),
    ("05_ofimatica_antigua", "Office 97: los formatos binarios", []),
    ("06_presentaciones", "Presentaciones", ["hacer_pptx", "hacer_odp"]),
    ("07_hojas", "Hojas de cálculo", ["hacer_xlsx", "hacer_ods"]),
    ("08_pdf", "PDF", ["hacer_pdf"]),
    ("09_escaneos", "Escaneos de biblioteca", []),
    ("10_comics", "Cómics", ["hacer_comics"]),
    ("11_correo", "Correo y páginas guardadas", ["hacer_correo"]),
    ("12_ayuda", "Archivos de ayuda de Windows", []),
    ("13_daisy", "Libros DAISY", ["hacer_daisy"]),
    ("14_musica", "Partituras", ["hacer_musica"]),
    ("15_braille", "Braille", ["hacer_braille"]),
]


def main() -> int:
    if DESTINO.exists():
        shutil.rmtree(DESTINO)
    DESTINO.mkdir(parents=True)

    generados = []
    for nombre, titulo, funciones in CARPETAS:
        carpeta = DESTINO / nombre
        carpeta.mkdir(parents=True, exist_ok=True)
        for funcion in funciones:
            try:
                salidos = globals()[funcion](carpeta)
            except Exception as error:
                print("   %-22s FALLO: %s" % (funcion, error))
                continue
            generados.extend(salidos)
        del titulo
    copiados = copiar_muestras(DESTINO)
    # Después de copiar y antes de los alias: el DjVu sin texto sale del que se
    # acaba de traer, y el alias «.djv» se saca del que sí lo trae.
    copiados.extend(hacer_djvu_sin_texto(DESTINO))
    copiados.extend(hacer_alias(DESTINO))

    escribir(DESTINO / "LEEME.md", leeme(generados, copiados))
    print("Documentos de muestra en %s" % DESTINO)
    print("   generados: %d   copiados: %d" % (len(generados), len(copiados)))
    for archivo in sorted(generados + copiados):
        print("   %-46s %8.1f KB"
              % (archivo.relative_to(DESTINO), archivo.stat().st_size / 1024))
    return 0


def leeme(generados, copiados) -> str:
    """El LEEME que acompaña a la carpeta."""
    lineas = ["# Documentos de muestra", "",
              "Un documento de **cada formato que el programa abre**, repartido "
              "por carpetas.", "",
              "Todos dicen lo mismo —el mismo título, los mismos apartados, la "
              "misma lista, la misma tabla y la misma cita—, así que lo que "
              "cambie de uno a otro es cosa del formato y no del contenido. "
              "Eso es lo que los hace útiles para comprobar que nada se ha "
              "estropeado.", "",
              "Se rehacen con:", "",
              "```bash", "python herramientas/documentos_muestra.py", "```", "",
              "## Qué hay en cada carpeta", ""]
    for nombre, titulo, _funciones in CARPETAS:
        carpeta = DESTINO / nombre
        archivos = sorted(hijo.name for hijo in carpeta.rglob("*")
                          if hijo.is_file())
        if not archivos:
            continue
        lineas.append("**`%s` — %s**" % (nombre, titulo))
        lineas.append("")
        lineas.append("- " + ", ".join("`%s`" % archivo for archivo in archivos))
        lineas.append("")
    lineas.extend([
        "## Lo que se fabrica y lo que se copia", "",
        "Casi todo se escribe byte a byte desde "
        "`herramientas/documentos_muestra.py`: los ZIP con XML dentro, el PDF, "
        "el MOBI, el correo, el DAISY y el braille. Salen en español y con el "
        "mismo texto.", "",
        "Hay formatos que **no se pueden fabricar** sin el programa que los "
        "inventó, y para esos se copia una muestra de verdad:", ""])
    for relativa, _origen, explicacion in COPIAS:
        if (DESTINO / relativa).is_file():
            lineas.append("- `%s` — %s" % (relativa, explicacion))
    lineas.extend(["", "## El mismo formato con otro nombre", "",
                   "Hay extensiones que son el mismo archivo por dentro —las "
                   "plantillas, sobre todo—. Están copiadas para poder "
                   "comprobar que el programa las reparte bien:", ""])
    for relativa, extension, explicacion in ALIAS:
        if (DESTINO / relativa).with_suffix(extension).is_file():
            lineas.append("- `%s` — %s"
                          % (Path(relativa).with_suffix(extension).name,
                             explicacion))
    lineas.extend([
        "", "## Lo que no está, y por qué", "",
        "- **AZW3, AZW4, AZW8, KFX y KFX-ZIP**, los formatos nuevos de Kindle. "
        "El programa los abre, pero escribirlos es otro proyecto: llevan dentro "
        "un formato distinto del MOBI, con su propio índice y su propia "
        "compresión. Sí hay un MOBI, que es el mismo envoltorio y se abre por "
        "el mismo camino, y está copiado también como `.azw` y como `.prc`.",
        "- **Un DjVu hecho aquí.** El que hay es una muestra de verdad. "
        "Escribir un DjVu exige codificar en JB2 y en ondículas, que es "
        "justamente lo que el programa no hace: solo lee su capa de texto.", "",
        "Si tienes un `.azw3` o un `.kfx` **sin protección anticopia**, déjalo "
        "en `01_libros` y la colección quedará completa. El programa los abre; "
        "lo que no sabe es fabricarlos.", "",
        "## Cuidado con una cosa", "",
        "Estos archivos son **de muestra**, no de referencia: si uno de ellos "
        "no se abre, lo primero que hay que mirar es si el archivo está bien "
        "hecho. Para comprobar el programa contra archivos de verdad están las "
        "pruebas, que usan muestras de terceros.", ""])
    return "\n".join(lineas)


if __name__ == "__main__":
    raise SystemExit(main())
