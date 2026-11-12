# -*- coding: utf-8 -*-
"""Escribir un libro DAISY 3, con texto y, si se quiere, con audio sincronizado.

El programa lee libros DAISY 2.02 y DAISY 3 desde hace tiempo.  Escribirlos es
lo que faltaba, y es lo que de verdad cambia algo: **DAISY es el formato de las
bibliotecas para personas ciegas de todo el mundo** —la ONCE, Bookshare, la
National Library Service— y poder generar uno a partir de un PDF recién
reconocido es justamente lo que hoy no se puede hacer sin herramientas de pago.

Qué se escribe
--------------

Un DAISY 3 (ANSI/NISO Z39.86-2005) es una carpeta con cuatro clases de archivo:

``libro.opf``
    El paquete: los metadatos, la lista de archivos y el orden de lectura.

``libro.ncx``
    La navegación: el índice, con un punto por cada encabezado, y la lista de
    páginas.  Es lo que hace que en un reproductor DAISY se pueda saltar de
    capítulo en capítulo y decir «llévame a la página 47».

``libro.xml``
    El texto, en DTBook, que es el XML propio de DAISY: encabezados por
    niveles, párrafos, listas y tablas.  Aquí es donde va **toda** la
    estructura que el programa dedujo del documento.

``libro.smil`` (uno por capítulo, solo con audio)
    La sincronización: qué trozo de la grabación corresponde a cada frase del
    texto.  Es lo que permite escuchar y a la vez seguir el texto en la línea
    braille, que es la razón por la que existe DAISY.

Dos formas, y las dos sirven
----------------------------

**Solo texto** (``textNCX``) es lo normal y lo rápido: sale en un segundo, se
lee con la voz del propio reproductor y ocupa lo que ocupa el libro.

**Texto y audio** (``audioFullText``) tarda lo que tarde en grabarse, ocupa
megas, y a cambio da un libro hablado con el texto sincronizado **frase a
frase**.  La sincronización se consigue grabando cada frase por separado, viendo
cuánto dura cada una y pegándolas en un archivo por capítulo: es lo mismo que se
hace al poner marcas de capítulo en un MP3, solo que con una frase por marca.

Este módulo no habla con la voz del sistema.  Recibe una función que graba, y
así se puede probar entero sin que haya ninguna voz instalada.
"""

from __future__ import annotations

import html as _html
import uuid
from pathlib import Path

from . import segmentador
from .idioma import _
from .marcas import ENCABEZADOS, TipoMarca, es_encabezado, nivel_de_encabezado
from .registro import obtener_registro

log = obtener_registro(__name__)

#: Versión de la norma que se declara.
NORMA = "ANSI/NISO Z39.86-2005"

#: Niveles de anidamiento que admite DTBook.  Más allá del seis no hay
#: elemento que lo represente, así que lo que pase de ahí se queda en el seis.
NIVEL_MAXIMO = 6


def _escapar(texto: str) -> str:
    """Deja un texto listo para meterlo en el XML."""
    return _html.escape(texto or "", quote=True)


def _tiempo(milisegundos: int) -> str:
    """Un instante como lo escribe SMIL 2.0: ``0:00:01.709``."""
    total = max(0, int(milisegundos))
    horas, resto = divmod(total, 3600000)
    minutos, resto = divmod(resto, 60000)
    segundos, milesimas = divmod(resto, 1000)
    return "%d:%02d:%02d.%03d" % (horas, minutos, segundos, milesimas)


class Frase:
    """Una frase del libro: su texto, dónde estaba y qué identificador lleva."""

    __slots__ = ("identificador", "texto", "inicio", "fin", "desde", "hasta")

    def __init__(self, identificador: str, texto: str, inicio: int, fin: int) -> None:
        self.identificador = identificador
        self.texto = texto
        #: Posiciones en el texto del documento.
        self.inicio = inicio
        self.fin = fin
        #: Instantes de la grabación, en milisegundos.  Se rellenan al grabar.
        self.desde = 0
        self.hasta = 0


class Bloque:
    """Una línea del documento convertida en un elemento de DTBook.

    :param clase: ``"h1"``…``"h6"`` para los encabezados, ``"p"`` para lo
                  demás, ``"pagenum"`` para un número de página.
    """

    __slots__ = ("clase", "texto", "identificador", "frases", "rotulo")

    def __init__(self, clase: str, texto: str, identificador: str,
                 rotulo: str = "") -> None:
        self.clase = clase
        self.texto = texto
        self.identificador = identificador
        self.rotulo = rotulo
        self.frases: list[Frase] = []


class Capitulo:
    """Un tramo del libro con su título, sus bloques y su archivo de audio."""

    __slots__ = ("titulo", "nivel", "bloques", "inicio", "fin", "audio", "duracion")

    def __init__(self, titulo: str, nivel: int, inicio: int) -> None:
        self.titulo = titulo
        self.nivel = max(1, min(nivel, NIVEL_MAXIMO))
        self.inicio = inicio
        self.fin = inicio
        self.bloques: list[Bloque] = []
        #: Nombre del archivo de audio del capítulo, si se ha grabado.
        self.audio = ""
        #: Cuánto dura, en milisegundos.
        self.duracion = 0


def _clase_de_linea(encabezados: dict, paginas: dict, numero: int) -> tuple[str, str]:
    """Devuelve ``(clase, rótulo)`` de una línea a partir de sus marcas."""
    nivel = encabezados.get(numero, 0)
    if nivel:
        return "h%d" % min(nivel, NIVEL_MAXIMO), ""
    if numero in paginas:
        return "pagenum", paginas[numero]
    return "p", ""


def analizar(documento, con_frases: bool = False) -> list[Capitulo]:
    """Reparte el documento en capítulos y bloques listos para escribir.

    El corte en capítulos se hace por los encabezados de nivel más alto que
    tenga el libro: si trae encabezados de nivel 1 se corta por ellos, y si solo
    trae de nivel 2 se corta por esos.  Un libro sin ningún encabezado sale
    como un capítulo único, que es lo correcto: partirlo por donde no hay nada
    daría un índice inventado.

    :param con_frases: Si cada bloque se parte además en frases.  Hace falta
                       para sincronizar el audio y no hace falta sin él.
    """
    texto = documento.texto
    encabezados: dict[int, int] = {}
    for tipo in ENCABEZADOS:
        for marca in documento.marcas.grupo(tipo).marcas:
            encabezados[documento.linea_de(marca.posicion)] = nivel_de_encabezado(tipo)
    paginas: dict[int, str] = {}
    for marca in documento.marcas.grupo(TipoMarca.SALTO_PAGINA).marcas:
        paginas.setdefault(documento.linea_de(marca.posicion),
                           (marca.texto or "").strip())

    corte = min(encabezados.values()) if encabezados else 0
    capitulos: list[Capitulo] = []
    actual: Capitulo | None = None
    contador = 0

    posicion = 0
    for numero, linea in enumerate(texto.split("\n")):
        largo = len(linea)
        inicio = posicion
        posicion += largo + 1
        limpia = linea.strip()
        clase, rotulo = _clase_de_linea(encabezados, paginas, numero)
        if not limpia and clase != "pagenum":
            continue

        nivel = encabezados.get(numero, 0)
        if actual is None or (nivel and nivel == corte):
            actual = Capitulo(limpia or _("Capítulo %d") % (len(capitulos) + 1),
                              nivel or 1, inicio)
            capitulos.append(actual)
            if nivel:
                # El título del capítulo es su primer encabezado: se escribe
                # como tal y no se repite como párrafo.
                contador += 1
                bloque = Bloque(clase, limpia, "id%d" % contador)
                actual.bloques.append(bloque)
                if con_frases:
                    _partir(bloque, limpia, inicio, contador)
                actual.fin = inicio + largo
                continue

        contador += 1
        bloque = Bloque(clase, limpia, "id%d" % contador, rotulo)
        actual.bloques.append(bloque)
        if con_frases and limpia:
            _partir(bloque, limpia, inicio, contador)
        actual.fin = inicio + largo

    if not capitulos:
        vacio = Capitulo(getattr(documento.metadatos, "titulo", "") or _("Documento"), 1, 0)
        capitulos.append(vacio)
    return capitulos


def _partir(bloque: Bloque, linea: str, inicio: int, contador: int) -> None:
    """Parte una línea en frases, que es la unidad con la que se sincroniza."""
    posicion = 0
    numero = 0
    while posicion < len(linea):
        desde, hasta = segmentador.siguiente_frase(linea, posicion)
        if hasta <= desde:
            break
        numero += 1
        bloque.frases.append(Frase("f%d_%d" % (contador, numero),
                                   linea[desde:hasta].strip(),
                                   inicio + desde, inicio + hasta))
        posicion = hasta
    if not bloque.frases:
        bloque.frases.append(Frase("f%d_1" % contador, linea, inicio,
                                   inicio + len(linea)))


# ---------------------------------------------------------------------------
# Los archivos
# ---------------------------------------------------------------------------

def dtbook(documento, capitulos: list[Capitulo], con_audio: bool) -> str:
    """Escribe el texto del libro en DTBook."""
    metadatos = documento.metadatos
    idioma = metadatos.idioma or "es"
    titulo = metadatos.titulo or Path(documento.ruta_archivo).stem
    partes = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<!DOCTYPE dtbook PUBLIC "-//NISO//DTD dtbook 2005-3//EN" '
        '"http://www.daisy.org/z3986/2005/dtbook-2005-3.dtd">',
        '<dtbook xmlns="http://www.daisy.org/z3986/2005/dtbook/" version="2005-3" '
        'xml:lang="%s">' % _escapar(idioma),
        "<head>",
        '<meta name="dtb:uid" content="%s"/>' % _escapar(_identificador(documento)),
        '<meta name="dc:Title" content="%s"/>' % _escapar(titulo),
        '<meta name="dc:Creator" content="%s"/>' % _escapar(metadatos.autor or ""),
        "</head>",
        "<book>",
        "<frontmatter>",
        "<doctitle>%s</doctitle>" % _escapar(titulo),
    ]
    if metadatos.autor:
        partes.append("<docauthor>%s</docauthor>" % _escapar(metadatos.autor))
    partes.append("</frontmatter>")
    partes.append("<bodymatter>")
    for numero, capitulo in enumerate(capitulos, start=1):
        partes.append('<level1 id="nivel%d">' % numero)
        if not any(bloque.clase.startswith("h") for bloque in capitulo.bloques):
            # Un nivel sin encabezado no es válido en DTBook, y además dejaría
            # ese tramo sin nombre en el índice.
            partes.append('<h1 id="titulo%d">%s</h1>' % (numero, _escapar(capitulo.titulo)))
        for bloque in capitulo.bloques:
            partes.append(_bloque_a_xml(bloque, con_audio))
        partes.append("</level1>")
    partes.append("</bodymatter>")
    partes.append("</book>")
    partes.append("</dtbook>")
    return "\n".join(partes)


def _bloque_a_xml(bloque: Bloque, con_audio: bool) -> str:
    """Escribe un bloque como el elemento de DTBook que le toca."""
    if bloque.clase == "pagenum":
        return '<pagenum id="%s" page="normal">%s</pagenum>' % (
            bloque.identificador, _escapar(bloque.rotulo or bloque.texto))
    etiqueta = bloque.clase if bloque.clase.startswith("h") else "p"
    if not con_audio or not bloque.frases:
        return '<%s id="%s">%s</%s>' % (etiqueta, bloque.identificador,
                                        _escapar(bloque.texto), etiqueta)
    # Con audio, cada frase lleva su identificador: es lo que el SMIL apunta
    # para poder resaltar la frase que está sonando.
    dentro = "".join('<sent id="%s">%s</sent>' % (frase.identificador,
                                                  _escapar(frase.texto))
                     for frase in bloque.frases)
    return '<%s id="%s">%s</%s>' % (etiqueta, bloque.identificador, dentro, etiqueta)


def ncx(documento, capitulos: list[Capitulo], con_audio: bool) -> str:
    """Escribe la navegación: el índice y las páginas."""
    metadatos = documento.metadatos
    titulo = metadatos.titulo or Path(documento.ruta_archivo).stem
    paginas = [(capitulo, bloque) for capitulo in capitulos
               for bloque in capitulo.bloques if bloque.clase == "pagenum"]
    profundidad = max((capitulo.nivel for capitulo in capitulos), default=1)

    partes = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<!DOCTYPE ncx PUBLIC "-//NISO//DTD ncx 2005-1//EN" '
        '"http://www.daisy.org/z3986/2005/ncx-2005-1.dtd">',
        '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1" '
        'xml:lang="%s">' % _escapar(metadatos.idioma or "es"),
        "<head>",
        '<meta name="dtb:uid" content="%s"/>' % _escapar(_identificador(documento)),
        '<meta name="dtb:depth" content="%d"/>' % profundidad,
        '<meta name="dtb:totalPageCount" content="%d"/>' % len(paginas),
        '<meta name="dtb:maxPageNumber" content="%d"/>' % len(paginas),
        "</head>",
        "<docTitle><text>%s</text></docTitle>" % _escapar(titulo),
    ]
    if metadatos.autor:
        partes.append("<docAuthor><text>%s</text></docAuthor>" % _escapar(metadatos.autor))

    partes.append("<navMap>")
    for numero, capitulo in enumerate(capitulos, start=1):
        destino = _destino(capitulo, capitulo.bloques[0] if capitulo.bloques else None,
                           numero, con_audio, "titulo%d" % numero)
        partes.append('<navPoint id="punto%d" playOrder="%d" class="level1">'
                      % (numero, numero))
        partes.append("<navLabel><text>%s</text></navLabel>" % _escapar(capitulo.titulo))
        partes.append('<content src="%s"/>' % _escapar(destino))
        partes.append("</navPoint>")
    partes.append("</navMap>")

    if paginas:
        partes.append("<pageList>")
        for orden, (capitulo, bloque) in enumerate(paginas, start=1):
            numero = capitulos.index(capitulo) + 1
            destino = _destino(capitulo, bloque, numero, con_audio, bloque.identificador)
            partes.append('<pageTarget id="pagina%d" type="normal" value="%d" '
                          'playOrder="%d">' % (orden, orden, len(capitulos) + orden))
            partes.append("<navLabel><text>%s</text></navLabel>"
                          % _escapar(bloque.rotulo or str(orden)))
            partes.append('<content src="%s"/>' % _escapar(destino))
            partes.append("</pageTarget>")
        partes.append("</pageList>")
    partes.append("</ncx>")
    return "\n".join(partes)


def _destino(capitulo: Capitulo, bloque, numero: int, con_audio: bool,
             respaldo: str) -> str:
    """A dónde apunta una entrada del índice.

    Con audio se apunta al SMIL, que es quien sabe a la vez dónde está el texto
    y dónde está el sonido.  Sin audio se apunta directamente al texto.
    """
    ancla = bloque.identificador if bloque is not None else respaldo
    if con_audio:
        return "%s#par_%s" % (capitulo.audio.replace(".wav", ".smil")
                              .replace(".mp3", ".smil"), ancla)
    return "libro.xml#%s" % ancla


def smil(capitulo: Capitulo, numero: int, titulo: str, identificador: str) -> str:
    """Escribe la sincronización de un capítulo: texto y sonido, frase a frase."""
    partes = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<!DOCTYPE smil PUBLIC "-//NISO//DTD dtbsmil 2005-2//EN" '
        '"http://www.daisy.org/z3986/2005/dtbsmil-2005-2.dtd">',
        '<smil xmlns="http://www.w3.org/2001/SMIL20/">',
        "<head>",
        '<meta name="dtb:uid" content="%s"/>' % _escapar(identificador),
        '<meta name="dtb:totalElapsedTime" content="%s"/>' % _tiempo(0),
        "</head>",
        "<body>",
        '<seq id="seq%d" dur="%.3fs">' % (numero, capitulo.duracion / 1000.0),
    ]
    for bloque in capitulo.bloques:
        for frase in bloque.frases:
            partes.append('<par id="par_%s">' % frase.identificador)
            partes.append('<text src="libro.xml#%s"/>' % frase.identificador)
            partes.append('<audio src="%s" clipBegin="%s" clipEnd="%s"/>'
                          % (_escapar(capitulo.audio), _tiempo(frase.desde),
                             _tiempo(frase.hasta)))
            partes.append("</par>")
        if not bloque.frases:
            partes.append('<par id="par_%s"><text src="libro.xml#%s"/></par>'
                          % (bloque.identificador, bloque.identificador))
    partes.append("</seq>")
    partes.append("</body>")
    partes.append("</smil>")
    return "\n".join(partes)


def opf(documento, capitulos: list[Capitulo], con_audio: bool,
        duracion_total: int) -> str:
    """Escribe el paquete: metadatos, lista de archivos y orden de lectura."""
    metadatos = documento.metadatos
    titulo = metadatos.titulo or Path(documento.ruta_archivo).stem
    identificador = _identificador(documento)
    tipo = "audioFullText" if con_audio else "textNCX"

    recursos = ['<item id="libro" href="libro.xml" media-type="application/x-dtbook+xml"/>',
                '<item id="ncx" href="libro.ncx" media-type="application/x-dtbncx+xml"/>',
                '<item id="opf" href="libro.opf" media-type="text/xml"/>']
    lomo = []
    if con_audio:
        for numero, capitulo in enumerate(capitulos, start=1):
            nombre = "capitulo%03d.smil" % numero
            recursos.append('<item id="smil%d" href="%s" media-type="application/smil"/>'
                            % (numero, nombre))
            lomo.append('<itemref idref="smil%d"/>' % numero)
            if capitulo.audio:
                clase = "audio/mpeg" if capitulo.audio.endswith(".mp3") else "audio/x-wav"
                recursos.append('<item id="audio%d" href="%s" media-type="%s"/>'
                                % (numero, _escapar(capitulo.audio), clase))
    else:
        lomo.append('<itemref idref="libro"/>')

    return "\n".join([
        '<?xml version="1.0" encoding="utf-8"?>',
        '<!DOCTYPE package PUBLIC "+//ISBN 0-9673008-1-9//DTD OEB 1.2 Package//EN" '
        '"http://openebook.org/dtds/oeb-1.2/oebpkg12.dtd">',
        '<package xmlns="http://openebook.org/namespaces/oeb-package/1.0/" '
        'unique-identifier="uid">',
        "<metadata>",
        '<dc-metadata xmlns:dc="http://purl.org/dc/elements/1.1/">',
        "<dc:Format>%s</dc:Format>" % NORMA,
        '<dc:Identifier id="uid">%s</dc:Identifier>' % _escapar(identificador),
        "<dc:Title>%s</dc:Title>" % _escapar(titulo),
        "<dc:Creator>%s</dc:Creator>" % _escapar(metadatos.autor or _("Desconocido")),
        "<dc:Language>%s</dc:Language>" % _escapar(metadatos.idioma or "es"),
        "<dc:Publisher>%s</dc:Publisher>" % _escapar(metadatos.editorial or ""),
        "</dc-metadata>",
        "<x-metadata>",
        '<meta name="dtb:multimediaType" content="%s"/>' % tipo,
        '<meta name="dtb:totalTime" content="%s"/>' % _tiempo(duracion_total),
        '<meta name="dtb:multimediaContent" content="%s"/>'
        % ("audio,text" if con_audio else "text"),
        "</x-metadata>",
        "</metadata>",
        "<manifest>",
        "\n".join(recursos),
        "</manifest>",
        "<spine>",
        "\n".join(lomo),
        "</spine>",
        "</package>",
    ])


def _identificador(documento) -> str:
    """Un identificador estable del libro.

    Se usa el del propio archivo si lo trae; si no, uno inventado a partir de
    su ruta.  Tiene que ser el mismo en los tres archivos o el reproductor
    rechaza el libro por incoherente.
    """
    propio = (getattr(documento.metadatos, "identificador", "") or "").strip()
    if propio:
        return propio
    semilla = str(getattr(documento, "ruta_archivo", "") or "libro")
    return "visor-%s" % uuid.uuid5(uuid.NAMESPACE_URL, semilla)


# ---------------------------------------------------------------------------
# La exportación entera
# ---------------------------------------------------------------------------

def exportar(documento, carpeta, grabar=None, progreso=None, cancelado=None) -> list[Path]:
    """Escribe el libro DAISY completo en una carpeta.

    :param carpeta: Dónde se deja.  Se crea si no existe.
    :param grabar: Función ``(textos, destino) -> comienzos`` que graba una
                   lista de frases en un archivo y devuelve el instante en que
                   empieza cada una, en milisegundos.  Con ``None`` se escribe
                   el libro **solo con texto**, que es lo normal.
    :param progreso: Se llama con ``(hecho, total, detalle)``.
    :param cancelado: Se consulta entre capítulos.
    :return: Los archivos escritos.
    :raises OSError: Si no se puede escribir.
    """
    destino = Path(carpeta)
    destino.mkdir(parents=True, exist_ok=True)
    con_audio = grabar is not None

    capitulos = analizar(documento, con_frases=con_audio)
    escritos: list[Path] = []
    duracion_total = 0

    if con_audio:
        total = len(capitulos)
        for numero, capitulo in enumerate(capitulos, start=1):
            if cancelado is not None and cancelado():
                log.info("Exportación a DAISY cancelada en el capítulo %d", numero)
                return escritos
            if progreso is not None:
                progreso(numero - 1, total, _("Grabando: %s") % capitulo.titulo)
            frases = [frase for bloque in capitulo.bloques for frase in bloque.frases]
            if not frases:
                continue
            nombre = "capitulo%03d.wav" % numero
            comienzos, duracion = grabar([frase.texto for frase in frases],
                                         destino / nombre)
            capitulo.audio = nombre
            capitulo.duracion = duracion
            for indice, frase in enumerate(frases):
                frase.desde = comienzos[indice] if indice < len(comienzos) else 0
                frase.hasta = (comienzos[indice + 1] if indice + 1 < len(comienzos)
                               else duracion)
            duracion_total += duracion
            escritos.append(destino / nombre)

        for numero, capitulo in enumerate(capitulos, start=1):
            archivo = destino / ("capitulo%03d.smil" % numero)
            archivo.write_text(
                smil(capitulo, numero, documento.metadatos.titulo,
                     _identificador(documento)), encoding="utf-8")
            escritos.append(archivo)

    for nombre, contenido in (
            ("libro.xml", dtbook(documento, capitulos, con_audio)),
            ("libro.ncx", ncx(documento, capitulos, con_audio)),
            ("libro.opf", opf(documento, capitulos, con_audio, duracion_total)),
    ):
        archivo = destino / nombre
        archivo.write_text(contenido, encoding="utf-8")
        escritos.append(archivo)

    log.info("Libro DAISY escrito en %s: %d capítulos, %s", destino,
             len(capitulos), "con audio" if con_audio else "solo texto")
    if progreso is not None:
        progreso(len(capitulos), max(len(capitulos), 1), _("Libro DAISY escrito."))
    return escritos
