# -*- coding: utf-8 -*-
"""Búsqueda de texto dentro del documento.

Admite las cuatro opciones habituales: distinguir mayúsculas, palabra
completa, expresión regular y búsqueda circular (continuar desde el otro
extremo al llegar al final).

Para la búsqueda literal sin distinción de mayúsculas se prepara **una sola
vez** una copia del texto en minúsculas y se guarda en memoria mientras dure
la sesión de búsqueda.  Convertir 30 millones de caracteres a minúsculas
cuesta unas décimas de segundo; hacerlo en cada pulsación de «Buscar
siguiente» sería inaceptable, mientras que hacerlo una vez es imperceptible.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .documento import Documento
from .idioma import _
from .registro import obtener_registro

log = obtener_registro(__name__)


@dataclass
class OpcionesBusqueda:
    """Ajustes de una búsqueda."""

    distinguir_mayusculas: bool = False
    palabra_completa: bool = False
    expresion_regular: bool = False
    circular: bool = True


@dataclass
class ResultadoBusqueda:
    """Resultado de una búsqueda.

    :param encontrado: Si se ha hallado alguna coincidencia.
    :param inicio: Posición del primer carácter de la coincidencia.
    :param fin: Posición siguiente al último carácter.
    :param dio_la_vuelta: Si la búsqueda continuó desde el otro extremo.
    :param mensaje: Texto para anunciar el resultado.
    """

    encontrado: bool = False
    inicio: int = 0
    fin: int = 0
    dio_la_vuelta: bool = False
    mensaje: str = ""


class Buscador:
    """Realiza búsquedas sucesivas sobre un documento.

    Conserva entre llamadas el texto en minúsculas y la expresión regular ya
    compilada, que son las dos preparaciones costosas.
    """

    def __init__(self, documento: Documento) -> None:
        self._documento = documento
        self._texto_minusculas: str | None = None
        self._patron: re.Pattern[str] | None = None
        self._clave_patron: tuple | None = None

    # -- preparación ---------------------------------------------------------

    def _minusculas(self) -> str:
        """Copia del texto en minúsculas, calculada la primera vez que hace falta."""
        if self._texto_minusculas is None:
            log.debug("Preparando el índice de búsqueda sin distinción de mayúsculas")
            self._texto_minusculas = self._documento.texto.lower()
        return self._texto_minusculas

    def _compilar(self, termino: str, opciones: OpcionesBusqueda) -> re.Pattern[str] | None:
        """Compila (y memoriza) la expresión regular de la búsqueda.

        :raises re.error: Si la expresión escrita por el usuario no es válida.
        """
        clave = (termino, opciones.distinguir_mayusculas, opciones.palabra_completa,
                 opciones.expresion_regular)
        if self._clave_patron == clave and self._patron is not None:
            return self._patron
        if opciones.expresion_regular:
            fuente = termino
        else:
            fuente = re.escape(termino)
        if opciones.palabra_completa:
            fuente = r"\b(?:%s)\b" % fuente
        banderas = 0 if opciones.distinguir_mayusculas else re.IGNORECASE
        self._patron = re.compile(fuente, banderas)
        self._clave_patron = clave
        return self._patron

    # -- búsqueda ------------------------------------------------------------

    def buscar(self, termino: str, desde: int, hacia_adelante: bool,
               opciones: OpcionesBusqueda) -> ResultadoBusqueda:
        """Busca la siguiente (o anterior) aparición de un término.

        :param termino: Texto o expresión regular que se busca.
        :param desde: Posición del cursor desde la que empezar.
        :param hacia_adelante: Dirección de la búsqueda.
        :param opciones: Ajustes de la búsqueda.
        """
        if not termino:
            return ResultadoBusqueda(mensaje=_("No se ha indicado qué buscar."))
        try:
            if opciones.expresion_regular or opciones.palabra_completa:
                return self._buscar_con_patron(termino, desde, hacia_adelante, opciones)
            return self._buscar_literal(termino, desde, hacia_adelante, opciones)
        except re.error as error:
            return ResultadoBusqueda(mensaje=_("La expresión regular no es válida: %s") % error)

    def _buscar_literal(self, termino: str, desde: int, hacia_adelante: bool,
                        opciones: OpcionesBusqueda) -> ResultadoBusqueda:
        """Búsqueda de texto literal, la más rápida (usa ``str.find``)."""
        if opciones.distinguir_mayusculas:
            texto = self._documento.texto
            aguja = termino
        else:
            texto = self._minusculas()
            aguja = termino.lower()
        longitud = len(aguja)
        if hacia_adelante:
            posicion = texto.find(aguja, desde + 1)
            if posicion < 0 and opciones.circular:
                posicion = texto.find(aguja, 0, desde + longitud)
                if posicion >= 0:
                    return self._exito(posicion, longitud, True, True)
        else:
            posicion = texto.rfind(aguja, 0, max(desde, 0))
            if posicion < 0 and opciones.circular:
                posicion = texto.rfind(aguja, desde)
                if posicion >= 0:
                    return self._exito(posicion, longitud, False, True)
        if posicion < 0:
            return ResultadoBusqueda(mensaje=_("No se ha encontrado «%s».") % termino)
        return self._exito(posicion, longitud, hacia_adelante, False)

    def _buscar_con_patron(self, termino: str, desde: int, hacia_adelante: bool,
                           opciones: OpcionesBusqueda) -> ResultadoBusqueda:
        """Búsqueda con expresión regular o de palabra completa."""
        patron = self._compilar(termino, opciones)
        assert patron is not None
        texto = self._documento.texto
        if hacia_adelante:
            coincidencia = patron.search(texto, max(desde + 1, 0))
            if coincidencia is None and opciones.circular:
                coincidencia = patron.search(texto, 0, max(desde + 1, 0))
                if coincidencia is not None:
                    return self._exito(coincidencia.start(),
                                       coincidencia.end() - coincidencia.start(), True, True)
        else:
            coincidencia = self._ultima_antes(patron, texto, max(desde, 0))
            if coincidencia is None and opciones.circular:
                coincidencia = self._ultima_antes(patron, texto, len(texto))
                if coincidencia is not None:
                    return self._exito(coincidencia.start(),
                                       coincidencia.end() - coincidencia.start(), False, True)
        if coincidencia is None:
            return ResultadoBusqueda(mensaje=_("No se ha encontrado «%s».") % termino)
        return self._exito(coincidencia.start(), coincidencia.end() - coincidencia.start(),
                           hacia_adelante, False)

    @staticmethod
    def _ultima_antes(patron: re.Pattern[str], texto: str, limite: int):
        """Última coincidencia que empieza antes de ``limite``.

        Las expresiones regulares de Python no saben buscar hacia atrás, así
        que se recorren las coincidencias del tramo anterior.  Para acotar el
        coste en libros muy grandes se examina el texto por bloques desde el
        final hacia el principio, y se para en cuanto uno da resultado.
        """
        bloque = 1_000_000
        fin = limite
        while fin > 0:
            inicio = max(0, fin - bloque)
            ultima = None
            for coincidencia in patron.finditer(texto, inicio, limite):
                if coincidencia.start() >= limite:
                    break
                ultima = coincidencia
            if ultima is not None:
                return ultima
            fin = inicio
        return None

    def _exito(self, inicio: int, longitud: int, hacia_adelante: bool,
               dio_la_vuelta: bool) -> ResultadoBusqueda:
        """Construye el resultado de una búsqueda con éxito."""
        documento = self._documento
        linea = documento.linea_de(inicio) + 1
        mensaje = _("Encontrado en la línea %d, %d %%.") % (linea, documento.porcentaje_en(inicio))
        if dio_la_vuelta:
            prefijo = _("Se continúa desde el principio. ") if hacia_adelante else \
                      _("Se continúa desde el final. ")
            mensaje = prefijo + mensaje
        return ResultadoBusqueda(True, inicio, inicio + longitud, dio_la_vuelta, mensaje)

    def contar(self, termino: str, opciones: OpcionesBusqueda) -> int:
        """Cuenta cuántas veces aparece un término en todo el libro."""
        if not termino:
            return 0
        try:
            if opciones.expresion_regular or opciones.palabra_completa:
                patron = self._compilar(termino, opciones)
                assert patron is not None
                return sum(1 for _ in patron.finditer(self._documento.texto))
            if opciones.distinguir_mayusculas:
                return self._documento.texto.count(termino)
            return self._minusculas().count(termino.lower())
        except re.error:
            return 0
