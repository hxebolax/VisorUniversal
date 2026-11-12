# -*- coding: utf-8 -*-
"""Presentaciones: PowerPoint (.pptx) e Impress (.odp).

Los apuntes de clase llegan así. Hasta ahora había que convertirlos en otro
programa, que es justo donde se pierde el orden de las diapositivas y todo
acaba siendo un bloque de texto sin saber dónde empieza cada una.

Los dos son un ZIP con XML dentro, igual que el DOCX y el ODT, así que no hace
falta instalar nada: :mod:`formatos.ofimatica` ya demostró que con el ZIP y el
XML de la biblioteca estándar basta.

**Lo que hay que decidir en una presentación no es cómo leer el texto, sino en
qué orden.** Una diapositiva no tiene un hilo: tiene cuadros colocados por la
pantalla, y el archivo los guarda en el orden en que se dibujaron, que puede ser
cualquiera. Aquí se ordenan **de arriba abajo y de izquierda a derecha** por su
posición real, que es como se lee una diapositiva mirándola. Sin eso, el título
puede salir en medio y el pie antes que el cuerpo.

Y tres cosas más que cambian mucho cómo suena:

- **Cada diapositiva es un encabezado de nivel 1**, con su número y su título.
  Así se salta de una a otra con la tecla ``H`` y se ven todas en el índice, que
  es la forma natural de recorrer unos apuntes.
- **Las notas del ponente se leen**, detrás de la diapositiva y anunciadas como
  lo que son. En unos apuntes suelen tener más contenido que la diapositiva.
- **Las tablas y las imágenes con descripción salen** como tabla e imagen de
  verdad, no como texto suelto.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

from lxml import etree

from nucleo.documento import Metadatos
from nucleo.idioma import _
from nucleo.registro import obtener_registro, registrar_excepcion

from .base import Analizador, ErrorFormato, OpcionesAnalisis, registrar
from .ensamblador import abrir_odf, escapar, montar
from .lectura_xml import crear_parser_xml

log = obtener_registro(__name__)

#: Espacios de nombres de PowerPoint.
_P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_CP = "{http://schemas.openxmlformats.org/package/2006/metadata/core-properties}"
_DC = "{http://purl.org/dc/elements/1.1/}"
_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"

#: Espacios de nombres de Impress.
_TEXT = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
_DRAW = "{urn:oasis:names:tc:opendocument:xmlns:drawing:1.0}"
_OFFICE = "{urn:oasis:names:tc:opendocument:xmlns:office:1.0}"
_TABLE = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
_PRESENTATION = "{urn:oasis:names:tc:opendocument:xmlns:presentation:1.0}"
_SVG = "{urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0}"
_XLINK = "{http://www.w3.org/1999/xlink}"
_META = "{urn:oasis:names:tc:opendocument:xmlns:meta:1.0}"

#: Nombre de archivo de una diapositiva dentro del pptx, con su número.
_NUMERO_DIAPOSITIVA = re.compile(r"slide(\d+)\.xml$", re.IGNORECASE)


class Cuadro:
    """Un cuadro de una diapositiva: dónde está y qué lleva escrito."""

    __slots__ = ("arriba", "izquierda", "es_titulo", "html", "orden")

    def __init__(self, arriba: int, izquierda: int, es_titulo: bool,
                 html: str, orden: int) -> None:
        self.arriba = arriba
        self.izquierda = izquierda
        self.es_titulo = es_titulo
        self.html = html
        self.orden = orden

    def clave(self):
        """Cómo se ordena: el título primero y después de arriba abajo.

        La posición se redondea a bandas antes de comparar. Dos cuadros que
        están «a la misma altura» casi nunca lo están al milímetro, y sin
        redondear se leerían en zigzag: el de la izquierda que está tres
        micras más abajo saldría detrás del de la derecha.
        """
        if self.es_titulo:
            return (0, 0, 0, self.orden)
        return (1, self.arriba // _BANDA, self.izquierda, self.orden)


#: Altura de la banda en la que dos cuadros cuentan como <<a la misma altura>>.
#: Va en EMU, la unidad de Office: 914400 por pulgada, así que esto es un
#: tercio de pulgada, algo menos que una línea de texto grande.
_BANDA = 300000


def _texto_pptx(elemento) -> str:
    """El texto de un cuadro de PowerPoint, con sus saltos de párrafo."""
    parrafos = []
    for parrafo in elemento.iter(_A + "p"):
        piezas = [nodo.text or "" for nodo in parrafo.iter(_A + "t")]
        # <<a:br>> es un salto de línea dentro del párrafo; se respeta, porque
        # en una diapositiva casi siempre separa dos ideas de una lista.
        texto = "".join(piezas).strip()
        if texto:
            parrafos.append(texto)
    return "\n".join(parrafos)


def _posicion_pptx(forma) -> tuple[int, int]:
    """Dónde está dibujada una forma, en las unidades de Office."""
    for desplazamiento in forma.iter(_A + "off"):
        try:
            return (int(desplazamiento.get("y", "0")),
                    int(desplazamiento.get("x", "0")))
        except (TypeError, ValueError):
            break
    return (0, 0)


def _es_titulo_pptx(forma) -> bool:
    """Dice si la forma es el marcador de título de la diapositiva."""
    for marcador in forma.iter(_P + "ph"):
        if (marcador.get("type") or "").lower() in ("title", "ctrtitle"):
            return True
    return False


def _tabla_pptx(grafico) -> str:
    """Convierte una tabla de PowerPoint en una tabla HTML."""
    filas = []
    for fila in grafico.iter(_A + "tr"):
        celdas = []
        for celda in fila.findall(_A + "tc"):
            celdas.append("<td>%s</td>" % escapar(_texto_pptx(celda)))
        if celdas:
            filas.append("<tr>%s</tr>" % "".join(celdas))
    if not filas:
        return ""
    return "<table>%s</table>" % "".join(filas)


def _lista_o_parrafos(texto: str) -> str:
    """Convierte el texto de un cuadro en párrafos o en una lista.

    Un cuadro de una diapositiva con varias líneas **es** una lista de puntos,
    aunque el archivo no la marque como tal: eso es lo que se ve en la pantalla
    y lo que hace falta oír, porque anunciar <<lista de cinco elementos>> dice de
    entrada cuánto queda.
    """
    lineas = [l.strip() for l in texto.split("\n") if l.strip()]
    if not lineas:
        return ""
    if len(lineas) == 1:
        return "<p>%s</p>" % escapar(lineas[0])
    return "<ul>%s</ul>" % "".join("<li>%s</li>" % escapar(l) for l in lineas)


class AnalizadorPPTX(Analizador):
    """Presentaciones de PowerPoint (.pptx y su variante con macros)."""

    extensiones = (".pptx", ".pptm", ".ppsx")
    descripcion = _("Presentaciones de PowerPoint")

    def analizar(self, ruta, opciones: OpcionesAnalisis):
        camino = Path(ruta)
        try:
            archivo = zipfile.ZipFile(camino)
        except (OSError, zipfile.BadZipFile) as error:
            raise ErrorFormato(_("El archivo no se puede abrir: %s") % error)
        with archivo:
            nombres = archivo.namelist()
            diapositivas = sorted(
                (n for n in nombres if _NUMERO_DIAPOSITIVA.search(n)
                 and n.startswith("ppt/slides/")),
                key=lambda n: int(_NUMERO_DIAPOSITIVA.search(n).group(1)))
            if not diapositivas:
                raise ErrorFormato(_("La presentación no tiene diapositivas."))
            secciones = []
            total = len(diapositivas)
            for numero, nombre in enumerate(diapositivas, start=1):
                opciones.progreso.paso(
                    numero - 1, total,
                    _("Leyendo la diapositiva %d de %d") % (numero, total))
                try:
                    cuerpo = self._diapositiva(archivo, nombre, numero)
                except Exception as error:
                    registrar_excepcion(
                        log, "Diapositiva ilegible: %s" % nombre, error)
                    continue
                secciones.append((nombre, cuerpo))
            metadatos = self._metadatos(archivo, camino)
        if not secciones:
            raise ErrorFormato(_("No se ha podido leer ninguna diapositiva."))
        return montar(secciones, metadatos, camino, opciones)

    def _diapositiva(self, archivo, nombre: str, numero: int) -> bytes:
        """Monta el XHTML de una diapositiva, en el orden en que se lee."""
        raiz = etree.fromstring(archivo.read(nombre),
                                    parser=crear_parser_xml())
        cuadros: list[Cuadro] = []
        titulo = ""
        for orden, forma in enumerate(raiz.iter()):
            etiqueta = forma.tag
            if etiqueta == _P + "sp":
                texto = _texto_pptx(forma)
                if not texto.strip():
                    continue
                arriba, izquierda = _posicion_pptx(forma)
                es_titulo = _es_titulo_pptx(forma)
                if es_titulo and not titulo:
                    titulo = " ".join(texto.split())
                    continue
                cuadros.append(Cuadro(arriba, izquierda, es_titulo,
                                      _lista_o_parrafos(texto), orden))
            elif etiqueta == _P + "graphicFrame":
                tabla = _tabla_pptx(forma)
                if tabla:
                    arriba, izquierda = _posicion_pptx(forma)
                    cuadros.append(Cuadro(arriba, izquierda, False, tabla, orden))
            elif etiqueta == _P + "pic":
                alterno = self._descripcion_de_imagen(forma)
                if alterno:
                    arriba, izquierda = _posicion_pptx(forma)
                    cuadros.append(Cuadro(
                        arriba, izquierda, False,
                        '<p><img src="" alt="%s"/></p>' % escapar(alterno), orden))

        cuadros.sort(key=Cuadro.clave)
        rotulo = titulo or _("Diapositiva %d") % numero
        partes = ["<h1>%s</h1>" % escapar(_("%(numero)d. %(titulo)s")
                                          % {"numero": numero, "titulo": rotulo})]
        partes.extend(cuadro.html for cuadro in cuadros)
        partes.append(self._notas(archivo, nombre))
        return ("<?xml version=\"1.0\" encoding=\"utf-8\"?>"
                "<html xmlns=\"http://www.w3.org/1999/xhtml\"><head>"
                "<meta charset=\"utf-8\"/></head><body>%s</body></html>"
                % "".join(p for p in partes if p)).encode("utf-8")

    @staticmethod
    def _descripcion_de_imagen(imagen) -> str:
        """El texto alternativo de una imagen, si lo tiene."""
        for propiedades in imagen.iter(_P + "cNvPr"):
            texto = (propiedades.get("descr") or propiedades.get("title") or "").strip()
            if texto:
                return texto
        return ""

    @staticmethod
    def _notas(archivo, nombre_diapositiva: str) -> str:
        """Las notas del ponente, que suelen ser el contenido de verdad."""
        numero = _NUMERO_DIAPOSITIVA.search(nombre_diapositiva)
        if numero is None:
            return ""
        candidato = "ppt/notesSlides/notesSlide%s.xml" % numero.group(1)
        try:
            crudo = archivo.read(candidato)
        except KeyError:
            return ""
        try:
            raiz = etree.fromstring(crudo, parser=crear_parser_xml())
        except Exception:
            return ""
        piezas = []
        for forma in raiz.iter(_P + "sp"):
            # El número de diapositiva también es un cuadro de texto de las
            # notas; se salta, o cada una acabaría diciendo su número dos veces.
            if any((m.get("type") or "").lower() == "sldnum"
                   for m in forma.iter(_P + "ph")):
                continue
            texto = _texto_pptx(forma)
            if texto.strip():
                piezas.append(texto)
        if not piezas:
            return ""
        cuerpo = "".join(_lista_o_parrafos(p) for p in piezas)
        return "<h2>%s</h2>%s" % (escapar(_("Notas")), cuerpo)

    @staticmethod
    def _metadatos(archivo, camino) -> Metadatos:
        """Título y autor de la presentación."""
        metadatos = Metadatos(titulo=camino.stem)
        try:
            crudo = archivo.read("docProps/core.xml")
        except KeyError:
            return metadatos
        try:
            raiz = etree.fromstring(crudo, parser=crear_parser_xml())
        except Exception:
            return metadatos
        for nodo in raiz:
            valor = (nodo.text or "").strip()
            if not valor:
                continue
            if nodo.tag == _DC + "title":
                metadatos.titulo = valor
            elif nodo.tag == _DC + "creator":
                metadatos.autor = valor
            elif nodo.tag == _DC + "language":
                metadatos.idioma = valor
            elif nodo.tag == _DC + "description":
                metadatos.descripcion = valor
        return metadatos

    def extraer_recurso(self, ruta, interna: str) -> bytes | None:
        try:
            with zipfile.ZipFile(Path(ruta)) as archivo:
                return archivo.read(interna)
        except (OSError, KeyError, zipfile.BadZipFile):
            return None


class AnalizadorODP(Analizador):
    """Presentaciones de LibreOffice Impress (.odp)."""

    extensiones = (".odp", ".fodp", ".otp")
    descripcion = _("Presentaciones de LibreOffice")

    def analizar(self, ruta, opciones: OpcionesAnalisis):
        camino = Path(ruta)
        archivo = abrir_odf(camino)
        with archivo:
            try:
                crudo = archivo.read("content.xml")
            except KeyError:
                raise ErrorFormato(_("El archivo no es una presentación válida."))
            raiz = etree.fromstring(crudo, parser=crear_parser_xml())
            paginas = list(raiz.iter(_DRAW + "page"))
            if not paginas:
                raise ErrorFormato(_("La presentación no tiene diapositivas."))
            secciones = []
            total = len(paginas)
            for numero, pagina in enumerate(paginas, start=1):
                opciones.progreso.paso(
                    numero - 1, total,
                    _("Leyendo la diapositiva %d de %d") % (numero, total))
                secciones.append(("diapositiva%d" % numero,
                                  self._diapositiva(pagina, numero)))
            metadatos = self._metadatos(archivo, camino)
        return montar(secciones, metadatos, camino, opciones)

    def _diapositiva(self, pagina, numero: int) -> bytes:
        """Monta el XHTML de una diapositiva de Impress."""
        cuadros: list[Cuadro] = []
        notas: list[str] = []
        titulo = ""
        for orden, marco in enumerate(pagina.iter(_DRAW + "frame")):
            if self._dentro_de_notas(marco, pagina):
                texto = self._texto_odp(marco)
                if texto.strip():
                    notas.append(texto)
                continue
            arriba, izquierda = self._posicion_odp(marco)
            tabla = self._tabla_odp(marco)
            if tabla:
                cuadros.append(Cuadro(arriba, izquierda, False, tabla, orden))
                continue
            imagen = self._imagen_odp(marco)
            if imagen:
                cuadros.append(Cuadro(arriba, izquierda, False, imagen, orden))
                continue
            texto = self._texto_odp(marco)
            if not texto.strip():
                continue
            es_titulo = (marco.get(_PRESENTATION + "class") or "") in ("title",
                                                                       "outline")
            if es_titulo and not titulo and \
                    (marco.get(_PRESENTATION + "class") or "") == "title":
                titulo = " ".join(texto.split())
                continue
            cuadros.append(Cuadro(arriba, izquierda, False,
                                  _lista_o_parrafos(texto), orden))

        cuadros.sort(key=Cuadro.clave)
        rotulo = titulo or _("Diapositiva %d") % numero
        partes = ["<h1>%s</h1>" % escapar(_("%(numero)d. %(titulo)s")
                                          % {"numero": numero, "titulo": rotulo})]
        partes.extend(cuadro.html for cuadro in cuadros)
        if notas:
            partes.append("<h2>%s</h2>" % escapar(_("Notas")))
            partes.extend(_lista_o_parrafos(n) for n in notas)
        return ("<?xml version=\"1.0\" encoding=\"utf-8\"?>"
                "<html xmlns=\"http://www.w3.org/1999/xhtml\"><head>"
                "<meta charset=\"utf-8\"/></head><body>%s</body></html>"
                % "".join(p for p in partes if p)).encode("utf-8")

    @staticmethod
    def _dentro_de_notas(marco, pagina) -> bool:
        """Dice si el marco está dentro del bloque de notas del ponente."""
        for notas in pagina.iter(_PRESENTATION + "notes"):
            for hijo in notas.iter(_DRAW + "frame"):
                if hijo is marco:
                    return True
        return False

    @staticmethod
    def _posicion_odp(marco) -> tuple[int, int]:
        """Dónde está el marco, **en las mismas unidades que PowerPoint**.

        Impress escribe las medidas con su unidad pegada —``4.5cm``,
        ``1.2in``—, así que hay que convertirlas. Y se convierten a la unidad de
        Office (914400 por pulgada) y no a la propia de Impress porque
        :data:`_BANDA` —la altura a la que dos cuadros cuentan como «a la misma
        altura»— está escrita en esa unidad, y la comparten los dos formatos.
        Con la unidad equivocada, la banda sale tan grande que la diapositiva
        entera cabe en una y los cuadros se leen de izquierda a derecha en vez
        de de arriba abajo: el pie de página, antes que el cuerpo.
        """
        def medida(valor: str) -> int:
            texto = (valor or "").strip().lower()
            factores = (("cm", 360000.0), ("mm", 36000.0), ("in", 914400.0),
                        ("pt", 12700.0), ("pc", 152400.0), ("px", 9525.0))
            for unidad, factor in factores:
                if texto.endswith(unidad):
                    try:
                        return int(float(texto[:-len(unidad)]) * factor)
                    except ValueError:
                        return 0
            try:
                return int(float(texto))
            except ValueError:
                return 0

        return (medida(marco.get(_SVG + "y", "")),
                medida(marco.get(_SVG + "x", "")))

    @staticmethod
    def _texto_odp(marco) -> str:
        """El texto de un marco, un párrafo por línea."""
        parrafos = []
        for nodo in marco.iter():
            if nodo.tag in (_TEXT + "p", _TEXT + "h"):
                texto = " ".join("".join(nodo.itertext()).split())
                if texto:
                    parrafos.append(texto)
        return "\n".join(parrafos)

    @staticmethod
    def _tabla_odp(marco) -> str:
        """La tabla que haya dentro del marco, como tabla HTML."""
        filas = []
        for tabla in marco.iter(_TABLE + "table"):
            for fila in tabla.iter(_TABLE + "table-row"):
                celdas = []
                for celda in fila.findall(_TABLE + "table-cell"):
                    celdas.append("<td>%s</td>"
                                  % escapar(" ".join("".join(celda.itertext()).split())))
                if celdas:
                    filas.append("<tr>%s</tr>" % "".join(celdas))
        if not filas:
            return ""
        return "<table>%s</table>" % "".join(filas)

    @staticmethod
    def _imagen_odp(marco) -> str:
        """La imagen del marco, si la tiene y si trae descripción."""
        for imagen in marco.iter(_DRAW + "image"):
            alterno = ""
            for nodo in marco.iter(_SVG + "desc"):
                alterno = (nodo.text or "").strip()
                break
            if not alterno:
                for nodo in marco.iter(_SVG + "title"):
                    alterno = (nodo.text or "").strip()
                    break
            if not alterno:
                alterno = (marco.get(_DRAW + "name") or "").strip()
            origen = imagen.get(_XLINK + "href", "")
            return '<p><img src="%s" alt="%s"/></p>' % (escapar(origen),
                                                        escapar(alterno))
        return ""

    @staticmethod
    def _metadatos(archivo, camino) -> Metadatos:
        """Título y autor de la presentación."""
        metadatos = Metadatos(titulo=camino.stem)
        try:
            crudo = archivo.read("meta.xml")
        except KeyError:
            return metadatos
        try:
            raiz = etree.fromstring(crudo, parser=crear_parser_xml())
        except Exception:
            return metadatos
        for nodo in raiz.iter():
            valor = (nodo.text or "").strip()
            if not valor:
                continue
            if nodo.tag == _DC + "title":
                metadatos.titulo = valor
            elif nodo.tag == _META + "initial-creator" and not metadatos.autor:
                metadatos.autor = valor
            elif nodo.tag == _DC + "creator":
                metadatos.autor = valor
            elif nodo.tag == _DC + "language":
                metadatos.idioma = valor
        return metadatos

    def extraer_recurso(self, ruta, interna: str) -> bytes | None:
        try:
            with zipfile.ZipFile(Path(ruta)) as archivo:
                return archivo.read(interna)
        except (OSError, KeyError, zipfile.BadZipFile):
            return None


registrar(AnalizadorPPTX())
registrar(AnalizadorODP())
