# -*- coding: utf-8 -*-
"""Modelo del documento ya analizado.

Un :class:`Documento` es el resultado de analizar un libro: el texto completo,
sus marcas de estructura, el índice, la lista de páginas y los metadatos.  A
partir de aquí el formato original (EPUB, y en el futuro otros) ya no importa:
toda la aplicación trabaja con este único modelo.

El índice de líneas se calcula una sola vez al construir el documento, con una
búsqueda de saltos de línea que se ejecuta en C.  Gracias a él, responder a
«¿en qué línea estoy?» o «¿dónde empieza la línea 12.000?» es una búsqueda
binaria, no un recorrido del texto.
"""

from __future__ import annotations

import bisect
import re
from dataclasses import dataclass, field
from typing import Iterator

from .idioma import _
from .marcas import ColeccionMarcas, Marca, TipoMarca

#: Patrón usado para localizar todos los saltos de línea de una vez.
_PATRON_SALTOS = re.compile("\n")


@dataclass
class Seccion:
    """Un archivo del libro (un capítulo) situado dentro del texto global.

    :param ruta: Ruta del archivo dentro del EPUB.
    :param inicio: Posición del primer carácter de la sección.
    :param fin: Posición siguiente al último carácter de la sección.
    :param titulo: Rótulo de la sección para los anuncios de navegación.
    """

    ruta: str
    inicio: int
    fin: int
    titulo: str = ""


@dataclass
class ElementoIndice:
    """Una entrada del índice (tabla de contenidos) del libro.

    :param titulo: Texto que se muestra al usuario.
    :param posicion: Posición del texto a la que salta.
    :param referencia: Destino original tal como venía en el libro.
    :param hijos: Entradas anidadas bajo esta.
    """

    titulo: str
    posicion: int
    referencia: str = ""
    hijos: list["ElementoIndice"] = field(default_factory=list)

    def recorrer(self, profundidad: int = 0) -> Iterator[tuple["ElementoIndice", int]]:
        """Recorre esta entrada y todas sus descendientes en orden de lectura."""
        yield self, profundidad
        for hijo in self.hijos:
            yield from hijo.recorrer(profundidad + 1)


@dataclass
class Metadatos:
    """Datos descriptivos del libro, tomados del propio archivo."""

    titulo: str = ""
    autor: str = ""
    idioma: str = ""
    editorial: str = ""
    fecha: str = ""
    identificador: str = ""
    descripcion: str = ""
    #: Qué trae el archivo para poder leerse de forma accesible.  De momento lo
    #: rellena el analizador de PDF, que es donde hay algo que contar: si el
    #: documento está etiquetado, cuánto de su texto cubre la estructura y
    #: cuántas de sus imágenes llevan descripción.
    accesibilidad: str = ""
    #: Resumen SHA-256 del archivo de origen.  Es el nombre verdadero del
    #: documento: no cambia al moverlo ni al renombrarlo, y cambia en cuanto
    #: cambia su contenido.  Con él se encuentran las correcciones que el
    #: usuario haya hecho sobre este documento (:mod:`nucleo.correcciones`).
    #: Solo lo rellena el analizador de PDF, que es donde hay algo que corregir.
    huella: str = ""

    def como_lista(self) -> list[tuple[str, str]]:
        """Devuelve los metadatos no vacíos como pares (etiqueta, valor)."""
        pares = (
            (_("Título"), self.titulo),
            (_("Autor"), self.autor),
            (_("Idioma"), self.idioma),
            (_("Editorial"), self.editorial),
            (_("Fecha"), self.fecha),
            (_("Identificador"), self.identificador),
            (_("Descripción"), self.descripcion),
            (_("Accesibilidad"), self.accesibilidad),
        )
        return [(etiqueta, valor) for etiqueta, valor in pares if valor]


@dataclass
class Estadisticas:
    """Recuentos del documento, calculados solo cuando se piden."""

    palabras: int = 0
    lineas: int = 0
    caracteres: int = 0
    caracteres_sin_espacios: int = 0


class Documento:
    """Un libro analizado y listo para leer.

    :param texto: Texto plano completo del libro.
    :param marcas: Todas las marcas de estructura.
    :param indice: Árbol del índice de contenidos.
    :param paginas: Marcas de página, ya incluidas también en ``marcas``.
    :param posiciones_id: Correspondencia entre identificadores internos del
                          libro y posiciones del texto, para resolver enlaces.
    :param secciones: Tramos del texto que corresponden a cada archivo.
    :param metadatos: Datos descriptivos del libro.
    :param ruta_archivo: Ruta del archivo original en el disco.
    """

    def __init__(
        self,
        texto: str,
        marcas: list[Marca],
        indice: list[ElementoIndice] | None = None,
        posiciones_id: dict[str, int] | None = None,
        secciones: list[Seccion] | None = None,
        metadatos: Metadatos | None = None,
        ruta_archivo: str = "",
    ) -> None:
        self.texto = texto
        self.marcas = ColeccionMarcas(marcas)
        self.indice = indice or []
        self.posiciones_id = posiciones_id or {}
        self.secciones = secciones or []
        self.metadatos = metadatos or Metadatos()
        self.ruta_archivo = ruta_archivo
        self._saltos: list[int] = [c.start() for c in _PATRON_SALTOS.finditer(texto)]
        self._estadisticas: Estadisticas | None = None

    # -- longitud y líneas ---------------------------------------------------

    def __len__(self) -> int:
        return len(self.texto)

    @property
    def total_lineas(self) -> int:
        """Número de líneas del documento."""
        if not self.texto:
            return 0
        return len(self._saltos) + (0 if self.texto.endswith("\n") else 1)

    def linea_de(self, posicion: int) -> int:
        """Número de línea (empezando en 0) que contiene una posición."""
        return bisect.bisect_right(self._saltos, posicion - 1) if posicion > 0 else 0

    def inicio_de_linea(self, numero: int) -> int:
        """Posición del primer carácter de una línea."""
        if numero <= 0:
            return 0
        if numero > len(self._saltos):
            return len(self.texto)
        return self._saltos[numero - 1] + 1

    def fin_de_linea(self, numero: int) -> int:
        """Posición siguiente al último carácter de una línea (sin el salto)."""
        if numero < 0:
            return 0
        if numero >= len(self._saltos):
            return len(self.texto)
        return self._saltos[numero]

    def texto_de_linea(self, posicion: int) -> str:
        """Texto completo de la línea que contiene una posición."""
        numero = self.linea_de(posicion)
        return self.texto[self.inicio_de_linea(numero):self.fin_de_linea(numero)]

    def primera_linea_con_texto(self, posicion: int) -> str:
        """Primera línea con contenido a partir de una posición.

        Se usa al anunciar saltos de página, donde la propia posición suele
        caer en una línea vacía o en la marca de página.
        """
        numero = self.linea_de(posicion)
        for actual in range(numero, min(numero + 8, self.total_lineas)):
            contenido = self.texto[self.inicio_de_linea(actual):self.fin_de_linea(actual)].strip()
            if contenido:
                return contenido
        return ""

    def porcentaje_en(self, posicion: int) -> int:
        """Porcentaje del libro leído hasta una posición (0-100)."""
        total = len(self.texto)
        if total <= 0:
            return 0
        return max(0, min(100, round(posicion * 100 / total)))

    def posicion_de_porcentaje(self, porcentaje: float) -> int:
        """Posición correspondiente a un porcentaje del libro.

        El resultado se ajusta al principio de una línea, para no dejar el
        cursor en mitad de una palabra.
        """
        objetivo = int(len(self.texto) * max(0.0, min(100.0, porcentaje)) / 100.0)
        return self.inicio_de_linea(self.linea_de(objetivo))

    # -- secciones y páginas -------------------------------------------------

    def indice_de_pagina(self, posicion: int) -> int:
        """Índice de la página en la que está una posición (o ``-1``)."""
        return self.marcas.grupo(TipoMarca.SALTO_PAGINA).indice_actual(posicion)

    @property
    def total_paginas(self) -> int:
        """Número de páginas del libro (0 si no tiene numeración)."""
        return self.marcas.cantidad(TipoMarca.SALTO_PAGINA)

    # -- enlaces internos ----------------------------------------------------

    def resolver_referencia(self, referencia: str) -> int:
        """Traduce el destino de un enlace interno a una posición del texto.

        Acepta las tres formas que aparecen en un EPUB: ``archivo.xhtml``,
        ``archivo.xhtml#ancla`` y ``#ancla``.  Devuelve ``-1`` si el destino
        no existe en el libro (por ejemplo, un enlace a una página web).
        """
        if not referencia:
            return -1
        destino = referencia.split("#", 1)
        ruta = destino[0]
        ancla = destino[1] if len(destino) > 1 else ""
        if ancla:
            clave = "%s#%s" % (ruta, ancla) if ruta else ""
            if clave and clave in self.posiciones_id:
                return self.posiciones_id[clave]
            if ancla in self.posiciones_id:
                return self.posiciones_id[ancla]
        if ruta:
            for seccion in self.secciones:
                if seccion.ruta == ruta:
                    return seccion.inicio
            # Último recurso: comparar solo el nombre del archivo.
            nombre = ruta.rsplit("/", 1)[-1].lower()
            for seccion in self.secciones:
                if seccion.ruta.rsplit("/", 1)[-1].lower() == nombre:
                    return seccion.inicio
        return -1

    # -- estadísticas --------------------------------------------------------

    def estadisticas(self) -> Estadisticas:
        """Calcula (una sola vez) los recuentos del documento.

        El cálculo se hace bajo demanda porque recorrer 30 millones de
        caracteres, aunque sea en C, no debe retrasar la apertura del libro.
        """
        if self._estadisticas is None:
            texto = self.texto
            self._estadisticas = Estadisticas(
                palabras=len(texto.split()),
                lineas=self.total_lineas,
                caracteres=len(texto),
                caracteres_sin_espacios=len(texto) - sum(texto.count(c) for c in " \t\n"),
            )
        return self._estadisticas

    # -- índice --------------------------------------------------------------

    def indice_plano(self) -> list[tuple[ElementoIndice, int]]:
        """Devuelve el índice como lista plana de (entrada, profundidad)."""
        resultado: list[tuple[ElementoIndice, int]] = []
        for raiz in self.indice:
            resultado.extend(raiz.recorrer())
        return resultado
