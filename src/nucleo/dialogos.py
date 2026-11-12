# -*- coding: utf-8 -*-
"""Reconocer quién habla en una novela, para poder leerla con dos tonos.

En una novela con mucho diálogo, oírlo todo con la misma voz obliga a
reconstruir sobre la marcha quién dice cada cosa. Quien lee con los ojos lo ve
de un vistazo: las rayas están ahí, en el margen. De oído no están.

Cambiar de tono en las líneas de diálogo es un cambio pequeño en el programa y
grande al escuchar. **Lo que tiene trabajo es reconocer una raya de diálogo sin
confundirla con un guion**, y de eso va casi todo este módulo.

Cómo se distingue, y por qué así
--------------------------------

En español el diálogo se marca con **raya** (—), no con guion (-). La raya abre
la intervención al principio del renglón y vuelve a aparecer para meter lo que
dice el narrador::

    —No pienso ir —dijo ella—. Y no insistas.

Eso da tres tramos: lo que dice el personaje, el inciso del narrador, y otra vez
el personaje. Los tres se reconocen contando rayas.

El problema es que en muchos libros —sobre todo los convertidos deprisa desde un
PDF— la raya se ha vuelto un guion corriente, y un guion al principio de un
renglón es también **una lista con viñetas**. Leer una lista de la compra con voz
de personaje es peor que no cambiar de voz en absoluto.

Así que la regla es deliberadamente prudente:

* La **raya** (—) y la **raya corta** (–) al principio del renglón son diálogo,
  sin más preguntas: en un texto en español no significan otra cosa.
* El **guion** (-) al principio del renglón solo se toma por diálogo cuando el
  documento **no usa rayas en ninguna parte** —si las usa, ese guion es otra
  cosa— y además el renglón se parece a una intervención: tiene su verbo de
  habla, o acaba en punto, en interrogación o en exclamación, y no es una de
  esas líneas cortas y sin puntuación de las que se hacen las listas.
* Dentro de una palabra, un guion nunca es diálogo. Eso ni se mira.

**Cuando hay duda, se lee como narración.** Equivocarse hacia ese lado hace que
una frase suene igual que antes; equivocarse hacia el otro pone voz de personaje
a un índice.
"""

from __future__ import annotations

import re

from .registro import obtener_registro

log = obtener_registro(__name__)

#: Los signos con los que se abre una intervención. La raya y la raya corta son
#: inequívocas; el guion solo se mira cuando el libro no usa ninguna de las dos.
RAYAS = ("—", "―", "–")

#: El guion corriente, que es el que se confunde con una viñeta de lista.
GUION = "-"

#: Verbos que delatan el inciso del narrador. No hace falta que estén —«—Vete
#: —dijo» y «—Vete —y se fue» son las dos correctas—, pero cuando están,
#: confirman que aquello era diálogo y no una lista.
VERBOS = (
    "dijo", "dije", "decía", "añadió", "añadí", "respondió", "respondí",
    "replicó", "preguntó", "pregunté", "exclamó", "murmuró", "susurró",
    "gritó", "contestó", "contesté", "insistió", "protestó", "repitió",
    "continuó", "concluyó", "asintió", "negó", "sentenció", "aclaró",
    "explicó", "advirtió", "suspiró", "rio", "rió", "afirmó", "comentó",
)

_VERBOS = re.compile(r"(?i)\b(%s)\b" % "|".join(VERBOS))

#: Longitud mínima de un renglón para que un guion inicial se tome por diálogo.
#: Las viñetas de una lista suelen ser cortas y sin verbo.
MINIMO_GUION = 25


def usa_rayas(texto: str) -> bool:
    """Dice si el documento marca sus diálogos con raya.

    Basta con mirar un trozo: si un libro usa rayas, las usa desde el primer
    capítulo. Y saberlo es lo que permite decidir qué hacer con los guiones,
    que es la única parte de verdad ambigua.
    """
    muestra = texto[:200000]
    for raya in RAYAS:
        if muestra.count(raya) >= 3:
            return True
    return False


def _parece_intervencion(renglon: str) -> bool:
    """Dice si un renglón que empieza por guion parece diálogo y no una viñeta."""
    cuerpo = renglon.lstrip(GUION).strip()
    if len(cuerpo) < MINIMO_GUION:
        return False
    if _VERBOS.search(cuerpo):
        return True
    return cuerpo.endswith((".", "?", "!", "…", "»", '"'))


def es_apertura(renglon: str, con_guiones: bool) -> bool:
    """Dice si el renglón abre una intervención de un personaje.

    :param con_guiones: Si se admite el guion corriente como raya.  Se decide
        una vez por documento con :func:`usa_rayas`, no renglón a renglón: es
        lo que evita que en el mismo libro un guion sea diálogo en una página y
        una lista en la siguiente.
    """
    limpio = renglon.lstrip()
    if not limpio:
        return False
    if limpio[0] in RAYAS:
        return True
    if con_guiones and limpio[0] == GUION:
        return _parece_intervencion(limpio)
    return False


def tramos(texto: str, con_guiones: bool = False):
    """Reparte un texto en tramos, diciendo de cada uno si es diálogo.

    Devuelve una lista de ``(texto, es_diálogo)`` en el orden en que se leen.
    Un renglón de diálogo alterna: habla el personaje, entra el narrador con su
    inciso, vuelve el personaje.  Un renglón normal sale entero como narración.

    Se trabaja renglón a renglón y no sobre el texto entero porque la raya solo
    significa «empieza a hablar alguien» **al principio de un renglón**: en
    medio de una frase es un inciso, y hay libros llenos de ellos.
    """
    salida: list[tuple[str, bool]] = []
    for numero, renglon in enumerate(texto.split("\n")):
        if numero:
            salida.append(("\n", False))
        if not es_apertura(renglon, con_guiones):
            if renglon:
                salida.append((renglon, False))
            continue
        salida.extend(_tramos_del_renglon(renglon))
    return [(trozo, dialogo) for trozo, dialogo in salida if trozo]


def _tramos_del_renglon(renglon: str):
    """Parte un renglón de diálogo en lo que dice cada uno.

    La primera raya abre al personaje; la siguiente da paso al narrador; la
    siguiente devuelve la palabra al personaje, y así.  Es exactamente lo que
    hace la vista al recorrer el margen.
    """
    signos = set(RAYAS) | {GUION}
    trozos: list[tuple[str, bool]] = []
    actual: list[str] = []
    # Se empieza **fuera** del diálogo: la primera raya es la que da la palabra
    # al personaje. Empezando dentro, todo saldría al revés.
    hablando = False
    delantera = len(renglon) - len(renglon.lstrip())
    if delantera:
        trozos.append((renglon[:delantera], False))
    for posicion, letra in enumerate(renglon[delantera:], start=delantera):
        if letra in signos and _corta_aqui(renglon, posicion, delantera):
            if actual:
                trozos.append(("".join(actual), hablando))
                actual = []
            hablando = not hablando
            continue
        actual.append(letra)
    if actual:
        trozos.append(("".join(actual), hablando))
    return trozos


def _corta_aqui(renglon: str, posicion: int, delantera: int) -> bool:
    """Dice si esa raya abre o cierra una intervención, y no es un guion.

    La primera del renglón siempre corta.  Las demás, solo si están sueltas
    —con un espacio a un lado— porque una raya pegada por los dos lados es un
    guion de una palabra compuesta, y partir ahí rompería la palabra.
    """
    if posicion == delantera:
        return True
    antes = renglon[posicion - 1] if posicion else " "
    despues = renglon[posicion + 1] if posicion + 1 < len(renglon) else " "
    return antes.isspace() or despues.isspace() or despues in ".,;:!?"


def cuantas_intervenciones(texto: str) -> int:
    """Cuántos renglones del texto abren una intervención.

    Sirve para decidir si merece la pena ofrecer el modo: en un ensayo sin
    diálogo, encenderlo no cambia nada y solo añade una opción que despista.
    """
    con_guiones = not usa_rayas(texto)
    return sum(1 for renglon in texto.split("\n")
               if es_apertura(renglon, con_guiones))


def hay_bastante_dialogo(texto: str, minimo: int = 12) -> bool:
    """Dice si el documento tiene diálogo suficiente para que el modo sirva."""
    return cuantas_intervenciones(texto) >= minimo
