# -*- coding: utf-8 -*-
"""Conversión de tablas HTML a texto.

Una tabla se representa en el texto plano como filas separadas por saltos de
línea y celdas separadas por tabuladores.  Ese formato tiene dos virtudes:

* Los lectores de pantalla anuncian los tabuladores como separación de
  columnas, de modo que la tabla sigue siendo comprensible al oído.
* Es reversible: la ventana «ver tabla» puede reconstruir la rejilla a partir
  del mismo texto.

Existen dos modos de presentación, elegibles en las opciones:

* **En línea**: la tabla completa se inserta en el texto del libro.
* **Marcador**: solo se inserta ``[Tabla]: primera fila``.  Resulta cómodo
  en libros con muchas tablas de maquetación, que estorban la lectura.
"""

from __future__ import annotations

from typing import Iterator, NamedTuple

from nucleo.texto import colapsar_espacios

#: Etiquetas que agrupan filas sin ser filas ellas mismas.
_AGRUPADORES = frozenset({"thead", "tbody", "tfoot", "colgroup"})

#: Etiquetas de celda.
_CELDAS = frozenset({"td", "th"})


def nombre_local(etiqueta) -> str:
    """Devuelve el nombre de una etiqueta sin su espacio de nombres XML.

    En un EPUB las etiquetas llegan como ``{http://www.w3.org/1999/xhtml}td``;
    esta función devuelve ``td``.  Los comentarios y las instrucciones de
    proceso de lxml no tienen nombre de texto y devuelven cadena vacía.
    """
    if not isinstance(etiqueta, str):
        return ""
    if etiqueta.startswith("{"):
        etiqueta = etiqueta.rsplit("}", 1)[-1]
    return etiqueta.lower()


class TablaRenderizada(NamedTuple):
    """Resultado de convertir una tabla a texto.

    :param lineas: Líneas ya terminadas que hay que insertar en el documento.
    :param titulo: Rótulo con el que se anuncia la tabla al navegar hasta ella.
    :param filas: Rejilla completa (filas x celdas), para la ventana de tabla.
    """

    lineas: list[str]
    titulo: str
    filas: list[list[str]]


def _texto_celda(celda) -> str:
    """Texto plano de una celda, con los espacios normalizados.

    Los tabuladores y saltos de línea internos se sustituyen por espacios
    para que no rompan la rejilla de filas y columnas.
    """
    bruto = "".join(celda.itertext())
    bruto = bruto.replace("\t", " ").replace("\n", " ").replace("\r", " ")
    return colapsar_espacios(bruto).strip()


def _recorrer_filas(nodo) -> Iterator[list[str]]:
    """Recorre las filas de una tabla, sin entrar en tablas anidadas.

    Una tabla dentro de una celda no aporta filas a la rejilla exterior: su
    contenido se aplana dentro del texto de la celda que la contiene.
    """
    for hijo in nodo:
        nombre = nombre_local(hijo.tag)
        if not nombre:
            continue
        if nombre == "tr":
            yield _celdas_de_fila(hijo)
        elif nombre == "table":
            continue  # tabla anidada: sus filas pertenecen a la celda
        elif nombre in _AGRUPADORES:
            yield from _recorrer_filas(hijo)


def _celdas_de_fila(fila) -> list[str]:
    """Devuelve el texto de las celdas de una fila."""
    celdas: list[str] = []
    _acumular_celdas(fila, celdas)
    return celdas


def _acumular_celdas(nodo, destino: list[str]) -> None:
    """Busca celdas descendiendo por envoltorios, pero sin entrar en tablas anidadas."""
    for hijo in nodo:
        nombre = nombre_local(hijo.tag)
        if not nombre:
            continue
        if nombre in _CELDAS:
            destino.append(_texto_celda(hijo))
        elif nombre == "table":
            continue
        else:
            _acumular_celdas(hijo, destino)


def _titulo_explicito(tabla) -> str:
    """Texto del elemento ``<caption>`` de la tabla, si lo tiene."""
    for hijo in tabla:
        if nombre_local(hijo.tag) == "caption":
            texto = _texto_celda(hijo)
            if texto:
                return texto
    return ""


def renderizar(tabla, en_linea: bool) -> TablaRenderizada:
    """Convierte un elemento ``<table>`` de lxml a texto.

    :param tabla: Elemento ``<table>`` ya analizado.
    :param en_linea: Si ``True`` se vuelca la tabla entera; si ``False`` solo
                     se inserta un marcador con la primera fila.
    """
    filas = [celdas for celdas in _recorrer_filas(tabla)]
    titulo = _titulo_explicito(tabla)
    primera = " ".join(filas[0]).strip() if filas else ""
    if not titulo:
        titulo = primera if primera else "tabla"
    if en_linea:
        lineas = ["\t".join(celdas) for celdas in filas]
    else:
        lineas = ["[Tabla]: " + primera if primera else "[Tabla]"]
    return TablaRenderizada(lineas=lineas, titulo=titulo, filas=filas)
