# -*- coding: utf-8 -*-
"""Formatos de texto: TXT, Markdown, HTML y FictionBook.

Son los formatos «sencillos», y precisamente por eso importan: una parte enorme
de lo que llega a un lector de pantalla no es un EPUB sino un archivo de texto
suelto, una página guardada del navegador o un apunte en Markdown.  Abrirlos
aquí evita tener que convertirlos antes en otro programa.

Los cuatro acaban en lo mismo: un XHTML que se le pasa al ensamblador común.

* **TXT**: se agrupa en párrafos.  Un detalle que se nota al leer: los bloques
  de líneas cortas —verso, listas, índices— se dejan línea a línea, mientras
  que la prosa partida por el ancho del archivo se junta en un párrafo, que es
  como el lector de pantalla la lee bien.
* **Markdown**: se convierte a HTML con el conversor propio del programa, el
  mismo que muestra el manual, así que los encabezados y las listas quedan
  navegables con las teclas de siempre.
* **HTML**: se convierte tal cual.
* **FB2**: es XML con sus propias etiquetas; se traducen a las de HTML.
"""

from __future__ import annotations

import re
from pathlib import Path

from nucleo import marcado
from nucleo.documento import Metadatos
from nucleo.idioma import _
from nucleo.registro import obtener_registro

from . import articulo
from .base import Analizador, ErrorFormato, OpcionesAnalisis, registrar
from .ensamblador import envolver, escapar, montar, parrafos_de_texto
from .lectura_xml import crear_parser_xml

log = obtener_registro(__name__)

#: Codificaciones que se prueban, en orden, al abrir un archivo de texto.
#: El orden importa: UTF-8 primero porque es lo normal hoy, y los dos de
#: Windows después porque es de donde salen los archivos antiguos en español.
CODIFICACIONES = ("utf-8-sig", "utf-8", "cp1252", "latin-1")

#: Marcas de orden de bytes con las que un archivo dice en qué codificación
#: está.  Se miran **antes** que nada porque son la única señal segura que hay:
#: un archivo en UTF-16 —que es lo que guarda el Bloc de notas de Windows al
#: elegir «Unicode»— se deja decodificar como cp1252 sin protestar, y lo que
#: sale es el texto con un byte nulo entre cada dos letras.  Probar
#: codificaciones a ver cuál no falla no sirve para esto: hay que preguntarle
#: al archivo.  La lista va de la marca más larga a la más corta, porque la de
#: UTF-32 empieza igual que la de UTF-16.
MARCAS_DE_ORDEN = (
    (bytes.fromhex("fffe0000"), "utf-32"),
    (bytes.fromhex("0000feff"), "utf-32"),
    (bytes.fromhex("efbbbf"), "utf-8-sig"),
    (bytes.fromhex("fffe"), "utf-16"),
    (bytes.fromhex("feff"), "utf-16"),
)


#: A partir de este tamaño, un archivo de texto se trocea en varias secciones.
#: Sin esto, un libro entero sería una sola sección y la navegación por
#: capítulos no tendría nada a lo que saltar.
TROZO = 200_000


def leer_texto(ruta) -> str:
    """Lee un archivo de texto probando codificaciones hasta que una funcione.

    La última de la lista nunca falla —``latin-1`` acepta cualquier byte—, de
    modo que un archivo con la codificación estropeada se abre igual, con algún
    carácter raro, en lugar de negarse a abrirlo.
    """
    return descifrar(Path(ruta).read_bytes())


def descifrar(datos: bytes) -> str:
    """Convierte a texto unos bytes, averiguando en qué codificación vienen.

    Primero se mira si el archivo lo dice él mismo con su marca de orden de
    bytes, que es la única señal fiable; y si no la trae, se prueban las
    codificaciones corrientes hasta que una funcione.
    """
    for marca, codificacion in MARCAS_DE_ORDEN:
        if datos.startswith(marca):
            try:
                # Las de UTF-16 y UTF-32 se quedan la marca al decodificar, así
                # que se quita: en el texto sería un carácter invisible al
                # principio del libro.
                return datos.decode(codificacion).lstrip("﻿")
            except (UnicodeDecodeError, LookupError):
                break
    for codificacion in CODIFICACIONES:
        try:
            return datos.decode(codificacion)
        except UnicodeDecodeError:
            continue
    return datos.decode("latin-1", errors="replace")


def _trocear(texto: str) -> list[str]:
    """Parte un texto largo en trozos, cortando siempre entre párrafos."""
    if len(texto) <= TROZO:
        return [texto]
    trozos: list[str] = []
    resto = texto
    while len(resto) > TROZO:
        corte = resto.rfind("\n\n", TROZO // 2, TROZO)
        if corte == -1:
            corte = resto.rfind("\n", TROZO // 2, TROZO)
        if corte == -1:
            corte = TROZO
        trozos.append(resto[:corte])
        resto = resto[corte:]
    if resto.strip():
        trozos.append(resto)
    return trozos


class AnalizadorTexto(Analizador):
    """Archivos de texto plano y Markdown."""

    extensiones = (".txt", ".text", ".md", ".markdown", ".log", ".nfo")
    descripcion = _("Texto plano y Markdown")

    def analizar(self, ruta, opciones: OpcionesAnalisis):
        """Convierte el archivo en un documento con párrafos navegables."""
        destino = Path(ruta)
        texto = leer_texto(destino)
        if not texto.strip():
            raise ErrorFormato(_("El archivo está vacío."))
        es_markdown = destino.suffix.lower() in (".md", ".markdown")
        secciones = []
        for numero, trozo in enumerate(_trocear(texto), start=1):
            if es_markdown:
                cuerpo = marcado.a_html(trozo, "")
                # El conversor de Markdown devuelve una página entera; aquí solo
                # hace falta el cuerpo, que es lo que se ensambla.
                inicio = cuerpo.find("<body>")
                fin = cuerpo.rfind("</body>")
                if inicio != -1 and fin != -1:
                    cuerpo = cuerpo[inicio + 6:fin]
            else:
                cuerpo = parrafos_de_texto(trozo)
            secciones.append(("parte-%d" % numero, envolver(cuerpo)))
        return montar(secciones, Metadatos(titulo=destino.stem), destino, opciones)


class AnalizadorWeb(Analizador):
    """Páginas web guardadas en el disco."""

    extensiones = (".html", ".htm", ".xhtml", ".xml")
    descripcion = _("Páginas web")

    def analizar(self, ruta, opciones: OpcionesAnalisis):
        """Convierte la página, quedándose con el artículo si se ha pedido."""
        destino = Path(ruta)
        datos = destino.read_bytes()
        if not datos.strip():
            raise ErrorFormato(_("El archivo está vacío."))
        titulo = self._titulo(datos) or destino.stem
        if opciones.solo_articulo:
            # Si no se puede decidir con seguridad, el extractor devuelve
            # «None» y la página se lee entera, que es lo que hacía siempre.
            recortada = articulo.extraer(datos)
            if recortada is not None:
                datos = recortada
        metadatos = Metadatos(titulo=titulo)
        return montar([(destino.name, datos)], metadatos, destino, opciones)

    @staticmethod
    def _titulo(datos: bytes) -> str:
        """Saca el título de la etiqueta ``<title>`` de la página."""
        encontrado = re.search(rb"<title[^>]*>(.*?)</title>", datos[:20000],
                               re.IGNORECASE | re.DOTALL)
        if not encontrado:
            return ""
        return encontrado.group(1).decode("utf-8", errors="replace").strip()[:200]


class AnalizadorFB2(Analizador):
    """FictionBook 2, muy extendido en las bibliotecas de Europa del Este.

    Es XML con etiquetas propias: ``<section>`` por capítulo, ``<title>`` para
    los títulos y ``<p>`` para los párrafos.  Se traducen a las de HTML y el
    resto del programa las trata como cualquier otro libro.
    """

    extensiones = (".fb2",)
    descripcion = _("FictionBook (FB2)")

    #: Correspondencia entre las etiquetas de FB2 y las de HTML.
    EQUIVALENCIAS = {
        "p": "p", "empty-line": "br", "strong": "strong", "emphasis": "em",
        "strikethrough": "s", "sub": "sub", "sup": "sup", "code": "code",
        "poem": "blockquote", "cite": "blockquote", "epigraph": "blockquote",
        "stanza": "div", "v": "p", "subtitle": "h3", "text-author": "p",
        "table": "table", "tr": "tr", "td": "td", "th": "th",
    }

    def analizar(self, ruta, opciones: OpcionesAnalisis):
        """Traduce el FB2 a XHTML y lo ensambla."""
        from lxml import etree

        destino = Path(ruta)
        try:
            arbol = etree.fromstring(destino.read_bytes(), parser=crear_parser_xml())
        except Exception as error:
            raise ErrorFormato(_("El archivo no es un FictionBook válido: %s") % error)
        if arbol is None:
            raise ErrorFormato(_("El archivo no es un FictionBook válido."))

        metadatos = self._metadatos(arbol)
        cuerpos = [hijo for hijo in arbol.iter() if self._nombre(hijo) == "body"]
        if not cuerpos:
            raise ErrorFormato(_("El FictionBook no tiene ningún cuerpo de texto."))

        secciones = []
        for cuerpo in cuerpos:
            hijas = [h for h in cuerpo if self._nombre(h) == "section"]
            for numero, seccion in enumerate(hijas or [cuerpo], start=1):
                partes = ["<div>"]
                self._volcar(seccion, partes, 1)
                partes.append("</div>")
                secciones.append(("seccion-%d" % len(secciones + [1]),
                                  envolver("".join(partes))))
        return montar(secciones, metadatos, destino, opciones)

    @staticmethod
    def _nombre(elemento) -> str:
        """Nombre de la etiqueta sin su espacio de nombres."""
        etiqueta = elemento.tag
        if not isinstance(etiqueta, str):
            return ""
        return etiqueta.rsplit("}", 1)[-1].lower()

    def _volcar(self, elemento, partes: list[str], nivel: int) -> None:
        """Recorre el árbol FB2 escribiendo su equivalente en HTML."""
        for hijo in elemento:
            nombre = self._nombre(hijo)
            if nombre == "section":
                partes.append("<div>")
                self._volcar(hijo, partes, min(nivel + 1, 6))
                partes.append("</div>")
                continue
            if nombre == "title":
                texto = " ".join("".join(hijo.itertext()).split())
                if texto:
                    partes.append("<h%d>%s</h%d>" % (nivel, escapar(texto), nivel))
                continue
            if nombre == "image":
                referencia = ""
                for clave, valor in hijo.attrib.items():
                    if clave.rsplit("}", 1)[-1] == "href":
                        referencia = valor.lstrip("#")
                partes.append('<img src="%s" alt=""/>' % escapar(referencia))
                continue
            equivalente = self.EQUIVALENCIAS.get(nombre)
            if equivalente is None:
                self._volcar(hijo, partes, nivel)
                continue
            if equivalente == "br":
                partes.append("<br/>")
                continue
            partes.append("<%s>" % equivalente)
            if hijo.text:
                partes.append(escapar(hijo.text))
            self._volcar(hijo, partes, nivel)
            partes.append("</%s>" % equivalente)
            if hijo.tail:
                partes.append(escapar(hijo.tail))

    def _metadatos(self, arbol) -> Metadatos:
        """Saca título, autor e idioma de la descripción del FictionBook."""
        metadatos = Metadatos()
        for elemento in arbol.iter():
            nombre = self._nombre(elemento)
            if nombre == "book-title" and not metadatos.titulo:
                metadatos.titulo = " ".join("".join(elemento.itertext()).split())
            elif nombre == "author" and not metadatos.autor:
                partes = []
                for hijo in elemento:
                    if self._nombre(hijo) in ("first-name", "middle-name", "last-name"):
                        texto = (hijo.text or "").strip()
                        if texto:
                            partes.append(texto)
                metadatos.autor = " ".join(partes)
            elif nombre == "lang" and not metadatos.idioma:
                metadatos.idioma = (elemento.text or "").strip()
            elif nombre == "publisher" and not metadatos.editorial:
                metadatos.editorial = (elemento.text or "").strip()
        return metadatos

    def extraer_recurso(self, ruta, interna: str) -> bytes | None:
        """Extrae una imagen del FictionBook, que las lleva dentro en base64."""
        import base64
        from lxml import etree

        if not interna:
            return None
        try:
            arbol = etree.fromstring(Path(ruta).read_bytes(), parser=crear_parser_xml())
        except Exception:
            return None
        for elemento in arbol.iter():
            if self._nombre(elemento) != "binary":
                continue
            if elemento.get("id") != interna:
                continue
            try:
                return base64.b64decode("".join((elemento.text or "").split()))
            except Exception as error:
                log.debug("Imagen FB2 ilegible (%s): %s", interna, error)
                return None
        return None


registrar(AnalizadorTexto())
registrar(AnalizadorWeb())
registrar(AnalizadorFB2())
