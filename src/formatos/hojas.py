# -*- coding: utf-8 -*-
"""Hojas de cálculo: Excel (.xlsx) y Calc (.ods).

Una tabla de datos es justo lo que el programa sabe enseñar bien: la lista de
elementos, el recorrido por filas y columnas y la lectura de una celda diciendo
a qué encabezado pertenece ya existían para las tablas de un libro. Lo único que
faltaba era la puerta de entrada.

Los dos formatos son un ZIP con XML, así que no hace falta instalar nada.

**Las cuatro decisiones que hacen que una hoja se pueda oír**, que es distinto
de que se pueda leer:

- **Cada hoja es un encabezado de nivel 1.** Un libro de Excel con seis pestañas
  es un documento con seis apartados, y así se salta entre ellos con ``H``.
- **Se recorta el rectángulo vacío.** Una hoja declara a menudo mil filas y
  veinte columnas para catorce datos. Sin recortar, la tabla que se anuncia
  tiene mil filas y hay que recorrer novecientas ochenta y seis vacías.
- **La primera fila se toma como encabezado si tiene pinta de serlo**: texto en
  todas las celdas y números debajo. Es lo que permite que al leer una celda se
  diga «Importe: 1.240» en vez de «1.240» a secas.
- **Se leen los valores, no las fórmulas.** Lo que interesa es el resultado.
  Pero cuando una celda tiene fórmula **y** el archivo no trae el resultado
  calculado, se dice la fórmula: es preferible oír «=SUMA(B2:B8)» a oír un hueco
  y creer que la celda está vacía.
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

#: Espacios de nombres de Excel.
_S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
_DC = "{http://purl.org/dc/elements/1.1/}"

#: Espacios de nombres de Calc.
_TABLE = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
_TEXT = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
_OFFICE = "{urn:oasis:names:tc:opendocument:xmlns:office:1.0}"
_META = "{urn:oasis:names:tc:opendocument:xmlns:meta:1.0}"

#: Cuántas filas se leen como mucho de una hoja. Una hoja de cien mil filas no
#: es un documento que nadie vaya a recorrer de oído; es una base de datos, y
#: cargarla entera dejaría el programa parado varios minutos para nada.
MAXIMAS_FILAS = 5000

#: Y cuántas columnas. Más allá de esto, recorrer una fila con la flecha derecha
#: deja de ser posible.
MAXIMAS_COLUMNAS = 200

#: Una referencia de celda de Excel: las letras de la columna y el número.
_REFERENCIA = re.compile(r"^([A-Z]+)(\d+)$")


def _columna_a_numero(letras: str) -> int:
    """«A» es 0, «B» es 1, «AA» es 26. Devuelve el número de columna."""
    numero = 0
    for letra in letras:
        numero = numero * 26 + (ord(letra) - ord("A") + 1)
    return numero - 1


def _recortar(filas: list[list[str]]) -> list[list[str]]:
    """Quita las filas y las columnas vacías de los bordes.

    Es lo que convierte «una tabla de mil filas» en «una tabla de catorce»: sin
    esto, el lector de pantalla anuncia el tamaño declarado y quien lo oye da
    por hecho que tiene novecientas ochenta y seis filas que recorrer.
    """
    while filas and not any(c.strip() for c in filas[-1]):
        filas.pop()
    while filas and not any(c.strip() for c in filas[0]):
        filas.pop(0)
    if not filas:
        return []
    ancho = max(len(f) for f in filas)
    for fila in filas:
        fila.extend([""] * (ancho - len(fila)))
    ultima = -1
    for numero in range(ancho):
        if any(fila[numero].strip() for fila in filas):
            ultima = numero
    primera = ancho
    for numero in range(ancho):
        if any(fila[numero].strip() for fila in filas):
            primera = numero
            break
    if ultima < primera:
        return []
    return [fila[primera:ultima + 1] for fila in filas]


def _parece_encabezado(filas: list[list[str]]) -> bool:
    """Dice si la primera fila son los nombres de las columnas.

    Se pide que **no** tenga ninguna celda vacía, que ninguna sea un número, y
    que debajo haya al menos un número: una fila de textos encima de más textos
    puede ser simplemente la primera fila de datos.
    """
    if len(filas) < 2:
        return False
    cabecera = filas[0]
    if not all(celda.strip() for celda in cabecera):
        return False
    if any(_es_numero(celda) for celda in cabecera):
        return False
    return any(_es_numero(celda) for fila in filas[1:] for celda in fila)


def _es_numero(texto: str) -> bool:
    """Dice si lo escrito en la celda es una cifra."""
    limpio = (texto or "").strip().replace(" ", "").replace(".", "").replace(",", ".")
    limpio = limpio.lstrip("-+").rstrip("%€$")
    if not limpio:
        return False
    try:
        float(limpio)
    except ValueError:
        return False
    return True


def _tabla_html(filas: list[list[str]]) -> str:
    """Convierte una rejilla de celdas en una tabla HTML de verdad."""
    if not filas:
        return "<p>%s</p>" % escapar(_("(hoja vacía)"))
    partes = ["<table>"]
    inicio = 0
    if _parece_encabezado(filas):
        partes.append("<thead><tr>%s</tr></thead>"
                      % "".join("<th>%s</th>" % escapar(c) for c in filas[0]))
        inicio = 1
    partes.append("<tbody>")
    for fila in filas[inicio:]:
        partes.append("<tr>%s</tr>"
                      % "".join("<td>%s</td>" % escapar(c) for c in fila))
    partes.append("</tbody></table>")
    return "".join(partes)


def _envolver(cuerpo: str) -> bytes:
    return ("<?xml version=\"1.0\" encoding=\"utf-8\"?>"
            "<html xmlns=\"http://www.w3.org/1999/xhtml\"><head>"
            "<meta charset=\"utf-8\"/></head><body>%s</body></html>"
            % cuerpo).encode("utf-8")


class AnalizadorXLSX(Analizador):
    """Libros de Excel (.xlsx, .xlsm)."""

    extensiones = (".xlsx", ".xlsm")
    descripcion = _("Hojas de cálculo de Excel")

    def analizar(self, ruta, opciones: OpcionesAnalisis):
        camino = Path(ruta)
        try:
            archivo = zipfile.ZipFile(camino)
        except (OSError, zipfile.BadZipFile) as error:
            raise ErrorFormato(_("El archivo no se puede abrir: %s") % error)
        with archivo:
            compartidas = self._cadenas_compartidas(archivo)
            hojas = self._hojas(archivo)
            if not hojas:
                raise ErrorFormato(_("El libro no tiene ninguna hoja."))
            secciones = []
            total = len(hojas)
            for numero, (nombre, interna) in enumerate(hojas, start=1):
                opciones.progreso.paso(numero - 1, total,
                                       _("Leyendo la hoja «%s»") % nombre)
                try:
                    filas = self._celdas(archivo, interna, compartidas)
                except Exception as error:
                    registrar_excepcion(log, "Hoja ilegible: %s" % interna, error)
                    continue
                cuerpo = "<h1>%s</h1>%s" % (escapar(nombre),
                                            _tabla_html(_recortar(filas)))
                secciones.append((interna, _envolver(cuerpo)))
            metadatos = self._metadatos(archivo, camino)
        if not secciones:
            raise ErrorFormato(_("No se ha podido leer ninguna hoja."))
        return montar(secciones, metadatos, camino, opciones)

    @staticmethod
    def _cadenas_compartidas(archivo) -> list[str]:
        """La tabla de textos que Excel guarda una sola vez y reutiliza."""
        try:
            crudo = archivo.read("xl/sharedStrings.xml")
        except KeyError:
            return []
        try:
            raiz = etree.fromstring(crudo, parser=crear_parser_xml())
        except Exception:
            return []
        salida = []
        for elemento in raiz.findall(_S + "si"):
            # Un texto puede estar partido en trozos con distinto formato; se
            # juntan, porque el formato aquí no significa nada.
            salida.append("".join(nodo.text or ""
                                  for nodo in elemento.iter(_S + "t")))
        return salida

    @staticmethod
    def _hojas(archivo) -> list[tuple[str, str]]:
        """Los nombres de las hojas y sus archivos, en el orden del libro."""
        try:
            libro = etree.fromstring(archivo.read("xl/workbook.xml"),
                                    parser=crear_parser_xml())
            relaciones_crudas = archivo.read("xl/_rels/workbook.xml.rels")
        except (KeyError, Exception):
            return []
        destinos = {}
        try:
            raiz = etree.fromstring(relaciones_crudas, parser=crear_parser_xml())
            for relacion in raiz:
                destinos[relacion.get("Id", "")] = relacion.get("Target", "")
        except Exception:
            pass
        hojas = []
        for hoja in libro.iter(_S + "sheet"):
            nombre = hoja.get("name") or _("Hoja")
            # Una hoja oculta lo está por algo —cálculos intermedios, listas de
            # validación— y meterla haría el documento más largo y más confuso.
            if (hoja.get("state") or "").lower() in ("hidden", "veryhidden"):
                continue
            destino = destinos.get(hoja.get(_R + "id", ""), "")
            if not destino:
                continue
            interna = destino if destino.startswith("xl/") else "xl/" + destino.lstrip("/")
            hojas.append((nombre, interna))
        return hojas

    @staticmethod
    def _celdas(archivo, interna: str, compartidas) -> list[list[str]]:
        """Lee una hoja y devuelve su rejilla de textos."""
        raiz = etree.fromstring(archivo.read(interna),
                                    parser=crear_parser_xml())
        filas: list[list[str]] = []
        for fila in raiz.iter(_S + "row"):
            if len(filas) >= MAXIMAS_FILAS:
                log.info("La hoja %s se corta en %d filas", interna, MAXIMAS_FILAS)
                break
            actual: list[str] = []
            for celda in fila.findall(_S + "c"):
                referencia = celda.get("r") or ""
                encaje = _REFERENCIA.match(referencia)
                if encaje is not None:
                    columna = _columna_a_numero(encaje.group(1))
                    if columna >= MAXIMAS_COLUMNAS:
                        continue
                    while len(actual) < columna:
                        actual.append("")
                actual.append(AnalizadorXLSX._valor(celda, compartidas))
            filas.append(actual)
        return filas

    @staticmethod
    def _valor(celda, compartidas) -> str:
        """Lo que hay escrito en una celda, ya resuelto."""
        tipo = celda.get("t") or "n"
        if tipo == "inlineStr":
            return "".join(nodo.text or "" for nodo in celda.iter(_S + "t"))
        valor = celda.find(_S + "v")
        if valor is not None and valor.text is not None:
            if tipo == "s":
                try:
                    return compartidas[int(valor.text)]
                except (ValueError, IndexError):
                    return ""
            if tipo == "b":
                return _("Sí") if valor.text.strip() == "1" else _("No")
            return valor.text
        formula = celda.find(_S + "f")
        if formula is not None and (formula.text or "").strip():
            # Sin resultado guardado, es mejor oír la fórmula que un hueco: un
            # hueco se entiende como <<aquí no hay nada>>, y sí lo hay.
            return "=" + formula.text.strip()
        return ""

    @staticmethod
    def _metadatos(archivo, camino) -> Metadatos:
        metadatos = Metadatos(titulo=camino.stem)
        try:
            raiz = etree.fromstring(archivo.read("docProps/core.xml"),
                                    parser=crear_parser_xml())
        except (KeyError, Exception):
            return metadatos
        for nodo in raiz:
            valor = (nodo.text or "").strip()
            if not valor:
                continue
            if nodo.tag == _DC + "title":
                metadatos.titulo = valor
            elif nodo.tag == _DC + "creator":
                metadatos.autor = valor
        return metadatos


class AnalizadorODS(Analizador):
    """Hojas de cálculo de LibreOffice Calc (.ods)."""

    extensiones = (".ods", ".fods", ".ots")
    descripcion = _("Hojas de cálculo de LibreOffice")

    def analizar(self, ruta, opciones: OpcionesAnalisis):
        camino = Path(ruta)
        archivo = abrir_odf(camino)
        with archivo:
            try:
                raiz = etree.fromstring(archivo.read("content.xml"),
                                    parser=crear_parser_xml())
            except KeyError:
                raise ErrorFormato(_("El archivo no es una hoja de cálculo válida."))
            tablas = list(raiz.iter(_TABLE + "table"))
            if not tablas:
                raise ErrorFormato(_("El libro no tiene ninguna hoja."))
            secciones = []
            total = len(tablas)
            for numero, tabla in enumerate(tablas, start=1):
                nombre = tabla.get(_TABLE + "name") or _("Hoja %d") % numero
                opciones.progreso.paso(numero - 1, total,
                                       _("Leyendo la hoja «%s»") % nombre)
                filas = self._celdas(tabla)
                cuerpo = "<h1>%s</h1>%s" % (escapar(nombre),
                                            _tabla_html(_recortar(filas)))
                secciones.append(("hoja%d" % numero, _envolver(cuerpo)))
            metadatos = self._metadatos(archivo, camino)
        return montar(secciones, metadatos, camino, opciones)

    @staticmethod
    def _celdas(tabla) -> list[list[str]]:
        """Lee una hoja de Calc deshaciendo sus repeticiones.

        Calc no escribe mil celdas vacías: escribe una diciendo «repetida mil
        veces». Hay que deshacerlo para saber en qué columna va cada dato, pero
        **con tope**: hay archivos que declaran un millón de repeticiones al
        final de la fila, y desplegarlas dejaría el programa sin memoria.
        """
        filas: list[list[str]] = []
        for fila in tabla.iter(_TABLE + "table-row"):
            if len(filas) >= MAXIMAS_FILAS:
                break
            repetir_fila = min(int(fila.get(_TABLE + "number-rows-repeated", "1") or 1),
                               MAXIMAS_FILAS)
            actual: list[str] = []
            for celda in fila:
                if celda.tag not in (_TABLE + "table-cell",
                                     _TABLE + "covered-table-cell"):
                    continue
                texto = " ".join("".join(celda.itertext()).split())
                repetir = min(int(celda.get(_TABLE + "number-columns-repeated", "1")
                                  or 1), MAXIMAS_COLUMNAS)
                if not texto and len(actual) + repetir > MAXIMAS_COLUMNAS:
                    # Relleno del final de la fila: no aporta nada.
                    break
                for _vez in range(repetir):
                    if len(actual) >= MAXIMAS_COLUMNAS:
                        break
                    actual.append(texto)
            if not any(c.strip() for c in actual):
                # Una fila vacía repetida mil veces son mil filas vacías: se
                # deja una, para que se note el hueco sin pagarlo.
                repetir_fila = 1
            for _vez in range(repetir_fila):
                if len(filas) >= MAXIMAS_FILAS:
                    break
                filas.append(list(actual))
        return filas

    @staticmethod
    def _metadatos(archivo, camino) -> Metadatos:
        metadatos = Metadatos(titulo=camino.stem)
        try:
            raiz = etree.fromstring(archivo.read("meta.xml"),
                                    parser=crear_parser_xml())
        except (KeyError, Exception):
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
        return metadatos


registrar(AnalizadorXLSX())
registrar(AnalizadorODS())
