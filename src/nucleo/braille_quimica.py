# -*- coding: utf-8 -*-
"""Química en braille, siguiendo la signografía de la Comisión Braille Española.

Las fórmulas químicas ya se **leen** en voz alta (:mod:`nucleo.quimica`). Lo que
faltaba era escribirlas: quien estudia química necesita el papel además del
oído, porque una reacción no se retiene escuchándola una vez, y porque en un
examen hay que escribirla.

Se sigue el **documento técnico B 6-1, «Signografía braille para química
lineal»** (Comisión Braille Española, ONCE), que es la norma en español. Está
guardado en ``adjuntos/Estudio/normas`` para poder consultarlo.

**Lo que distingue esta notación de la matemática**, y por qué no vale reutilizar
:mod:`nucleo.braille_matematicas`:

- Los subíndices numéricos **no llevan signo de subíndice**: se escriben con la
  quinta serie del braille, los mismos puntos que las diez primeras letras pero
  bajados una fila. ``H₂O`` son tres celdas de contenido, no cinco.
- Todo símbolo de elemento lleva delante el **signo de mayúscula**, aunque tenga
  dos letras: la mayúscula afecta a la primera y la segunda va sin nada.
- Las cargas van en **superíndice**, con su signo propio, detrás del número de
  átomos.

**La regla que más cuesta y sin la cual esto no se puede leer**: los números
bajos usan las mismas combinaciones de puntos que los operadores aritméticos
—el 6 bajo y el signo de sumar son los dos puntos 235—. La norma lo resuelve
exigiendo **un espacio en blanco a cada lado de todo operador y de toda
flecha**. Aquí se cumple sin excepciones: sin ese espacio, ``2H₂ + O₂`` y
``2H₂₆O₂`` se escriben igual.

Como en las matemáticas, **lo que no se sabe transcribir con seguridad se
rechaza**: se devuelve ``None`` y la fórmula se escribe hablada. Una fórmula
mal transcrita al braille es peor que una fórmula hablada, porque quien la lee
no tiene forma de saber que está mal.
"""

from __future__ import annotations

import re

from .braille import ASCII_BRAILLE
from .idioma import _
from .quimica import ELEMENTOS
from .registro import obtener_registro

log = obtener_registro(__name__)


def _puntos(*numeros: int) -> int:
    """Convierte una lista de puntos en el número que representa la celda."""
    celda = 0
    for numero in numeros:
        celda |= 1 << (numero - 1)
    return celda


BLANCO = 0

#: Signo de mayúscula: puntos 4 y 6. Va delante de cada símbolo de elemento.
MAYUSCULA = _puntos(4, 6)

#: Signo de número, para los coeficientes que van en posición normal.
NUMERO = _puntos(3, 4, 5, 6)

#: Signo de superíndice (puntos 1 y 6), con el que se escriben las cargas.
SUPERINDICE = _puntos(1, 6)

#: Signo de subíndice (puntos 3 y 4). Solo hace falta para los subíndices que
#: no son un número: ``Cₙ``, ``C₂ₙ``.
SUBINDICE = _puntos(3, 4)

#: Paréntesis auxiliares, para agrupar un subíndice de varios signos.
ABRIR_AUXILIAR = _puntos(2, 6)
CERRAR_AUXILIAR = _puntos(3, 5)

#: Paréntesis de agrupar átomos: ``(NH₄)₂SO₄``.
ABRIR_PARENTESIS = _puntos(1, 2, 6)
CERRAR_PARENTESIS = _puntos(3, 4, 5)
ABRIR_CORCHETE = _puntos(1, 2, 3, 5, 6)
CERRAR_CORCHETE = _puntos(2, 3, 4, 5, 6)

#: Las veintiséis letras, iguales en todos los braille del mundo.
LETRAS = {
    "a": _puntos(1), "b": _puntos(1, 2), "c": _puntos(1, 4), "d": _puntos(1, 4, 5),
    "e": _puntos(1, 5), "f": _puntos(1, 2, 4), "g": _puntos(1, 2, 4, 5),
    "h": _puntos(1, 2, 5), "i": _puntos(2, 4), "j": _puntos(2, 4, 5),
    "k": _puntos(1, 3), "l": _puntos(1, 2, 3), "m": _puntos(1, 3, 4),
    "n": _puntos(1, 3, 4, 5), "o": _puntos(1, 3, 5), "p": _puntos(1, 2, 3, 4),
    "q": _puntos(1, 2, 3, 4, 5), "r": _puntos(1, 2, 3, 5), "s": _puntos(2, 3, 4),
    "t": _puntos(2, 3, 4, 5), "u": _puntos(1, 3, 6), "v": _puntos(1, 2, 3, 6),
    "w": _puntos(2, 4, 5, 6), "x": _puntos(1, 3, 4, 6), "y": _puntos(1, 3, 4, 5, 6),
    "z": _puntos(1, 3, 5, 6),
}

#: Cifras en posición normal, las mismas letras de la «a» a la «j».
CIFRAS = {
    "1": LETRAS["a"], "2": LETRAS["b"], "3": LETRAS["c"], "4": LETRAS["d"],
    "5": LETRAS["e"], "6": LETRAS["f"], "7": LETRAS["g"], "8": LETRAS["h"],
    "9": LETRAS["i"], "0": LETRAS["j"],
}

#: **Cifras en posición baja**, la quinta serie: las mismas combinaciones
#: bajadas una fila, de modo que los puntos 1 y 4 pasan a ser el 2 y el 5, y el
#: 2 y el 5 pasan a ser el 3 y el 6. Es lo que se usa para los subíndices, y es
#: lo que hace que una fórmula ocupe en braille casi lo mismo que en tinta.
CIFRAS_BAJAS = {
    "1": _puntos(2), "2": _puntos(2, 3), "3": _puntos(2, 5), "4": _puntos(2, 5, 6),
    "5": _puntos(2, 6), "6": _puntos(2, 3, 5), "7": _puntos(2, 3, 5, 6),
    "8": _puntos(2, 3, 6), "9": _puntos(3, 5), "0": _puntos(3, 5, 6),
}

#: Operadores aritméticos. **Todos** llevan espacio a los dos lados, porque sus
#: puntos coinciden con los de las cifras bajas.
OPERADORES = {
    "+": _puntos(2, 3, 5),
    "-": _puntos(3, 6),
    "=": _puntos(2, 3, 5, 6),
    "·": _puntos(2, 3, 6),
    "*": _puntos(2, 3, 6),
    "/": _puntos(2, 5, 6),
}

#: Flechas de reacción, cada una de varias celdas.
FLECHAS = {
    "->": (_puntos(2, 5), _puntos(1, 2, 3, 5)),
    "→": (_puntos(2, 5), _puntos(1, 2, 3, 5)),
    "<-": (_puntos(2, 4, 5, 6), _puntos(2, 5)),
    "←": (_puntos(2, 4, 5, 6), _puntos(2, 5)),
    "<->": (_puntos(2, 4, 5, 6), _puntos(2, 5), _puntos(1, 2, 3, 5)),
    "↔": (_puntos(2, 4, 5, 6), _puntos(2, 5), _puntos(1, 2, 3, 5)),
    "⇌": (_puntos(2, 4, 5, 6), _puntos(2, 5), _puntos(1, 2, 3, 5)),
}

#: Enlaces entre átomos.
ENLACES = {
    "-": (_puntos(5), _puntos(2)),
    "=": (_puntos(5, 6), _puntos(2, 3)),
    "#": (_puntos(4, 5, 6), _puntos(1, 2, 3)),
    "≡": (_puntos(4, 5, 6), _puntos(1, 2, 3)),
}

#: Estados de la materia. Se escriben con el punto 6 delante de la abreviatura,
#: **pegados** a la fórmula y sin paréntesis: ``O₂(g)`` es ``{o;_g``.
ESTADOS = {
    "s": (_puntos(6), LETRAS["s"]),
    "l": (_puntos(6), LETRAS["l"]),
    "g": (_puntos(6), LETRAS["g"]),
    "ac": (_puntos(6), LETRAS["a"], LETRAS["c"]),
    "aq": (_puntos(6), LETRAS["a"], LETRAS["c"]),
}


class Imposible(Exception):
    """La fórmula usa algo que esta signografía no cubre con seguridad."""


#: Los trozos en que se parte una fórmula: elemento con sus índices, número,
#: operador, flecha, paréntesis, estado o espacio.
_PIEZA = re.compile(
    r"(?P<estado>\((?:s|l|g|ac|aq)\.?\))"
    r"|(?P<elemento>[A-Z][a-z]?)"
    r"|(?P<numero>\d+)"
    r"|(?P<flecha><->|->|<-|[→←↔⇌])"
    r"|(?P<enlace>≡)"
    r"|(?P<abre>[(\[])"
    r"|(?P<cierra>[)\]])"
    # La carga va **pegada** a lo que carga: en «K+» el signo es una carga, y
    # en «H2 + O2» es el operador de sumar. Lo único que los distingue es el
    # espacio de delante, y confundirlos cambia la reacción entera.
    r"|(?P<carga>\^[0-9]*[+-]|(?<=[0-9A-Za-z)\]])[+-](?=\s|$))"
    r"|(?P<operador>[+\-=·*/])"
    r"|(?P<espacio>\s+)"
)

#: Subíndices y superíndices escritos con los caracteres de Unicode.
_BAJOS = {"₀": "0", "₁": "1", "₂": "2", "₃": "3", "₄": "4", "₅": "5",
          "₆": "6", "₇": "7", "₈": "8", "₉": "9"}
_ALTOS = {"⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4", "⁵": "5",
          "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9", "⁺": "+", "⁻": "-"}


def _normalizar(formula: str) -> str:
    """Deja la fórmula con los índices escritos en llano, para poder leerla.

    Los subíndices bajos se quedan como cifras pegadas al elemento; los altos
    —que en una fórmula son siempre la carga— se marcan con un acento circunflejo
    delante, que es como se escriben cuando no hay superíndices disponibles.
    """
    salida = []
    for letra in formula or "":
        if letra in _BAJOS:
            salida.append(_BAJOS[letra])
        elif letra in _ALTOS:
            if not salida or salida[-1] != "^":
                if not (salida and salida[-1] == "^"):
                    salida.append("^")
            salida.append(_ALTOS[letra])
        else:
            salida.append(letra)
    texto = "".join(salida)
    # Dos cargas seguidas --«SO4^2^-»-- se juntan en una: «SO4^2-».
    return re.sub(r"\^(\d*)\^", r"^\1", texto)


def celdas(formula: str) -> list[int]:
    """Convierte una fórmula química en celdas braille.

    :raises Imposible: Si la fórmula usa algo que la signografía no cubre aquí.
    """
    texto = _normalizar(formula).strip()
    if not texto:
        raise Imposible("fórmula vacía")

    salida: list[int] = []
    posicion = 0
    ultimo_fue_elemento = False
    hubo_elemento = False

    while posicion < len(texto):
        encaje = _PIEZA.match(texto, posicion)
        if encaje is None:
            raise Imposible("no se entiende %r" % texto[posicion:posicion + 8])
        posicion = encaje.end()
        clase = encaje.lastgroup
        pieza = encaje.group()

        if clase == "espacio":
            if salida and salida[-1] != BLANCO:
                salida.append(BLANCO)
            ultimo_fue_elemento = False
        elif clase == "elemento":
            if pieza not in ELEMENTOS:
                raise Imposible("«%s» no es un elemento químico" % pieza)
            salida.append(MAYUSCULA)
            for letra in pieza.lower():
                salida.append(LETRAS[letra])
            ultimo_fue_elemento = True
            hubo_elemento = True
        elif clase == "numero":
            if ultimo_fue_elemento:
                # Detrás de un elemento, un número es el número de átomos: va
                # en posición baja y **sin** signo de número.
                for cifra in pieza:
                    salida.append(CIFRAS_BAJAS[cifra])
            else:
                # Delante, es el coeficiente de la molécula: posición normal.
                salida.append(NUMERO)
                for cifra in pieza:
                    salida.append(CIFRAS[cifra])
            ultimo_fue_elemento = False
        elif clase == "carga":
            salida.append(SUPERINDICE)
            for signo in pieza.lstrip("^"):
                if signo in CIFRAS:
                    salida.append(CIFRAS[signo])
                else:
                    salida.append(OPERADORES["+" if signo == "+" else "-"])
            ultimo_fue_elemento = False
        elif clase == "estado":
            salida.extend(ESTADOS[pieza.strip("().")])
            ultimo_fue_elemento = False
        elif clase == "abre":
            salida.append(ABRIR_PARENTESIS if pieza == "(" else ABRIR_CORCHETE)
            ultimo_fue_elemento = False
        elif clase == "cierra":
            salida.append(CERRAR_PARENTESIS if pieza == ")" else CERRAR_CORCHETE)
            # Detrás de un grupo cerrado también puede ir el número de átomos.
            ultimo_fue_elemento = True
        elif clase == "flecha":
            _con_espacios(salida, FLECHAS[pieza])
            ultimo_fue_elemento = False
        elif clase == "enlace":
            salida.extend(ENLACES["≡"])
            ultimo_fue_elemento = False
        elif clase == "operador":
            # **El espacio no es cosmético**: los puntos del signo de sumar son
            # los mismos que los del seis en posición baja, así que sin él
            # «2H₂ + O₂» y «2H₂₆O₂» se escribirían igual.
            _con_espacios(salida, (OPERADORES[pieza],))
            ultimo_fue_elemento = False

    if not hubo_elemento:
        raise Imposible("no hay ningún elemento químico")
    while salida and salida[-1] == BLANCO:
        salida.pop()
    return salida


def _con_espacios(salida: list[int], piezas) -> None:
    """Mete un signo dejando un blanco a cada lado, sin duplicarlos."""
    if salida and salida[-1] != BLANCO:
        salida.append(BLANCO)
    salida.extend(piezas)
    salida.append(BLANCO)


def a_brf(celdas_de_la_formula) -> str:
    """Pasa las celdas a los caracteres con los que se escribe un archivo BRF."""
    return "".join(ASCII_BRAILLE[celda] if 0 <= celda < len(ASCII_BRAILLE) else " "
                   for celda in celdas_de_la_formula or ())


def transcribir(formula: str) -> str | None:
    """Transcribe una fórmula química a braille, o devuelve ``None``.

    Es la puerta de entrada de la exportación. Devolver ``None`` no es un fallo:
    es la respuesta correcta cuando la fórmula usa algo que esta signografía no
    cubre —estructuras de dos dimensiones, configuraciones electrónicas,
    orbitales—, y entonces se escribe hablada, que se entiende.
    """
    try:
        return a_brf(celdas(formula))
    except Imposible as motivo:
        log.debug("Fórmula química no transcrita (%s): %r", motivo, formula)
        return None
    except Exception as error:                       # pragma: no cover
        log.debug("Fórmula química ilegible %r: %s", formula, error)
        return None


def descripcion() -> str:
    """Frase que explica qué se obtiene, para la ventana de opciones."""
    return _("Las fórmulas químicas se escriben con la signografía de la Comisión "
             "Braille Española (documento B 6-1). Las que usen notaciones que no "
             "cubre —estructuras dibujadas, configuraciones electrónicas— se "
             "escriben habladas.")
