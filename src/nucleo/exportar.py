# -*- coding: utf-8 -*-
"""Guardar el documento abierto en otros formatos.

Sacar el texto de un documento sirve para más cosas de las que parece: pasarlo
al móvil, mandárselo a alguien, meterlo en una libreta de notas, imprimirlo en
braille o abrirlo con otro programa.  Y cada uno de esos destinos quiere un
formato distinto, así que exportar solo a texto plano se queda corto.

Aquí están los formatos a los que se exporta, todos escritos con la biblioteca
estándar salvo el EPUB, que es un ZIP y también:

=========  =====================================================
Formato    Para qué
=========  =====================================================
TXT        Lo universal.  Cualquier programa lo abre.
Markdown   Conserva los encabezados y las listas, y se sigue
           leyendo como texto plano.
HTML       Se abre en el navegador con su índice y sus enlaces.
EPUB       Para leerlo en un lector de libros o en el móvil.
=========  =====================================================

Los cuatro conservan la **estructura** —encabezados, listas, tablas— porque es
lo que permite seguir navegando el documento después de exportarlo.  Un volcado
de texto corrido pierde justo lo que hace que un documento largo se pueda usar.
"""

from __future__ import annotations

import html as _html
import zipfile
from pathlib import Path

from .documento import Documento
from .idioma import _
from .marcas import TipoMarca
from .registro import obtener_registro

log = obtener_registro(__name__)

#: Formatos a los que se puede exportar, con su extensión y su descripción.
#: El orden es el del menú: de lo más sencillo a lo más elaborado.
FORMATOS = ("txt", "md", "html", "epub", "brf", "pef")


def nombres() -> dict[str, tuple[str, str, str]]:
    """``{clave: (nombre de menú, extensión, filtro del diálogo)}``."""
    return {
        "txt": (_("Texto plano (.txt)"), ".txt",
                _("Archivos de texto (*.txt)|*.txt")),
        "md": (_("Markdown (.md)"), ".md",
               _("Archivos Markdown (*.md)|*.md")),
        "html": (_("Página web (.html)"), ".html",
                 _("Páginas web (*.html)|*.html")),
        "epub": (_("Libro electrónico (.epub)"), ".epub",
                 _("Libros EPUB (*.epub)|*.epub")),
        "brf": (_("Braille (.brf)"), ".brf",
                _("Archivos braille (*.brf)|*.brf")),
        "pef": (_("Braille en XML (.pef)"), ".pef",
                _("Braille PEF (*.pef)|*.pef")),
    }


def _nivel(tipo: TipoMarca) -> int:
    """Nivel de un encabezado, o 0 si la marca no lo es."""
    return {
        TipoMarca.ENCABEZADO1: 1, TipoMarca.ENCABEZADO2: 2, TipoMarca.ENCABEZADO3: 3,
        TipoMarca.ENCABEZADO4: 4, TipoMarca.ENCABEZADO5: 5, TipoMarca.ENCABEZADO6: 6,
    }.get(tipo, 0)


def _lineas_con_estructura(documento: Documento):
    """Recorre el documento devolviendo ``(clase, texto)`` por cada línea.

    La clase es ``h1``…``h6`` para los encabezados y ``p`` para lo demás.  Se
    saca de las marcas y no del texto porque el texto ya está aplanado: sin
    esto no habría forma de saber qué línea era un título.
    """
    encabezados = {}
    for marca in documento.marcas.todas():
        nivel = _nivel(marca.tipo)
        if nivel:
            encabezados[documento.linea_de(marca.posicion)] = nivel
    for numero, linea in enumerate(documento.texto.split("\n")):
        texto = linea.strip()
        if not texto:
            continue
        nivel = encabezados.get(numero, 0)
        yield ("h%d" % nivel if nivel else "p"), texto


def a_txt(documento: Documento) -> bytes:
    """Texto plano, tal cual, con los saltos de línea de Windows."""
    return documento.texto.replace("\n", "\r\n").encode("utf-8")


def a_markdown(documento: Documento) -> bytes:
    """Markdown, con los encabezados marcados con almohadillas."""
    partes = []
    metadatos = documento.metadatos
    if metadatos.titulo:
        partes.append("# %s\n" % metadatos.titulo)
    if metadatos.autor:
        partes.append("*%s*\n" % metadatos.autor)
    for clase, texto in _lineas_con_estructura(documento):
        if clase.startswith("h"):
            partes.append("\n%s %s\n" % ("#" * int(clase[1]), texto))
        else:
            partes.append("%s\n" % texto)
    return "\n".join(partes).encode("utf-8")


def _cuerpo_html(documento: Documento) -> str:
    """El documento como una sucesión de etiquetas HTML."""
    partes = []
    for clase, texto in _lineas_con_estructura(documento):
        escapado = _html.escape(texto)
        if clase.startswith("h"):
            partes.append("<%s>%s</%s>" % (clase, escapado, clase))
        else:
            partes.append("<p>%s</p>" % escapado)
    return "\n".join(partes)


def a_html(documento: Documento) -> bytes:
    """Página web con su título, su autor y sus encabezados."""
    metadatos = documento.metadatos
    titulo = _html.escape(metadatos.titulo or Path(documento.ruta_archivo).stem)
    cabecera = "<h1>%s</h1>" % titulo
    if metadatos.autor:
        cabecera += "\n<p><em>%s</em></p>" % _html.escape(metadatos.autor)
    return ("<!DOCTYPE html>\n"
            '<html lang="%s"><head><meta charset="utf-8">\n'
            "<title>%s</title>\n"
            "<style>body{font-family:sans-serif;max-width:40em;margin:2em auto;"
            "line-height:1.5;padding:0 1em}</style>\n"
            "</head><body>\n%s\n%s\n</body></html>\n"
            % (metadatos.idioma or "es", titulo, cabecera,
               _cuerpo_html(documento))).encode("utf-8")


#: Dirección de la norma de accesibilidad de EPUB que se declara cumplir.
#: Es lo que la ley europea de accesibilidad pide desde junio de 2025, y lo que
#: hace que una librería o un lector sepan **antes de abrir el libro** qué trae.
CONFORMIDAD = "http://www.idpf.org/epub/a11y/accessibility-20170105.html#wcag-aa"


def _metadatos_de_accesibilidad(documento: Documento) -> str:
    """Escribe lo que el libro trae para poder leerse, en el lenguaje de la norma.

    No se declara nada que no sea verdad: cada rasgo se pone **solo si el
    documento lo tiene de verdad**, comprobándolo sobre sus marcas.  Un libro
    que dijera traer descripciones de imágenes sin traerlas sería peor que uno
    que no dijera nada: quien lo busque por eso se lo llevaría a casa creyendo
    que puede leerlo.
    """
    marcas = documento.marcas
    imagenes = (marcas.cantidad(TipoMarca.IMAGEN) + marcas.cantidad(TipoMarca.FIGURA))
    sin_describir = 0
    for tipo in (TipoMarca.IMAGEN, TipoMarca.FIGURA):
        for marca in marcas.grupo(tipo).marcas:
            if not (marca.texto or "").strip():
                sin_describir += 1
    rasgos = ["readingOrder"]
    if marcas.encabezados.marcas:
        rasgos.append("structuralNavigation")
    if documento.indice:
        rasgos.append("tableOfContents")
    if imagenes and not sin_describir:
        rasgos.append("alternativeText")
    if marcas.cantidad(TipoMarca.SALTO_PAGINA):
        rasgos.append("printPageNumbers")
    if marcas.cantidad(TipoMarca.FORMULA):
        rasgos.append("MathML")
    if marcas.cantidad(TipoMarca.TABLA):
        rasgos.append("tableStructure")

    modos = ["textual"] + (["visual"] if imagenes else [])
    partes = ['<meta property="schema:accessMode">%s</meta>' % modo for modo in modos]
    # Con el texto solo ya se puede leer el libro entero: eso es lo que dice
    # «accessModeSufficient», y es el dato que de verdad busca quien no ve.
    partes.append('<meta property="schema:accessModeSufficient">textual</meta>')
    partes += ['<meta property="schema:accessibilityFeature">%s</meta>' % rasgo
               for rasgo in rasgos]
    # Los peligros se declaran como «ninguno conocido» y no como «ninguno»: el
    # programa no puede saber si el original tenía destellos.
    for peligro in ("noFlashingHazard", "noSoundHazard", "noMotionSimulationHazard"):
        partes.append('<meta property="schema:accessibilityHazard">%s</meta>' % peligro)
    partes.append('<meta property="schema:accessibilitySummary">%s</meta>'
                  % _html.escape(_resumen_de_accesibilidad(documento, imagenes,
                                                           sin_describir)))
    partes.append('<link rel="dcterms:conformsTo" href="%s"/>' % CONFORMIDAD)
    return "\n".join(partes)


def _resumen_de_accesibilidad(documento: Documento, imagenes: int,
                              sin_describir: int) -> str:
    """La frase que explica a una persona qué se puede hacer con este libro."""
    piezas = []
    encabezados = len(documento.marcas.encabezados.marcas)
    if encabezados:
        piezas.append(_("se recorre por sus %d encabezados") % encabezados)
    if documento.indice:
        piezas.append(_("tiene índice"))
    if imagenes and not sin_describir:
        piezas.append(_("sus %d imágenes llevan descripción") % imagenes)
    elif sin_describir:
        piezas.append(_("%d de sus %d imágenes no llevan descripción")
                      % (sin_describir, imagenes))
    if not piezas:
        return _("Libro de texto, legible con lector de pantalla.")
    return _("Libro de texto: %s.") % ", ".join(piezas)


def a_brf(documento: Documento, contraido: bool = False) -> bytes:
    """Transcribe el documento a braille y lo devuelve como archivo BRF.

    Es la única forma de **sacar el libro del ordenador**: con un BRF se lleva
    a una impresora braille, a un anotador o a otro equipo.  Antes de
    transcribir se separa cada título con una línea en blanco, que es como se
    señala un título en braille cuando no se puede cambiar el cuerpo de letra.
    """
    from . import braille

    return braille.brf_de_bloques(bloques_para_braille(documento, contraido))


def _traductor(contraido: bool):
    """Lo que convierte un trozo de texto en braille contraído, o nada."""
    if not contraido:
        return None
    from . import braille_contraido

    return lambda texto: braille_contraido.a_brf(braille_contraido.celdas(texto))


def _pieza(texto: str, contraido: bool) -> tuple:
    """Un trozo de texto como bloque, contraído o no."""
    if not contraido:
        return (False, texto)
    return (True, _traductor(True)(texto))


def _rejilla(referencia: str) -> list[list[str]]:
    """Deshace la rejilla que la marca de tabla guarda en su referencia."""
    return [linea.split("\t") for linea in referencia.split("\n")
            if linea.strip()]


def bloques_para_braille(documento: Documento, contraido: bool = False) -> list:
    """Reparte el documento en bloques de texto y bloques ya en braille.

    Dos cosas pasan aquí.  La primera: en braille no se puede cambiar el cuerpo
    de letra, así que un **título** se marca dejándolo solo entre dos líneas en
    blanco; es lo que hace que al recorrer la hoja con los dedos se note dónde
    empieza un apartado.

    La segunda: las **fórmulas** se transcriben con el Código Matemático
    Unificado, que es la notación con la que se escriben de verdad las
    matemáticas en braille.  Lo que ese código no cubre —integrales, matrices—
    se queda como estaba, escrito con la frase hablada, y eso es lo correcto:
    una fórmula mal transcrita es peor que una fórmula dicha con palabras.

    Y la tercera: las **tablas** se componen en columnas alineadas en vez de
    salir como texto seguido.  Una tabla leída de corrido deja de ser una tabla,
    porque con el dedo en un número no hay forma de saber de qué columna es; y
    una tabla de datos es justo lo que más se consulta.  Cuando no cabe a lo
    ancho del renglón se escribe linealizada, con el nombre de la columna
    delante de cada dato.

    Con ``contraido`` el texto se escribe en **braille contraído**, que ocupa
    alrededor de un tercio menos. Las fórmulas no se contraen nunca: sus signos
    son los del código matemático y una contracción ahí cambiaría la fórmula.
    Las tablas sí, pero solo en el texto de sus celdas: la retícula se compone
    después, con lo que ya ocupa cada celda en braille.
    """
    from . import braille
    from . import braille_matematicas
    from . import braille_contraido

    formulas = {}
    for marca in documento.marcas.grupo(TipoMarca.FORMULA).marcas:
        linea = documento.linea_de(marca.posicion)
        formulas.setdefault(linea, marca)

    tablas, saltar = {}, set()
    for marca in documento.marcas.grupo(TipoMarca.TABLA).marcas:
        if not marca.referencia:
            continue
        primera = documento.linea_de(marca.posicion)
        ultima = documento.linea_de(max(marca.posicion,
                                        marca.posicion + marca.longitud - 1))
        tablas.setdefault(primera, marca)
        saltar.update(range(primera + 1, ultima + 1))

    bloques: list = []
    encabezados = {}
    for marca in documento.marcas.todas():
        nivel = _nivel(marca.tipo)
        if nivel:
            encabezados[documento.linea_de(marca.posicion)] = nivel

    for numero, linea in enumerate(documento.texto.split("\n")):
        if numero in saltar:
            continue
        marca = tablas.get(numero)
        if marca is not None:
            bloques.append((False, ""))
            if marca.texto:
                bloques.append(_pieza(marca.texto, contraido))
                bloques.append((False, ""))
            traducir = _traductor(contraido)
            for renglon in braille.tabla_a_lineas(_rejilla(marca.referencia),
                                                  traducir=traducir):
                bloques.append((bool(contraido), renglon) if renglon
                               else (False, ""))
            bloques.append((False, ""))
            continue
        texto = linea.strip()
        if not texto:
            continue
        marca = formulas.get(numero)
        if marca is not None:
            transcrita = braille_matematicas.transcribir(marca.referencia or "")
            if transcrita:
                bloques.append((False, ""))
                bloques.append((True, transcrita))
                bloques.append((False, ""))
                continue
        pieza = _pieza(texto, contraido)
        if numero in encabezados:
            bloques.append((False, ""))
            bloques.append(pieza)
            bloques.append((False, ""))
        else:
            bloques.append(pieza)
    return bloques


def a_pef(documento: Documento, contraido: bool = False) -> bytes:
    """Transcribe el documento a braille y lo devuelve como archivo PEF.

    Sale de la misma composición que el BRF —mismo corte de palabras, misma
    paginación—, así que los dos archivos dicen exactamente lo mismo; lo que
    cambia es que el PEF lleva dentro el título y el autor y no depende de la
    tabla de braille ASCII de quien lo abra.
    """
    from . import braille

    metadatos = documento.metadatos
    return braille.a_pef(
        "", metadatos.titulo or Path(documento.ruta_archivo).stem,
        metadatos.autor, metadatos.identificador,
        bloques=bloques_para_braille(documento, contraido))


def a_epub(documento: Documento, destino: Path) -> None:
    """Escribe un EPUB 3 accesible con la estructura del documento.

    Es lo que convierte a este programa en algo más que un lector: lo que se
    dedujo de un PDF sin etiquetar —sus títulos, sus tablas, sus listas— se
    puede **guardar en un archivo que se abre en cualquier lector**, y con la
    descripción que la inteligencia artificial haya puesto a cada imagen.

    Se escribe a mano con ``zipfile`` en vez de traerse una biblioteca entera:
    un EPUB es un ZIP con cuatro archivos dentro y una regla —el ``mimetype``
    va primero y sin comprimir—, y escribirlo así no añade dependencias.
    """
    from . import html_elementos

    metadatos = documento.metadatos
    titulo = metadatos.titulo or Path(documento.ruta_archivo).stem
    autor = metadatos.autor or _("Desconocido")
    idioma = metadatos.idioma or "es"
    identificador = "urn:uuid:visor-%s" % abs(hash(str(documento.ruta_archivo)))

    # El cuerpo se reconstruye con la misma maquinaria que enseña un capítulo
    # en el visor, así que salen las listas, las tablas, las citas, el código y
    # las imágenes con su descripción, no solo los párrafos.
    cuerpo = html_elementos.html_de_tramo(
        documento, 0, len(documento.texto), con_anclas=True)

    indice = []
    for marca in documento.marcas.todas():
        if _nivel(marca.tipo) and (marca.texto or "").strip():
            indice.append((_nivel(marca.tipo), _html.escape(marca.texto.strip())))

    contenido = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" '
        'xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="%s" lang="%s"><head>'
        '<meta charset="utf-8"/><title>%s</title></head><body>\n%s\n</body></html>'
        % (idioma, idioma, _html.escape(titulo), cuerpo))

    paquete = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
        'unique-identifier="uid" xml:lang="%s">\n'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
        '<dc:identifier id="uid">%s</dc:identifier>\n'
        '<dc:title>%s</dc:title>\n<dc:creator>%s</dc:creator>\n'
        '<dc:language>%s</dc:language>\n'
        '<meta property="dcterms:modified">2026-01-01T00:00:00Z</meta>\n'
        '%s\n'
        '</metadata>\n<manifest>\n'
        '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" '
        'properties="nav"/>\n'
        '<item id="c1" href="contenido.xhtml" media-type="application/xhtml+xml"/>\n'
        '</manifest>\n<spine><itemref idref="c1"/></spine>\n</package>'
        % (idioma, identificador, _html.escape(titulo), _html.escape(autor), idioma,
           _metadatos_de_accesibilidad(documento)))

    navegacion = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" '
        'xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="%s"><head>'
        '<meta charset="utf-8"/><title>%s</title></head><body>\n'
        '<nav epub:type="toc" id="toc"><h1>%s</h1>%s</nav>\n</body></html>'
        % (idioma, _html.escape(titulo), _("Índice"), _lista_del_indice(indice, titulo)))

    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as archivo:
        # El mimetype va el primero y sin comprimir: lo exige la norma y es lo
        # que permite reconocer un EPUB por sus primeros bytes.
        archivo.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip",
                         compress_type=zipfile.ZIP_STORED)
        archivo.writestr("META-INF/container.xml",
                         '<?xml version="1.0" encoding="utf-8"?>\n'
                         '<container version="1.0" '
                         'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                         '<rootfiles><rootfile full-path="OEBPS/paquete.opf" '
                         'media-type="application/oebps-package+xml"/></rootfiles>'
                         '</container>')
        archivo.writestr("OEBPS/paquete.opf", paquete)
        archivo.writestr("OEBPS/nav.xhtml", navegacion)
        archivo.writestr("OEBPS/contenido.xhtml", contenido)


def _lista_del_indice(entradas: list, titulo: str) -> str:
    """Escribe el índice como una lista anidada por niveles.

    Anidada y no plana: es lo que hace que al recorrerlo con el lector de
    pantalla se oiga a qué apartado pertenece cada cosa, en vez de una ristra
    de cincuenta títulos todos al mismo nivel.  Cada entrada lleva al ancla que
    la exportación puso en su encabezado, así que **el índice navega de
    verdad**, que era lo que faltaba: antes todas las entradas apuntaban al
    principio del libro.

    El anidamiento se escribe metiendo la lista de dentro **dentro del ``li``
    que la abre**, que es como lo exige la norma; una lista suelta entre dos
    ``li`` deja el índice mal formado y hay lectores que entonces no leen
    ninguna entrada.
    """
    if not entradas:
        return '<ol><li><a href="contenido.xhtml">%s</a></li></ol>' % _html.escape(titulo)

    numeradas = [(nivel, texto, numero)
                 for numero, (nivel, texto) in enumerate(entradas[:2000], start=1)]

    def rama(desde: int, nivel: int) -> tuple[str, int]:
        """Escribe las entradas de ese nivel desde esa posición."""
        partes = ["<ol>"]
        posicion = desde
        while posicion < len(numeradas):
            suyo, texto, numero = numeradas[posicion]
            if suyo < nivel:
                break
            if suyo > nivel:
                # Un nivel que se salta un peldaño: se trata como si fuera del
                # nivel que toca, que es mejor que perder la entrada.
                dentro, posicion = rama(posicion, suyo)
                if partes[-1].endswith("</li>"):
                    partes[-1] = partes[-1][:-len("</li>")] + dentro + "</li>"
                else:
                    partes.append("<li>" + dentro + "</li>")
                continue
            partes.append('<li><a href="contenido.xhtml#t%d">%s</a></li>'
                          % (numero, texto))
            posicion += 1
        partes.append("</ol>")
        return "".join(partes), posicion

    cuerpo, _fin = rama(0, numeradas[0][0])
    return cuerpo


def exportar(documento: Documento, destino, formato: str,
             contraido: bool = False) -> None:
    """Escribe el documento en el formato pedido.

    :param contraido: Solo lo miran el BRF y el PEF: escribe el braille
                      **contraído** en vez del integral.
    :raises ValueError: Si el formato no se conoce.
    :raises OSError: Si no se puede escribir.
    """
    ruta = Path(destino)
    if formato == "epub":
        a_epub(documento, ruta)
    elif formato == "brf":
        ruta.write_bytes(a_brf(documento, contraido))
    elif formato == "pef":
        ruta.write_bytes(a_pef(documento, contraido))
    elif formato == "html":
        ruta.write_bytes(a_html(documento))
    elif formato == "md":
        ruta.write_bytes(a_markdown(documento))
    elif formato == "txt":
        ruta.write_bytes(a_txt(documento))
    else:
        raise ValueError(_("Formato de exportación desconocido: %s") % formato)
    log.info("Documento exportado a %s (%s, %d KB)", ruta.name, formato,
             ruta.stat().st_size // 1024)
