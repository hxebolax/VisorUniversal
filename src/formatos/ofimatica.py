# -*- coding: utf-8 -*-
"""Documentos de ofimática: DOCX y ODT.

Es el formato en el que circula casi todo lo que no es un libro publicado:
apuntes de clase, informes, textos de trabajo, originales sin editar.  Poder
abrirlos aquí ahorra el paso de convertirlos en otro programa, que es
precisamente donde se pierde la estructura y todo acaba siendo un bloque.

**Sin dependencias nuevas para DOCX y ODT.**  Los dos son un ZIP con XML
dentro, y el programa ya trae con qué leer ZIP y XML.  Lo que hace falta es
saber qué etiqueta significa qué:

* En DOCX, el estilo del párrafo (``Heading 1``, ``Título 2``…) es lo que
  distingue un encabezado del texto normal, así que de ahí sale la estructura
  navegable con las teclas ``H`` y ``1`` a ``6``.
* En ODT, cada párrafo declara su estilo y los encabezados tienen etiqueta
  propia (``text:h``) con su nivel, que es más directo todavía.

El texto enriquecido (RTF) tiene su propio módulo, :mod:`formatos.rtf`:
no es un ZIP con XML sino un formato de llaves y palabras de control, y
no se parece en nada a estos dos.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

from nucleo.documento import Metadatos
from nucleo.idioma import _
from nucleo.registro import obtener_registro

from .base import Analizador, ErrorFormato, OpcionesAnalisis, registrar
from .ensamblador import abrir_odf, envolver, escapar, montar, parrafos_de_texto
from .lectura_xml import crear_parser_xml

log = obtener_registro(__name__)

#: Espacios de nombres de DOCX.
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
#: Espacios de nombres de ODT.
_TEXT = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
_TABLE = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
_OFFICE = "{urn:oasis:names:tc:opendocument:xmlns:office:1.0}"
_DRAW = "{urn:oasis:names:tc:opendocument:xmlns:drawing:1.0}"
_SVG = "{urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0}"
_XLINK = "{http://www.w3.org/1999/xlink}"
#: Espacios de nombres de DOCX que hacen falta para las imágenes y los enlaces.
_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_V = "{urn:schemas-microsoft-com:vml}"
_DC = "{http://purl.org/dc/elements/1.1/}"
_META = "{urn:oasis:names:tc:opendocument:xmlns:meta:1.0}"

#: Nombres de estilo que en un DOCX identifican un encabezado, con su nivel.
#: Word guarda el estilo en el idioma en el que se creó el documento, así que
#: hay que reconocer los de varios idiomas o los títulos pasan por texto normal.
_ESTILOS_TITULO = re.compile(
    r"^(?:heading|título|titulo|ttulo|titre|überschrift|uberschrift|berschrift|titolo|"
    r"kop|nadpis|rubrik|otsikko|cím|cim|nagl[oó]wek|naglowek|заголовок)\s*([1-6])$",
    re.IGNORECASE)

#: Comienzos de estilo que valen como título cuando el nombre no encaja del
#: todo.  Van sin acentos porque Word los quita al guardar el identificador.
_PREFIJOS_TITULO = ("heading", "titul", "ttulo", "titre", "berschrift", "uberschrift",
                    "titolo", "kop", "nadpis", "rubrik", "otsikko", "cim", "naglowek",
                    "заголовок")


def _texto_de(elemento, etiqueta_texto: str) -> str:
    """Junta el texto de todos los descendientes con esa etiqueta."""
    partes = [nodo.text or "" for nodo in elemento.iter(etiqueta_texto)]
    return "".join(partes)


class AnalizadorDOCX(Analizador):
    """Documentos de Word (.docx) y su variante con macros (.docm).

    Un DOCX bien hecho lleva dentro lo mismo que un EPUB accesible, solo que
    con otros nombres: los estilos de título son los encabezados, el texto
    alternativo de una imagen vive en ``wp:docPr/@descr``, una fila marcada
    como «repetir en cada página» (``w:tblHeader``) es la fila de encabezados
    de la tabla y ``w:numPr`` dice qué párrafos forman una lista y a qué nivel.
    Todo eso es lo que el comprobador de accesibilidad de Word pide poner, y
    aquí se lee para que sirva de algo.
    """

    extensiones = (".docx", ".docm")
    descripcion = _("Documentos de Word")

    def analizar(self, ruta, opciones: OpcionesAnalisis):
        """Convierte el documento a XHTML respetando su estructura de títulos."""
        from lxml import etree

        destino = Path(ruta)
        try:
            with zipfile.ZipFile(destino) as archivo:
                datos = archivo.read("word/document.xml")
                metadatos = self._metadatos(archivo)
                relaciones = self._relaciones(archivo)
                numeraciones = self._numeraciones(archivo)
        except KeyError:
            raise ErrorFormato(_("El archivo no contiene ningún documento de Word."))
        except (OSError, zipfile.BadZipFile) as error:
            raise ErrorFormato(_("El archivo está dañado o no es un DOCX: %s") % error)

        arbol = etree.fromstring(datos, parser=crear_parser_xml())
        cuerpo = arbol.find(_W + "body")
        if cuerpo is None:
            raise ErrorFormato(_("El documento de Word no tiene cuerpo de texto."))

        cuerpo_html = self._volcar(cuerpo, relaciones, numeraciones)
        if not cuerpo_html.strip():
            raise ErrorFormato(_("El documento de Word no contiene texto legible."))
        if not metadatos.titulo:
            metadatos.titulo = destino.stem
        return montar([(destino.name, envolver(cuerpo_html))], metadatos, destino, opciones)

    # -- recorrido del cuerpo -------------------------------------------------

    def _volcar(self, cuerpo, relaciones: dict, numeraciones: dict) -> str:
        """Recorre el cuerpo agrupando en listas los párrafos que lo son.

        Word no tiene listas: tiene párrafos que dicen «pertenezco a la
        numeración 3, nivel 0».  Sacar cada uno como una lista de un elemento
        —que es lo que se hacía antes— convierte veinte viñetas seguidas en
        veinte listas de un punto, y entonces la tecla ``L`` deja de servir
        para nada.  Aquí se juntan las que van seguidas y se anidan por su
        nivel, que es lo que el documento quería decir.
        """
        partes: list[str] = []
        lista: list[tuple[int, str, str]] = []      # (nivel, etiqueta, contenido)
        numeracion_abierta = ""
        for hijo in cuerpo:
            if hijo.tag == _W + "p":
                punto = self._punto_de_lista(hijo, numeraciones)
                if punto is not None:
                    nivel, etiqueta, identificador = punto
                    # Dos listas seguidas son dos listas: si no se cortaran al
                    # cambiar la numeración, los pasos numerados de la segunda
                    # se leerían como viñetas de la primera.
                    if lista and identificador != numeracion_abierta:
                        partes.append(self._cerrar_lista(lista))
                    numeracion_abierta = identificador
                    contenido = self._en_linea(hijo, relaciones)
                    if contenido.strip():
                        lista.append((nivel, etiqueta, contenido))
                    continue
                partes.append(self._cerrar_lista(lista))
                partes.append(self._parrafo(hijo, relaciones))
            elif hijo.tag == _W + "tbl":
                partes.append(self._cerrar_lista(lista))
                partes.append(self._tabla(hijo, relaciones))
        partes.append(self._cerrar_lista(lista))
        return "".join(parte for parte in partes if parte)

    @staticmethod
    def _cerrar_lista(lista: list) -> str:
        """Convierte los puntos acumulados en listas anidadas y vacía el montón."""
        if not lista:
            return ""
        piezas: list[str] = []
        pila: list[str] = []                       # etiquetas abiertas, por nivel
        for nivel, etiqueta, contenido in lista:
            while len(pila) > nivel + 1:
                piezas.append("</%s>" % pila.pop())
            while len(pila) < nivel + 1:
                piezas.append("<%s>" % etiqueta)
                pila.append(etiqueta)
            piezas.append("<li>%s</li>" % contenido)
        while pila:
            piezas.append("</%s>" % pila.pop())
        lista.clear()
        return "".join(piezas)

    def _parrafo(self, parrafo, relaciones: dict) -> str:
        """Convierte un párrafo, mirando su estilo para saber si es un título."""
        contenido = self._en_linea(parrafo, relaciones)
        if not contenido.strip():
            return ""
        nivel = self._nivel_de_titulo(parrafo)
        if nivel:
            return "<h%d>%s</h%d>" % (nivel, contenido, nivel)
        return "<p>%s</p>" % contenido

    def _en_linea(self, elemento, relaciones: dict) -> str:
        """Convierte el contenido de un párrafo: texto, enlaces e imágenes.

        Se recorre en orden en lugar de juntar todo el texto de golpe, porque
        el orden es justamente lo que dice dónde estaba el enlace y dónde la
        imagen.  Sin esto, una imagen con su descripción se perdía entera y un
        enlace quedaba como texto suelto que no llevaba a ninguna parte.
        """
        piezas: list[str] = []
        for hijo in elemento:
            if hijo.tag == _W + "hyperlink":
                interior = self._en_linea(hijo, relaciones)
                destino = relaciones.get(hijo.get(_R + "id", ""), ("", ""))[1]
                ancla = hijo.get(_W + "anchor", "")
                if not destino and ancla:
                    destino = "#" + ancla
                piezas.append('<a href="%s">%s</a>' % (escapar(destino), interior)
                              if interior.strip() else "")
            elif hijo.tag == _W + "r":
                piezas.append(self._pieza_de_texto(hijo, relaciones))
            elif hijo.tag in (_W + "smartTag", _W + "sdt", _W + "sdtContent", _W + "ins"):
                piezas.append(self._en_linea(hijo, relaciones))
        return "".join(piezas)

    def _pieza_de_texto(self, corrida, relaciones: dict) -> str:
        """Convierte una «corrida» de Word: su texto, su énfasis y sus imágenes."""
        piezas: list[str] = []
        for hijo in corrida:
            if hijo.tag == _W + "t":
                piezas.append(escapar(hijo.text or ""))
            elif hijo.tag == _W + "tab":
                piezas.append(" ")
            elif hijo.tag in (_W + "br", _W + "cr"):
                piezas.append("<br/>")
            elif hijo.tag in (_W + "drawing", _W + "pict", _W + "object"):
                piezas.append(self._imagen(hijo, relaciones))
        texto = "".join(piezas)
        if not texto:
            return ""
        propiedades = corrida.find(_W + "rPr")
        if propiedades is not None:
            for etiqueta, envoltura in ((_W + "b", "strong"), (_W + "i", "em")):
                marca = propiedades.find(etiqueta)
                if marca is not None and (marca.get(_W + "val") or "1") not in ("0", "false"):
                    texto = "<%s>%s</%s>" % (envoltura, texto, envoltura)
        return texto

    def _imagen(self, dibujo, relaciones: dict) -> str:
        """Convierte una imagen con el texto alternativo que le pusiera el autor.

        Word lo guarda en ``wp:docPr``: en ``descr`` la descripción y en
        ``title`` el título, que es lo que su comprobador de accesibilidad pide
        rellenar.  Las imágenes antiguas (VML) lo llevan en ``alt``.
        """
        descripcion = ""
        for propiedades in dibujo.iter(_WP + "docPr"):
            descripcion = (propiedades.get("descr") or propiedades.get("title") or "").strip()
            if descripcion:
                break
        if not descripcion:
            for forma in dibujo.iter():
                alterno = (forma.get("alt") or "").strip()
                if alterno:
                    descripcion = alterno
                    break
        origen = ""
        for grafico in dibujo.iter(_A + "blip"):
            origen = relaciones.get(grafico.get(_R + "embed", ""), ("", ""))[1]
            if origen:
                break
        if not origen:
            for imagen in dibujo.iter(_V + "imagedata"):
                origen = relaciones.get(imagen.get(_R + "id", ""), ("", ""))[1]
                if origen:
                    break
        return '<img src="%s" alt="%s"/>' % (escapar(origen), escapar(descripcion))

    # -- listas ---------------------------------------------------------------

    def _punto_de_lista(self, parrafo, numeraciones: dict):
        """Datos de lista del párrafo: ``(nivel, etiqueta HTML, numeración)``.

        Devuelve ``None`` si el párrafo no forma parte de ninguna lista.
        """
        propiedades = parrafo.find(_W + "pPr")
        if propiedades is None:
            return None
        numeracion = propiedades.find(_W + "numPr")
        if numeracion is None:
            return None
        nivel = 0
        marca_nivel = numeracion.find(_W + "ilvl")
        if marca_nivel is not None:
            try:
                nivel = max(0, min(5, int(marca_nivel.get(_W + "val") or 0)))
            except ValueError:
                nivel = 0
        identificador = ""
        marca_id = numeracion.find(_W + "numId")
        if marca_id is not None:
            identificador = marca_id.get(_W + "val") or ""
        formato = numeraciones.get((identificador, nivel), "bullet")
        return nivel, "ul" if formato == "bullet" else "ol", identificador

    @staticmethod
    def _numeraciones(archivo: zipfile.ZipFile) -> dict:
        """Lee de ``numbering.xml`` si cada lista es de viñetas o numerada.

        Sin esto habría que adivinarlo, y una lista de pasos numerados leída
        como viñetas pierde justo lo que la hacía una lista de pasos.
        """
        from lxml import etree

        try:
            arbol = etree.fromstring(archivo.read("word/numbering.xml"),
                                     parser=crear_parser_xml())
        except Exception:
            return {}
        formatos: dict[str, dict[int, str]] = {}
        for abstracto in arbol.iter(_W + "abstractNum"):
            clave = abstracto.get(_W + "abstractNumId") or ""
            niveles: dict[int, str] = {}
            for nivel in abstracto.iter(_W + "lvl"):
                try:
                    numero = int(nivel.get(_W + "ilvl") or 0)
                except ValueError:
                    continue
                formato = nivel.find(_W + "numFmt")
                niveles[numero] = (formato.get(_W + "val") or "bullet") if formato is not None \
                    else "bullet"
            formatos[clave] = niveles
        resultado: dict[tuple[str, int], str] = {}
        for numeracion in arbol.iter(_W + "num"):
            identificador = numeracion.get(_W + "numId") or ""
            referencia = numeracion.find(_W + "abstractNumId")
            clave = (referencia.get(_W + "val") or "") if referencia is not None else ""
            for numero, formato in formatos.get(clave, {}).items():
                resultado[(identificador, numero)] = formato
        return resultado

    # -- tablas ---------------------------------------------------------------

    def _tabla(self, tabla, relaciones: dict) -> str:
        """Convierte una tabla de Word conservando su fila de encabezados.

        La fila marcada como «repetir en cada página» (``w:tblHeader``) es la
        que Word usa como encabezado, y es lo que su comprobador de
        accesibilidad exige poner.  Traducida a ``<th>``, el lector de pantalla
        puede anunciar «Importe, 1.200 €» al recorrer la tabla en lugar de
        soltar los números sueltos.
        """
        cabecera: list[str] = []
        cuerpo: list[str] = []
        for fila in tabla.findall(_W + "tr"):
            es_cabecera = self._es_fila_de_encabezado(fila)
            celdas = []
            for celda in fila.findall(_W + "tc"):
                contenido = "".join(self._en_linea(parrafo, relaciones)
                                    for parrafo in celda.findall(_W + "p"))
                etiqueta = "th" if es_cabecera else "td"
                atributos = ' scope="col"' if es_cabecera else ""
                celdas.append("<%s%s>%s</%s>" % (etiqueta, atributos, contenido, etiqueta))
            if not celdas:
                continue
            (cabecera if es_cabecera else cuerpo).append("<tr>%s</tr>" % "".join(celdas))
        if not cabecera and not cuerpo:
            return ""
        partes = []
        if cabecera:
            partes.append("<thead>%s</thead>" % "".join(cabecera))
        if cuerpo:
            partes.append("<tbody>%s</tbody>" % "".join(cuerpo))
        return "<table>%s</table>" % "".join(partes)

    @staticmethod
    def _es_fila_de_encabezado(fila) -> bool:
        """Indica si la fila está marcada como encabezado de la tabla."""
        propiedades = fila.find(_W + "trPr")
        if propiedades is None:
            return False
        marca = propiedades.find(_W + "tblHeader")
        return marca is not None and (marca.get(_W + "val") or "1") not in ("0", "false")

    # -- lo de siempre --------------------------------------------------------

    @staticmethod
    def _nivel_de_titulo(parrafo) -> int:
        """Nivel del encabezado, o 0 si el párrafo es texto normal."""
        propiedades = parrafo.find(_W + "pPr")
        if propiedades is None:
            return 0
        estilo = propiedades.find(_W + "pStyle")
        if estilo is None:
            return 0
        nombre = (estilo.get(_W + "val") or "").strip()
        encontrado = _ESTILOS_TITULO.match(nombre)
        if encontrado:
            return int(encontrado.group(1))
        # Word guarda el identificador del estilo **sin acentos y sin espacios**,
        # de modo que «Título 2» acaba escrito «Ttulo2».  Sin contemplarlo, en un
        # documento hecho en español ningún título se reconocería como tal.
        digitos = re.search(r"([1-6])$", nombre)
        if digitos and nombre.lower().startswith(_PREFIJOS_TITULO):
            return int(digitos.group(1))
        return 0

    @staticmethod
    def _relaciones(archivo: zipfile.ZipFile) -> dict:
        """Lee ``document.xml.rels``: a qué apunta cada identificador.

        Es la tabla que hace falta para dos cosas: saber a dónde lleva un
        enlace y qué archivo es la imagen de una figura.  En el DOCX ninguna de
        las dos aparece en el documento: solo un identificador que hay que
        buscar aquí.
        """
        from lxml import etree

        try:
            arbol = etree.fromstring(archivo.read("word/_rels/document.xml.rels"),
                                     parser=crear_parser_xml())
        except Exception:
            return {}
        resultado: dict[str, tuple[str, str]] = {}
        for relacion in arbol:
            identificador = relacion.get("Id") or ""
            destino = relacion.get("Target") or ""
            tipo = (relacion.get("Type") or "").rsplit("/", 1)[-1]
            if not identificador or not destino:
                continue
            if relacion.get("TargetMode") == "External" or "://" in destino:
                resultado[identificador] = (tipo, destino)
            else:
                # Las rutas internas van relativas a «word/», que es donde vive
                # el documento; el extractor de recursos las quiere completas.
                resultado[identificador] = (tipo, "word/" + destino.lstrip("/"))
        return resultado

    @staticmethod
    def _metadatos(archivo: zipfile.ZipFile) -> Metadatos:
        """Lee título y autor de las propiedades del documento."""
        from lxml import etree

        metadatos = Metadatos()
        try:
            nucleo = etree.fromstring(archivo.read("docProps/core.xml"),
                                      parser=crear_parser_xml())
        except Exception:
            return metadatos
        for elemento in nucleo.iter():
            nombre = str(elemento.tag).rsplit("}", 1)[-1]
            valor = (elemento.text or "").strip()
            if not valor:
                continue
            if nombre == "title" and not metadatos.titulo:
                metadatos.titulo = valor
            elif nombre == "creator" and not metadatos.autor:
                metadatos.autor = valor
            elif nombre == "language" and not metadatos.idioma:
                metadatos.idioma = valor
            elif nombre == "description" and not metadatos.descripcion:
                metadatos.descripcion = valor
        return metadatos

    def extraer_recurso(self, ruta, interna: str) -> bytes | None:
        """Extrae una imagen incrustada en el documento."""
        if not interna:
            return None
        try:
            with zipfile.ZipFile(Path(ruta)) as archivo:
                return archivo.read(interna)
        except Exception:
            return None


class AnalizadorODT(Analizador):
    """Documentos de LibreOffice y OpenOffice (.odt).

    ODT dice las cosas más claras que ningún otro formato de ofimática: los
    encabezados tienen etiqueta propia con su nivel (``text:h``), el texto
    alternativo de una imagen es un elemento de verdad (``svg:desc``), las
    filas de encabezado de una tabla van dentro de ``table:table-header-rows``
    y las listas son listas.  Aquí se aprovecha todo eso tal cual.
    """

    extensiones = (".odt", ".fodt")
    descripcion = _("Documentos de LibreOffice")

    def analizar(self, ruta, opciones: OpcionesAnalisis):
        """Convierte el documento a XHTML con sus encabezados y listas."""
        from lxml import etree

        destino = Path(ruta)
        try:
            with abrir_odf(destino) as archivo:
                datos = archivo.read("content.xml")
                metadatos = self._metadatos(archivo)
        except KeyError:
            raise ErrorFormato(_("El archivo no contiene ningún documento de texto."))
        except (OSError, zipfile.BadZipFile) as error:
            raise ErrorFormato(_("El archivo está dañado o no es un ODT: %s") % error)

        arbol = etree.fromstring(datos, parser=crear_parser_xml())
        cuerpo = arbol.find(".//" + _OFFICE + "text")
        if cuerpo is None:
            raise ErrorFormato(_("El documento no tiene cuerpo de texto."))

        partes: list[str] = []
        self._volcar(cuerpo, partes)
        cuerpo_html = "".join(partes)
        if not cuerpo_html.strip():
            raise ErrorFormato(_("El documento no contiene texto legible."))
        if not metadatos.titulo:
            metadatos.titulo = destino.stem
        return montar([(destino.name, envolver(cuerpo_html))], metadatos, destino, opciones)

    def _volcar(self, elemento, partes: list[str]) -> None:
        """Recorre el cuerpo del ODT escribiendo su equivalente en HTML."""
        for hijo in elemento:
            etiqueta = str(hijo.tag)
            if etiqueta in (_TEXT + "h", _TEXT + "p"):
                notas: list[str] = []
                contenido = self._en_linea(hijo, notas)
                if contenido.strip():
                    if etiqueta == _TEXT + "h":
                        nivel = max(1, min(
                            6, int(hijo.get(_TEXT + "outline-level", "1") or 1)))
                        partes.append("<h%d>%s</h%d>" % (nivel, contenido, nivel))
                    else:
                        partes.append("<p>%s</p>" % contenido)
                partes.extend(notas)
            elif etiqueta == _TEXT + "list":
                partes.append(self._lista(hijo))
            elif etiqueta == _TABLE + "table":
                partes.append(self._tabla(hijo))
            else:
                self._volcar(hijo, partes)

    def _en_linea(self, elemento, notas: list | None = None) -> str:
        """Texto de un párrafo con sus enlaces, sus imágenes y sus énfasis.

        Se recorre en orden, y no se junta el texto de golpe, porque el orden
        es lo que dice dónde estaba cada cosa: juntándolo se perdían las
        imágenes con su descripción y los enlaces con su destino.

        :param notas: Lista donde se dejan las notas al pie que aparezcan, para
                      que quien llama las escriba **detrás** del párrafo.
        """
        piezas: list[str] = [escapar(elemento.text or "")]
        for hijo in elemento:
            etiqueta = str(hijo.tag)
            if etiqueta == _TEXT + "a":
                destino = hijo.get(_XLINK + "href", "")
                interior = self._en_linea(hijo, notas)
                piezas.append('<a href="%s">%s</a>' % (escapar(destino), interior)
                              if interior.strip() else interior)
            elif etiqueta == _TEXT + "s":
                piezas.append(" ")
            elif etiqueta == _TEXT + "tab":
                piezas.append(" ")
            elif etiqueta == _TEXT + "line-break":
                piezas.append("<br/>")
            elif etiqueta == _DRAW + "frame":
                piezas.append(self._imagen(hijo))
            elif etiqueta == _TEXT + "note":
                # Una nota al pie: la llamada se queda en su sitio dentro del
                # párrafo y el texto de la nota se aparta para ponerlo detrás.
                # Dejarlo donde está lo metería en mitad de la frase, que es
                # justo lo que una nota al pie existe para evitar.
                cuerpo = hijo.find(_TEXT + "note-body")
                cita = hijo.find(_TEXT + "note-citation")
                rotulo = escapar("".join(cita.itertext()).strip()) if cita is not None else "*"
                piezas.append('<a class="noteref">%s</a>' % rotulo)
                texto = self._en_linea(cuerpo, notas) if cuerpo is not None else ""
                if texto.strip() and notas is not None:
                    notas.append('<aside class="nota" role="doc-footnote">%s</aside>' % texto)
            else:
                piezas.append(self._en_linea(hijo, notas))
            piezas.append(escapar(hijo.tail or ""))
        return "".join(piezas)

    def _imagen(self, marco) -> str:
        """Convierte un marco de dibujo en una imagen con su descripción.

        ODT guarda el texto alternativo en ``svg:desc`` y el título en
        ``svg:title``, que son los dos campos que LibreOffice pide rellenar en
        «Insertar, Imagen, Propiedades, Texto alternativo».
        """
        descripcion = ""
        for etiqueta in (_SVG + "desc", _SVG + "title"):
            nodo = marco.find(etiqueta)
            if nodo is not None and (nodo.text or "").strip():
                descripcion = nodo.text.strip()
                break
        if not descripcion:
            descripcion = (marco.get(_DRAW + "name") or "").strip()
        origen = ""
        imagen = marco.find(_DRAW + "image")
        if imagen is not None:
            origen = imagen.get(_XLINK + "href", "").lstrip("./")
        return '<img src="%s" alt="%s"/>' % (escapar(origen), escapar(descripcion))

    def _lista(self, lista) -> str:
        """Convierte una lista con sus puntos y sus listas anidadas.

        Antes se sacaban todos los puntos en plano, incluidos los de las listas
        de dentro: una lista de tres apartados con cuatro subapartados cada uno
        salía como una lista de quince puntos al mismo nivel, y el lector de
        pantalla anunciaba quince donde había tres.
        """
        etiqueta = "ol" if self._es_numerada(lista) else "ul"
        puntos: list[str] = []
        for punto in lista.findall(_TEXT + "list-item"):
            partes: list[str] = []
            for hijo in punto:
                nombre = str(hijo.tag)
                if nombre in (_TEXT + "p", _TEXT + "h"):
                    partes.append(self._en_linea(hijo))
                elif nombre == _TEXT + "list":
                    partes.append(self._lista(hijo))
            contenido = "".join(partes)
            if contenido.strip():
                puntos.append("<li>%s</li>" % contenido)
        return "%s%s</%s>" % ("<%s>" % etiqueta, "".join(puntos), etiqueta) if puntos else ""

    @staticmethod
    def _es_numerada(lista) -> bool:
        """Indica si la lista lleva números en lugar de viñetas.

        El estilo con el detalle vive en ``styles.xml``, que aquí no se lee;
        basta con el nombre del estilo, que LibreOffice compone con la palabra
        «Numbering» cuando la lista es numerada.
        """
        estilo = (lista.get(_TEXT + "style-name") or "").lower()
        return "number" in estilo or "numering" in estilo or "enum" in estilo

    def _tabla(self, tabla) -> str:
        """Convierte una tabla conservando sus filas de encabezado.

        ODT las marca con ``table:table-header-rows``, que es lo que se traduce
        a ``<th scope="col">``: con eso el lector de pantalla puede anunciar el
        encabezado de cada celda al recorrer la tabla.
        """
        cabecera: list[str] = []
        cuerpo: list[str] = []
        for grupo in tabla.iter():
            if str(grupo.tag) != _TABLE + "table-row":
                continue
            es_cabecera = self._dentro_de_encabezado(grupo, tabla)
            celdas = []
            for celda in grupo.findall(_TABLE + "table-cell"):
                contenido = "".join(self._en_linea(parrafo)
                                    for parrafo in celda
                                    if str(parrafo.tag) in (_TEXT + "p", _TEXT + "h"))
                etiqueta = "th" if es_cabecera else "td"
                atributos = ' scope="col"' if es_cabecera else ""
                celdas.append("<%s%s>%s</%s>" % (etiqueta, atributos, contenido, etiqueta))
            if celdas:
                (cabecera if es_cabecera else cuerpo).append("<tr>%s</tr>" % "".join(celdas))
        if not cabecera and not cuerpo:
            return ""
        partes = []
        if cabecera:
            partes.append("<thead>%s</thead>" % "".join(cabecera))
        if cuerpo:
            partes.append("<tbody>%s</tbody>" % "".join(cuerpo))
        return "<table>%s</table>" % "".join(partes)

    @staticmethod
    def _dentro_de_encabezado(fila, tabla) -> bool:
        """Indica si la fila cuelga de un ``table:table-header-rows``."""
        padre = fila.getparent()
        while padre is not None and padre is not tabla:
            if str(padre.tag) == _TABLE + "table-header-rows":
                return True
            padre = padre.getparent()
        return False

    @staticmethod
    def _metadatos(archivo: zipfile.ZipFile) -> Metadatos:
        """Lee los metadatos de ``meta.xml``."""
        from lxml import etree

        metadatos = Metadatos()
        try:
            arbol = etree.fromstring(archivo.read("meta.xml"), parser=crear_parser_xml())
        except Exception:
            return metadatos
        for elemento in arbol.iter():
            valor = (elemento.text or "").strip()
            if not valor:
                continue
            if elemento.tag == _DC + "title" and not metadatos.titulo:
                metadatos.titulo = valor
            elif elemento.tag == _DC + "creator" and not metadatos.autor:
                metadatos.autor = valor
            elif elemento.tag == _DC + "language" and not metadatos.idioma:
                metadatos.idioma = valor
            elif elemento.tag == _DC + "description" and not metadatos.descripcion:
                metadatos.descripcion = valor
            elif elemento.tag == _META + "initial-creator" and not metadatos.autor:
                metadatos.autor = valor
        return metadatos

    def extraer_recurso(self, ruta, interna: str) -> bytes | None:
        """Extrae una imagen incrustada en el documento."""
        if not interna:
            return None
        try:
            with zipfile.ZipFile(Path(ruta)) as archivo:
                return archivo.read(interna)
        except Exception:
            return None


registrar(AnalizadorDOCX())
registrar(AnalizadorODT())
