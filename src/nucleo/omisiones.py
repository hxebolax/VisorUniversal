# -*- coding: utf-8 -*-
"""Lo que no se quiere oír al leer un libro de un tirón.

Escuchar un libro entero no es lo mismo que leerlo.  Con la vista, el ojo se
salta solo la cabecera que se repite en cada página, el número de página del
pie y el numerito volado de una nota: están ahí, se ven, y no se leen.  De
oído no hay forma de saltárselos: **todo suena, y suena en medio de la frase**.

    «...el ejército cruzó el río 47 Guerra y paz, capítulo tercero 212 sin
    encontrar resistencia...»

Ahí dentro hay una llamada de nota, la cabecera de la página siguiente y el
número de página.  Ninguna de las tres se quería oír.

Este módulo decide **qué tramos del texto no se dicen** durante la lectura
continua.  Tres cosas, cada una con su casilla, porque no todo el mundo quiere
lo mismo: quien estudia sí quiere oír las llamadas de nota.

Qué se salta y cómo se reconoce
-------------------------------

**Las llamadas de nota.**  Es lo fácil y lo seguro: el conversor ya las marca
una a una (:data:`~nucleo.marcas.TipoMarca.NOTA_PIE`), así que se sabe
exactamente dónde empieza y acaba cada una.  Se salta **la llamada**, no el
texto de la nota: la nota está al final del capítulo, se lee cuando toca, y
saltársela sería esconder contenido del libro.

**Los números de página sueltos.**  Una línea que no es más que un número —o un
número romano, o «- 47 -»— es el folio impreso.  Se exige que la línea entera
sea eso: una línea que empiece por un número no se toca, porque puede ser un
elemento de lista o un año.

**Las cabeceras y los pies que se repiten.**  Es lo único que tiene algo de
trabajo, y se hace sin adivinar: se miran las **dos primeras y las dos últimas
líneas de cada página** —que es donde van las cabeceras y los pies, y en ningún
otro sitio— y se cuenta cuántas veces se repite cada texto.  Lo que aparece en
al menos un tercio de las páginas es una cabecera; lo que aparece dos veces es
una casualidad.

Esa comprobación **necesita que el documento tenga marcas de página**, o sea,
que sea un PDF o un libro que las traiga.  En un EPUB sin páginas no se hace
nada, y es lo correcto: sin páginas no hay cabeceras que se repitan.

Lo que no se toca nunca
-----------------------

Nada de esto cambia el texto del libro.  Se ve entero, se busca entero, se
copia entero y se exporta entero: lo único que cambia es **lo que la voz dice**,
igual que el diccionario de pronunciación.  Y por eso mismo, si alguna vez se
salta algo que no debía, basta con leerlo con las flechas para tenerlo delante.
"""

from __future__ import annotations

import re

from .marcas import TipoMarca, es_encabezado
from .registro import obtener_registro

log = obtener_registro(__name__)

#: Una línea que es solo el folio: cifras o números romanos, con la
#: decoración habitual de guiones, barras y puntos alrededor.
_SOLO_FOLIO = re.compile(
    r"^[\s\-–—·.|\[\(]*(?:\d{1,4}|[ivxlcdmIVXLCDM]{1,7})[\s\-–—·.|\]\)]*$")

#: Una línea de folio con su rótulo delante: «Página 47», «Pág. 47 de 300».
_FOLIO_CON_ROTULO = re.compile(
    r"^\s*(?:p[aá]g(?:ina)?\.?|page|p\.)\s*\d{1,4}(?:\s*(?:de|of|/)\s*\d{1,4})?\s*$",
    re.IGNORECASE)

#: Cuántas líneas del principio y del final de cada página se miran buscando
#: cabeceras y pies repetidos.  Dos por cada lado: hay libros con la cabecera
#: en dos renglones (el título del libro y el del capítulo).
LINEAS_DE_BORDE = 2

#: Proporción de páginas en las que tiene que salir un texto para tomarlo por
#: cabecera.  Un tercio deja fuera lo que solo sale en una parte del libro y
#: recoge las cabeceras aunque el prólogo y los anexos lleven otra distinta.
PROPORCION_REPETIDO = 0.3

#: Repeticiones mínimas, pase lo que pase con la proporción.  En un documento
#: de cuatro páginas, un tercio es una página y media: sin este mínimo,
#: cualquier línea repetida dos veces se tomaría por cabecera.
REPETICIONES_MINIMAS = 4

#: Largo máximo de una cabecera.  Un párrafo entero repetido no es una
#: cabecera: es una cita, un estribillo o un error del documento, y en
#: cualquiera de los tres casos hay que leerlo.
LARGO_MAXIMO = 90


class Omisiones:
    """Los tramos de texto que la voz no va a decir.

    Se calcula **una vez por documento** —recorrerlo entero en cada frase sería
    absurdo— y se consulta con :meth:`filtrar`, que es lo que se llama en cada
    frase que se dice.

    :param documento: Documento abierto.
    :param notas: Si se saltan las llamadas de nota al pie.
    :param paginas: Si se saltan los números de página sueltos.
    :param repetidos: Si se saltan las cabeceras y los pies que se repiten.
    """

    __slots__ = ("tramos", "_inicios", "cabeceras")

    def __init__(self, documento=None, notas: bool = False, paginas: bool = False,
                 repetidos: bool = False) -> None:
        #: Tramos ``(inicio, fin)`` que no se dicen, ordenados y sin solaparse.
        self.tramos: list[tuple[int, int]] = []
        #: Los textos que se han tomado por cabecera, para poder contarlo.
        self.cabeceras: list[str] = []
        if documento is None or not (notas or paginas or repetidos):
            self._inicios: list[int] = []
            return

        crudos: list[tuple[int, int]] = []
        if notas:
            crudos += self._tramos_de_notas(documento)
        if paginas or repetidos:
            crudos += self._tramos_de_lineas(documento, paginas, repetidos)
        self.tramos = _fundir(crudos)
        self._inicios = [inicio for inicio, _fin in self.tramos]
        if self.tramos:
            log.info("Lectura en voz alta: se saltan %d tramos (%d cabeceras distintas)",
                     len(self.tramos), len(self.cabeceras))

    def __bool__(self) -> bool:
        """Indica si hay algo que saltarse."""
        return bool(self.tramos)

    # -- cálculo -------------------------------------------------------------

    @staticmethod
    def _tramos_de_notas(documento) -> list[tuple[int, int]]:
        """Las llamadas de nota, tal como las dejó marcadas el conversor."""
        salida = []
        for marca in documento.marcas.grupo(TipoMarca.NOTA_PIE).marcas:
            largo = max(marca.longitud, len((marca.texto or "").strip()))
            if largo > 0:
                salida.append((marca.posicion, marca.posicion + largo))
        return salida

    def _tramos_de_lineas(self, documento, paginas: bool,
                          repetidos: bool) -> list[tuple[int, int]]:
        """Recorre las líneas del documento decidiendo cuáles no se dicen."""
        texto = documento.texto
        encabezados = self._posiciones_de_encabezado(documento)
        repetidas = (self._cabeceras_repetidas(documento) if repetidos else set())
        self.cabeceras = sorted(repetidas)

        salida = []
        posicion = 0
        largo = len(texto)
        while posicion < largo:
            final = texto.find("\n", posicion)
            if final < 0:
                final = largo
            linea = texto[posicion:final]
            limpia = linea.strip()
            if limpia and posicion not in encabezados:
                if paginas and _es_folio(limpia):
                    salida.append((posicion, final))
                elif repetidas and limpia in repetidas:
                    salida.append((posicion, final))
            posicion = final + 1
        return salida

    @staticmethod
    def _posiciones_de_encabezado(documento) -> set:
        """Dónde empiezan los encabezados, para no saltárselos nunca.

        Un capítulo titulado «7» existe, y saltárselo por parecer un folio
        dejaría al oyente sin saber que ha cambiado de capítulo.
        """
        return {marca.posicion for marca in documento.marcas.encabezados.marcas
                if es_encabezado(marca.tipo)}

    @staticmethod
    def _cabeceras_repetidas(documento) -> set:
        """Textos que salen al principio o al final de casi todas las páginas."""
        paginas = documento.marcas.grupo(TipoMarca.SALTO_PAGINA).marcas
        if len(paginas) < REPETICIONES_MINIMAS:
            return set()
        texto = documento.texto
        cortes = [marca.posicion for marca in paginas] + [len(texto)]

        cuenta: dict[str, int] = {}
        for numero in range(len(cortes) - 1):
            trozo = texto[cortes[numero]:cortes[numero + 1]]
            lineas = [linea.strip() for linea in trozo.split("\n") if linea.strip()]
            if not lineas:
                continue
            bordes = lineas[:LINEAS_DE_BORDE] + lineas[-LINEAS_DE_BORDE:]
            for linea in set(bordes):
                if len(linea) <= LARGO_MAXIMO:
                    cuenta[linea] = cuenta.get(linea, 0) + 1

        falta = max(REPETICIONES_MINIMAS,
                    int(len(cortes[:-1]) * PROPORCION_REPETIDO))
        return {linea for linea, veces in cuenta.items() if veces >= falta}

    # -- uso -----------------------------------------------------------------

    def filtrar(self, texto: str, inicio: int) -> str:
        """Devuelve el tramo de texto sin lo que no se dice.

        :param texto: El texto tal cual, sacado del documento.
        :param inicio: Posición absoluta en la que empieza ``texto``.
        """
        if not self.tramos or not texto:
            return texto
        import bisect

        fin = inicio + len(texto)
        # Se empieza en el primer tramo que puede alcanzar a este trozo.
        primero = max(bisect.bisect_left(self._inicios, inicio) - 1, 0)
        piezas = []
        cursor = inicio
        for indice in range(primero, len(self.tramos)):
            desde, hasta = self.tramos[indice]
            if desde >= fin:
                break
            if hasta <= cursor:
                continue
            if desde > cursor:
                piezas.append(texto[cursor - inicio:desde - inicio])
            cursor = max(cursor, min(hasta, fin))
        if cursor < fin:
            piezas.append(texto[cursor - inicio:])
        return "".join(piezas)


def _es_folio(linea: str) -> bool:
    """Indica si una línea es solo el número de página."""
    if len(linea) > 30:
        return False
    return bool(_SOLO_FOLIO.match(linea) or _FOLIO_CON_ROTULO.match(linea))


def _fundir(tramos: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Ordena los tramos y junta los que se solapan o se tocan."""
    if not tramos:
        return []
    ordenados = sorted(t for t in tramos if t[1] > t[0])
    salida = [ordenados[0]]
    for inicio, fin in ordenados[1:]:
        ultimo_inicio, ultimo_fin = salida[-1]
        if inicio <= ultimo_fin:
            salida[-1] = (ultimo_inicio, max(ultimo_fin, fin))
        else:
            salida.append((inicio, fin))
    return salida


#: Unas omisiones que no omiten nada.  Ahorra comprobar si hay o no antes de
#: usarlas, que es lo que llena de condiciones el sitio donde se lee.
NINGUNA = Omisiones()
