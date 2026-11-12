# -*- coding: utf-8 -*-
"""Libros DAISY: el texto, para que el resto del programa los trate como libros.

La lectura del formato en sí —las dos versiones, los seis tipos, los SMIL y la
navegación— está en :mod:`nucleo.daisy`.  Aquí solo se hace una cosa: convertir
ese libro en el :class:`~nucleo.documento.Documento` de texto que usa todo lo
demás.

Y se hace **siguiendo el SMIL**, frase a frase, no volcando los archivos de
texto uno detrás de otro.  Eso cambia bastante:

* El orden es el orden real de lectura, el que declara el libro, y no el
  alfabético de los archivos.
* Cada frase deja en el texto un identificador ``daisy-N``.  Como el ensamblador
  guarda esos identificadores con su posición, el reproductor puede ir en los
  dos sentidos: del cursor a la grabación y de la grabación al cursor.
* Un libro **de solo audio** deja de ser un caso perdido.  Antes se rechazaba
  con un «este libro no trae texto»; ahora se construye el documento con lo que
  sí trae —el índice y los números de página del NCC—, que es poco texto pero
  es **navegación de verdad**: se recorre con la tecla H, con Control+T y por
  páginas, y desde cualquier punto se puede empezar a escuchar.

Eso es lo que hace un reproductor DAISY, y es lo que esperan quienes reciben
estos libros de una biblioteca: la mayoría de lo que prestan la ONCE o la
National Library Service son grabaciones humanas, no texto.
"""

from __future__ import annotations

import posixpath
from pathlib import Path

from nucleo import daisy as lector
from nucleo.documento import ElementoIndice, Metadatos
from nucleo.idioma import _
from nucleo.registro import obtener_registro, registrar_excepcion

from .base import Analizador, ErrorFormato, OpcionesAnalisis, registrar
from .ensamblador import envolver, escapar, montar

log = obtener_registro(__name__)

#: Prefijo de los identificadores que atan cada frase con su audio.
FRASE = "daisy-"

#: Etiquetas del contenido que se conservan tal cual al montar el texto.
_ENCABEZADOS = ("h1", "h2", "h3", "h4", "h5", "h6")

#: Traducción de las etiquetas de DTBook a las de HTML.  DTBook es el XML
#: propio de DAISY 3; sus etiquetas son primas de las de HTML, así que se
#: traducen y el conversor las trata como cualquier otro libro.
DTBOOK = {
    "h1": "h1", "h2": "h2", "h3": "h3", "h4": "h4", "h5": "h5", "h6": "h6",
    "hd": "h2", "p": "p", "list": "ul", "li": "li", "table": "table", "tr": "tr",
    "td": "td", "th": "th", "blockquote": "blockquote", "cite": "cite",
    "em": "em", "strong": "strong", "author": "p", "byline": "p",
    "doctitle": "h1", "docauthor": "p", "note": "aside", "sent": "span",
    "imggroup": "figure", "caption": "figcaption", "linenum": "span",
    "line": "p", "poem": "blockquote", "annotation": "aside", "span": "span",
    "levelhd": "h2", "bridgehead": "h3", "prodnote": "aside", "sidebar": "aside",
}


class AnalizadorDAISY(Analizador):
    """Libros DAISY 2.02 y 3, en carpeta o comprimidos, con o sin texto."""

    # ``ncc.html`` es el punto de entrada de un DAISY 2.02 y es un ``.html``
    # corriente, así que el reparto por extensión no basta: quien decide de
    # verdad es :meth:`reconoce`, que mira lo que hay alrededor del archivo.
    extensiones = (".ncx", ".opf", ".daisy")
    descripcion = _("Libros DAISY")

    def reconoce(self, ruta) -> bool:
        """Dice si esta ruta es un libro DAISY, mire lo que mire la extensión.

        Se llama antes que al reparto normal por extensión porque un DAISY 2.02
        se abre por su ``ncc.html``, y un ``.html`` suelto no tiene por qué
        serlo.  Lo que decide es si al lado hay un NCC, un NCX o un OPF de DTB.
        """
        try:
            return lector.es_libro_daisy(ruta)
        except Exception:
            return False

    def analizar(self, ruta, opciones: OpcionesAnalisis):
        """Convierte el libro DAISY en un documento de texto navegable."""
        destino = Path(ruta)
        try:
            libro = lector.abrir(destino, opciones.progreso)
        except ValueError as error:
            raise ErrorFormato(str(error))
        with lector.Origen(destino) as origen:
            if libro.frases:
                textos = self._cargar_textos(origen, libro)
                secciones = self._secciones(libro, textos, opciones)
            else:
                # Sin SMIL no hay nada que sincronizar, y es un caso legítimo:
                # los libros DAISY 3 de solo texto llegan muchas veces con el
                # OPF y el DTBook a secas.  Se leen como cualquier otro libro.
                secciones = self._sin_sincronizar(origen, opciones)

        metadatos = Metadatos()
        metadatos.titulo = libro.titulo
        metadatos.autor = libro.autor
        metadatos.idioma = libro.idioma
        metadatos.editorial = libro.editorial

        if not secciones:
            raise ErrorFormato(_("El libro DAISY no contiene nada que se pueda leer."))
        documento = montar(secciones, metadatos, destino, opciones,
                           indice=self._indice(libro) or None,
                           resolver_ruta=lambda seccion, referencia: posixpath.normpath(
                               posixpath.join(posixpath.dirname(seccion), referencia)))
        return documento

    # -- texto ---------------------------------------------------------------

    def _cargar_textos(self, origen: lector.Origen, libro) -> dict:
        """Lee los archivos de texto del libro y saca el trozo de cada frase.

        Devuelve ``{'archivo.html#id': (etiqueta, texto)}``.  Se carga cada
        archivo una sola vez aunque lo usen mil frases, que es lo normal.
        """
        from lxml import etree  # noqa: F401  (lo usa _analizar)

        archivos = {frase.texto.split("#", 1)[0] for frase in libro.frases if frase.texto}
        trozos: dict[str, tuple[str, str]] = {}
        for archivo in sorted(a for a in archivos if a):
            arbol = lector._analizar(origen, archivo, html=not archivo.lower().endswith(".xml"))
            if arbol is None:
                continue
            for elemento in arbol.iter():
                identificador = elemento.get("id")
                if not identificador:
                    continue
                etiqueta = lector._nombre(elemento)
                clase = (elemento.get("class") or "").lower()
                if clase in ("page-normal", "page-front", "page-special"):
                    etiqueta = "pagenum"
                elif etiqueta == "pagenum":
                    etiqueta = "pagenum"
                trozos["%s#%s" % (archivo, identificador)] = (
                    etiqueta, lector._texto_de(elemento))
        return trozos

    def _secciones(self, libro, textos: dict, opciones: OpcionesAnalisis) -> list:
        """Escribe el XHTML del libro recorriendo sus frases en orden.

        Se agrupa por archivo SMIL: cada uno es una sección, que es como el
        libro está dividido de verdad y lo que hace que «capítulo siguiente»
        vaya donde tiene que ir.
        """
        titulo_de_frase = {punto.frase: punto for punto in libro.puntos}
        pagina_de_frase = {punto.frase: punto for punto in libro.paginas}

        secciones: list[tuple[str, bytes]] = []
        partes: list[str] = []
        smil_actual = ""
        total = len(libro.frases)

        for numero, frase in enumerate(libro.frases):
            if frase.smil != smil_actual:
                if partes:
                    secciones.append((smil_actual, envolver("".join(partes))))
                partes = []
                smil_actual = frase.smil
            if numero % 200 == 0:
                opciones.progreso.paso(numero, total,
                                       _("Montando el texto: %d de %d") % (numero + 1, total))
            partes.append(self._trozo(numero, frase, textos,
                                      titulo_de_frase.get(numero),
                                      pagina_de_frase.get(numero)))
        if partes:
            secciones.append((smil_actual, envolver("".join(partes))))
        return secciones

    def _sin_sincronizar(self, origen: lector.Origen, opciones: OpcionesAnalisis) -> list:
        """Monta el libro cuando no trae SMIL, leyendo su contenido a secas.

        Es el camino de los libros DAISY sin grabación, que no tienen nada que
        sincronizar.  El orden lo da el ``spine`` del OPF y, si no lo hay, el
        nombre de los archivos, que en DAISY suelen ir numerados para eso.
        """
        secciones: list[tuple[str, bytes]] = []
        orden = self._orden_de_contenido(origen)
        total = len(orden)
        for numero, nombre in enumerate(orden, start=1):
            opciones.progreso.paso(numero - 1, total,
                                   _("Leyendo %d de %d") % (numero, total))
            try:
                datos = origen.leer(nombre)
            except Exception as error:
                registrar_excepcion(log, "No se ha podido leer %s" % nombre, error)
                continue
            convertido = convertir_dtbook(datos)
            if convertido is None:
                # No era DTBook: será XHTML, y el conversor normal lo entiende.
                convertido = lector.descodificar(datos).encode("utf-8")
            if convertido:
                secciones.append((nombre, convertido))
        return secciones

    def _orden_de_contenido(self, origen: lector.Origen) -> list[str]:
        """Archivos de texto del libro, en el orden en que se leen."""
        for opf in origen.buscar(".opf"):
            arbol = lector._analizar(origen, opf)
            if arbol is None:
                continue
            rutas = {}
            for elemento in arbol.iter():
                if lector._nombre(elemento) == "item":
                    rutas[elemento.get("id", "")] = elemento.get("href", "")
            orden = []
            for elemento in arbol.iter():
                if lector._nombre(elemento) != "itemref":
                    continue
                href = rutas.get(elemento.get("idref", ""), "")
                if href and href.lower().endswith((".xml", ".html", ".htm", ".xhtml")):
                    orden.append(posixpath.normpath(
                        posixpath.join(posixpath.dirname(opf), href)))
            if orden:
                return orden
        return [nombre for nombre in origen.buscar(".xml", ".html", ".htm", ".xhtml")
                if not nombre.lower().endswith((".ncx", ".opf"))
                and not nombre.lower().endswith(lector.NCC)]

    def _trozo(self, numero: int, frase, textos: dict, punto, pagina) -> str:
        """Escribe el XHTML de una sola frase.

        El identificador ``daisy-N`` es la costura entre el texto y la
        grabación: sin él, el reproductor no sabría a qué altura del libro está
        sonando ni desde dónde tiene que empezar cuando el usuario mueve el
        cursor.  Va en lo primero que se escribe de la frase, que es donde la
        frase empieza.
        """
        marca = '%s%d' % (FRASE, numero)
        etiqueta, contenido = textos.get(frase.texto, ("", ""))
        partes: list[str] = []

        # Una misma frase puede ser a la vez el comienzo de una página y el de
        # un capítulo, y de hecho es lo corriente: los capítulos empiezan en
        # página nueva.  Hay que escribir las dos cosas o se pierde una; antes
        # la página se comía el título y el libro se quedaba sin índice.
        if pagina is not None:
            # Se escribe como el salto de página del EPUB 3 para que el
            # conversor lo reconozca y funcione «ir a la página».
            partes.append('<span epub:type="pagebreak" id="%s" title="%s"></span>'
                          % (marca, escapar(pagina.titulo)))
        elif etiqueta == "pagenum":
            partes.append('<span epub:type="pagebreak" id="%s" title="%s"></span>'
                          % (marca, escapar(contenido)))

        siguiente = marca if not partes else ""
        atributo = ' id="%s"' % siguiente if siguiente else ""

        if punto is not None:
            # Comienzo de un capítulo o sección: manda el título del índice,
            # que es el que el usuario oirá al navegar con H.
            nivel = min(max(punto.nivel, 1), 6)
            partes.append('<h%d%s>%s</h%d>'
                          % (nivel, atributo, escapar(punto.titulo or contenido), nivel))
        elif etiqueta in _ENCABEZADOS:
            partes.append('<%s%s>%s</%s>' % (etiqueta, atributo, escapar(contenido), etiqueta))
        elif contenido:
            partes.append('<p%s>%s</p>' % (atributo, escapar(contenido)))
        elif not partes:
            # Frase sin texto: en un libro de solo audio son casi todas.  Se
            # deja un ancla vacía para que la grabación siga teniendo dónde
            # apoyarse, sin ensuciar el texto con marcadores de relleno.
            partes.append('<span id="%s"></span>' % marca)
        return "".join(partes)

    # -- índice --------------------------------------------------------------

    def _indice(self, libro) -> list[ElementoIndice]:
        """El índice se construye con los encabezados, ya en el ensamblador.

        Se devuelve vacío a propósito: los títulos del NCC o del NCX ya se han
        escrito como ``<h1>``…``<h6>`` al montar el texto, así que dejar que el
        ensamblador los recoja da un índice con las posiciones correctas, que es
        justo lo que aquí todavía no se sabe.
        """
        return []

    # -- recursos ------------------------------------------------------------

    def extraer_recurso(self, ruta, interna: str) -> bytes | None:
        """Extrae una imagen del libro."""
        if not interna:
            return None
        try:
            with lector.Origen(Path(ruta)) as origen:
                return origen.leer(interna)
        except Exception:
            return None


def convertir_dtbook(datos: bytes) -> bytes | None:
    """Traduce un archivo DTBook a XHTML.

    DTBook es el XML de contenido de DAISY 3.  Se usa cuando hay que leer el
    texto completo de un libro fuera del recorrido por frases.
    """
    from lxml import etree

    from .lectura_xml import crear_parser_xml

    try:
        arbol = etree.fromstring(lector.descodificar(datos).encode("utf-8"),
                                 parser=crear_parser_xml())
    except Exception as error:
        registrar_excepcion(log, "DTBook ilegible", error)
        return None
    if arbol is None:
        return None
    cuerpo = None
    for elemento in arbol.iter():
        if lector._nombre(elemento) == "book":
            cuerpo = elemento
            break
    if cuerpo is None:
        return None
    partes: list[str] = []
    _volcar(cuerpo, partes)
    texto = "".join(partes)
    return envolver(texto) if texto.strip() else None


def _volcar(elemento, partes: list[str]) -> None:
    """Recorre el DTBook escribiendo su equivalente en HTML."""
    for hijo in elemento:
        nombre = lector._nombre(hijo)
        if nombre == "img":
            partes.append('<img src="%s" alt="%s"/>'
                          % (escapar(hijo.get("src", "")), escapar(hijo.get("alt", ""))))
            continue
        if nombre == "pagenum":
            texto = " ".join("".join(hijo.itertext()).split())
            partes.append('<span epub:type="pagebreak" title="%s"></span>' % escapar(texto))
            continue
        equivalente = DTBOOK.get(nombre)
        if equivalente is None:
            if hijo.text and hijo.text.strip():
                partes.append(escapar(hijo.text))
            _volcar(hijo, partes)
            if hijo.tail and hijo.tail.strip():
                partes.append(escapar(hijo.tail))
            continue
        partes.append("<%s>" % equivalente)
        if hijo.text:
            partes.append(escapar(hijo.text))
        _volcar(hijo, partes)
        partes.append("</%s>" % equivalente)
        if hijo.tail:
            partes.append(escapar(hijo.tail))


registrar(AnalizadorDAISY())
