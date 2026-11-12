# -*- coding: utf-8 -*-
"""Fórmulas matemáticas en braille, según el Código Matemático Unificado.

Hasta ahora las fórmulas se leían **habladas**: el MathML se convertía en una
frase y se oía.  Eso vale para escuchar, y no vale para estudiar.  Quien estudia
matemáticas necesita **leer la fórmula con los dedos**, volver atrás, mirar el
exponente, comparar los dos lados de la igualdad; y para eso el braille tiene
notación propia desde hace casi un siglo.

Qué se sigue
------------

El **Código Matemático Unificado para Iberoamérica** (Consejo Iberoamericano del
Braille, 2.ª edición, 2024), que es el que usan la ONCE y las imprentas braille
de los países de habla hispana.  Los signos y sus puntos están tomados
literalmente de ese documento, capítulo a capítulo:

===================  ===========  =========================================
Signo                Puntos       Dónde lo dice
===================  ===========  =========================================
Signo de número      3456         Capítulo 2.1
Coma decimal         2            Capítulo 2.3
Separador de miles   3            Capítulo 2.2
Más                  235          Capítulo 5.1
Menos                36           Capítulo 5.1
Por (aspa)           236          Capítulo 5.1
Por (punto)          6            Capítulo 5.1
Partido (barra)      256          Capítulo 5.1
Igual                2356         Capítulo 5.1
Menor / mayor        246 / 135    Capítulo 6.1
Abrir paréntesis     126          Capítulo 3.1
Cerrar paréntesis    345          Capítulo 3.1
Paréntesis auxiliar  26 / 35      Capítulo 3.1
Superíndice          16           Capítulo 4.2
Subíndice            34           Capítulo 4.2
Raíz (abre / cierra) 1246 / 156   Capítulo 5.2.2
Letra latina         5            Capítulo 2.5
===================  ===========  =========================================

Lo que **no** se transcribe, y por qué eso es lo correcto
---------------------------------------------------------

Una transcripción matemática equivocada es peor que ninguna: quien la lee no
tiene forma de saber que está mal, y se lleva a un examen una fórmula que no es
la del libro.  Por eso este módulo **se niega** —devuelve ``None``— en cuanto se
encuentra algo que no sabe representar con exactitud: integrales, sumatorios con
límites, matrices, sistemas de ecuaciones, notaciones bidimensionales.

Cuando se niega, la fórmula se escribe **hablada**, que es lo que se hacía antes
y sigue siendo verdad.  Se pierde la notación, no el contenido.

Este módulo no decide dónde se usa: recibe una fórmula y devuelve celdas
braille.  Quien exporta a BRF o a PEF las escribe con las mismas funciones que
el resto del texto.
"""

from __future__ import annotations

from .idioma import _
from .registro import obtener_registro

log = obtener_registro(__name__)


def _puntos(*numeros: int) -> int:
    """El valor de una celda a partir de los puntos que la forman.

    Es la misma numeración que usa :mod:`nucleo.braille`: el punto 1 vale 1, el
    2 vale 2, el 3 vale 4, el 4 vale 8, el 5 vale 16 y el 6 vale 32.
    """
    valor = 0
    for numero in numeros:
        valor |= 1 << (numero - 1)
    return valor


#: Celda vacía.
BLANCO = 0

#: Signo de número (3456).  Va delante de la cantidad entera, una sola vez.
NUMERO = _puntos(3, 4, 5, 6)

#: Las diez cifras, que son las diez primeras letras del alfabeto braille.
CIFRAS = {
    "1": _puntos(1), "2": _puntos(1, 2), "3": _puntos(1, 4), "4": _puntos(1, 4, 5),
    "5": _puntos(1, 5), "6": _puntos(1, 2, 4), "7": _puntos(1, 2, 4, 5),
    "8": _puntos(1, 2, 5), "9": _puntos(2, 4), "0": _puntos(2, 4, 5),
}

#: Las veintiséis letras latinas minúsculas.
LETRAS = {
    "a": _puntos(1), "b": _puntos(1, 2), "c": _puntos(1, 4), "d": _puntos(1, 4, 5),
    "e": _puntos(1, 5), "f": _puntos(1, 2, 4), "g": _puntos(1, 2, 4, 5),
    "h": _puntos(1, 2, 5), "i": _puntos(2, 4), "j": _puntos(2, 4, 5),
    "k": _puntos(1, 3), "l": _puntos(1, 2, 3), "m": _puntos(1, 3, 4),
    "n": _puntos(1, 3, 4, 5), "o": _puntos(1, 3, 5), "p": _puntos(1, 2, 3, 4),
    "q": _puntos(1, 2, 3, 4, 5), "r": _puntos(1, 2, 3, 5), "s": _puntos(2, 3, 4),
    "t": _puntos(2, 3, 4, 5), "u": _puntos(1, 3, 6), "v": _puntos(1, 2, 3, 6),
    "w": _puntos(2, 4, 5, 6), "x": _puntos(1, 3, 4, 6),
    "y": _puntos(1, 3, 4, 5, 6), "z": _puntos(1, 3, 5, 6),
}

#: Prefijo de letra latina minúscula (5).  Hace falta delante de las letras de
#: la «a» a la «j» cuando podrían confundirse con una cifra.
PREFIJO_LATINA = _puntos(5)

#: Prefijo de mayúscula en contexto matemático (46).
PREFIJO_MAYUSCULA = _puntos(4, 6)

#: Prefijo de letra griega (4).
PREFIJO_GRIEGA = _puntos(4)

#: Operadores y relaciones, con los puntos que les da el código.
OPERADORES = {
    "+": (_puntos(2, 3, 5),),
    "-": (_puntos(3, 6),),
    "−": (_puntos(3, 6),),
    "±": (_puntos(4, 5), _puntos(2, 3, 5)),
    "×": (_puntos(2, 3, 6),),
    "*": (_puntos(2, 3, 6),),
    "·": (_puntos(6),),
    "⋅": (_puntos(6),),
    "/": (_puntos(2, 5, 6),),
    "÷": (_puntos(5), _puntos(2)),
    ":": (_puntos(5), _puntos(2)),
    "=": (_puntos(2, 3, 5, 6),),
    "≠": (_puntos(4, 5), _puntos(2, 3, 5, 6)),
    "<": (_puntos(2, 4, 6),),
    ">": (_puntos(1, 3, 5),),
    "≤": (_puntos(2, 4, 6), _puntos(2, 3, 5, 6)),
    "≥": (_puntos(1, 3, 5), _puntos(2, 3, 5, 6)),
    "≈": (_puntos(5), _puntos(2, 3, 5, 6), _puntos(3)),
    "≡": (_puntos(2, 3, 5, 6), _puntos(2, 3, 5, 6)),
    ",": (_puntos(2),),
    ";": (_puntos(2, 3),),
}

#: Delimitadores.
ABRIR_PARENTESIS = _puntos(1, 2, 6)
CERRAR_PARENTESIS = _puntos(3, 4, 5)
ABRIR_CORCHETE = _puntos(1, 2, 3, 5, 6)
CERRAR_CORCHETE = _puntos(2, 3, 4, 5, 6)

#: Paréntesis auxiliares, que son propios del braille: agrupan lo que en tinta
#: agrupa la posición —el numerador de una fracción, el contenido de una raíz—
#: y que en una línea de braille no tiene dónde ponerse.
ABRIR_AUXILIAR = _puntos(2, 6)
CERRAR_AUXILIAR = _puntos(3, 5)

#: Indicadores de posición.
SUPERINDICE = _puntos(1, 6)
SUBINDICE = _puntos(3, 4)

#: Raíz: se abre con 1246, se pone el índice si lo hay, y se cierra con 156
#: antes del radicando.
ABRIR_RAIZ = _puntos(1, 2, 4, 6)
CERRAR_RAIZ = _puntos(1, 5, 6)

#: Separadores dentro de un número.
COMA_DECIMAL = _puntos(2)
SEPARADOR_MILES = _puntos(3)

#: Barra de fracción, tanto la horizontal como la oblicua.
BARRA_FRACCION = _puntos(2, 5, 6)

#: Letras griegas que aparecen en las fórmulas de un libro corriente.  Cada una
#: es el prefijo de griega más la latina que le corresponde.
GRIEGAS = {
    "α": "a", "β": "b", "γ": "g", "δ": "d", "ε": "e", "ζ": "z", "η": "h",
    "θ": "q", "ι": "i", "κ": "k", "λ": "l", "μ": "m", "ν": "n", "ξ": "x",
    "ο": "o", "π": "p", "ρ": "r", "σ": "s", "τ": "t", "υ": "u", "φ": "f",
    "χ": "c", "ψ": "y", "ω": "w",
}

#: Los tres números con nombre propio que trae el código.
ESPECIALES = {
    "π": (PREFIJO_GRIEGA, LETRAS["p"]),
    "ℯ": (LETRAS["e"],),
    "∞": (_puntos(1, 6), _puntos(1, 2, 5)),
}

#: Los puntos que impiden poner un «medio cajetín en blanco» detrás del signo
#: de multiplicar por punto: si la celda siguiente lleva alguno de ellos, hay
#: que meter una celda vacía en medio para que no se lean como una sola.
_PUNTOS_ALTOS = _puntos(1, 2, 3)


class Imposible(Exception):
    """Esta fórmula no se puede transcribir con exactitud.

    No es un error del programa: es la respuesta correcta ante una notación que
    este módulo no cubre.  Quien la reciba debe escribir la fórmula hablada.
    """


class _Salida:
    """Va acumulando celdas y sabe cuándo hace falta separarlas."""

    def __init__(self) -> None:
        self.celdas: list[int] = []
        #: Si la última celda escrita exige medio cajetín en blanco detrás.
        self._pide_hueco = False

    def poner(self, *celdas: int) -> None:
        """Añade celdas, metiendo el hueco obligatorio si hace falta."""
        for celda in celdas:
            if self._pide_hueco and (celda & _PUNTOS_ALTOS):
                self.celdas.append(BLANCO)
            self._pide_hueco = False
            self.celdas.append(celda)

    def poner_con_hueco(self, celda: int) -> None:
        """Añade una celda que exige medio cajetín en blanco a su derecha."""
        self.poner(celda)
        self._pide_hueco = True

    def __len__(self) -> int:
        return len(self.celdas)


def _bajar(celda: int) -> int:
    """Baja una celda una posición, que es como se escribe la 5.ª serie.

    El punto 1 pasa al 2, el 2 al 3, el 4 al 5 y el 5 al 6.  Las diez cifras
    solo usan esos cuatro puntos, así que la operación siempre es posible.
    """
    bajada = 0
    for arriba, abajo in ((1, 2), (2, 3), (4, 5), (5, 6)):
        if celda & _puntos(arriba):
            bajada |= _puntos(abajo)
    return bajada


def _numero(texto: str, salida: _Salida) -> None:
    """Escribe un número entero o decimal con su signo numérico delante."""
    salida.poner(NUMERO)
    for letra in texto:
        if letra in CIFRAS:
            salida.poner(CIFRAS[letra])
        elif letra in ",":
            salida.poner(COMA_DECIMAL)
        elif letra == ".":
            # En tinta el punto puede ser decimal o de millares.  El código
            # dice que el decimal se escribe siempre con el punto 2; se
            # distingue por lo que sigue: tres cifras y nada más es millares.
            salida.poner(SEPARADOR_MILES)
        elif letra in "   ":
            salida.poner(SEPARADOR_MILES)
        else:
            raise Imposible("cifra desconocida: %r" % letra)


def _letra(texto: str, salida: _Salida, en_numero: bool = False) -> None:
    """Escribe una letra latina o griega con el prefijo que le corresponda."""
    for caracter in texto:
        minuscula = caracter.lower()
        if caracter in GRIEGAS or minuscula in GRIEGAS:
            base = GRIEGAS.get(caracter) or GRIEGAS[minuscula]
            salida.poner(PREFIJO_GRIEGA, LETRAS[base])
            continue
        if minuscula not in LETRAS:
            raise Imposible("letra desconocida: %r" % caracter)
        if caracter.isupper():
            salida.poner(PREFIJO_MAYUSCULA, LETRAS[minuscula])
            continue
        # De la «a» a la «j», la letra y la cifra se escriben igual: dentro de
        # una expresión numérica hay que decir cuál es cuál.
        if en_numero and minuscula <= "j":
            salida.poner(PREFIJO_LATINA)
        salida.poner(LETRAS[minuscula])


def _es_numero(texto: str) -> bool:
    """Indica si un texto es un número escrito con cifras."""
    limpio = texto.strip()
    if not limpio:
        return False
    return all(letra in "0123456789.,   " for letra in limpio) and any(
        letra.isdigit() for letra in limpio)


# ---------------------------------------------------------------------------
# Desde MathML
# ---------------------------------------------------------------------------

#: Etiquetas de MathML que este módulo sabe transcribir.  Lo que no esté aquí
#: hace que la transcripción se niegue, que es justo lo que tiene que pasar.
CONOCIDAS = frozenset((
    "math", "mrow", "mi", "mn", "mo", "mtext", "msup", "msub", "msubsup",
    "mfrac", "msqrt", "mroot", "mfenced", "mspace", "none", "semantics",
    "mstyle", "mpadded", "mphantom",
))


def _nombre(elemento) -> str:
    """Nombre de la etiqueta, sin su espacio de nombres."""
    etiqueta = getattr(elemento, "tag", "")
    if not isinstance(etiqueta, str):
        return ""
    return etiqueta.rsplit("}", 1)[-1].lower()


def _texto(elemento) -> str:
    """El texto de un elemento hoja, sin espacios de sobra."""
    return "".join(elemento.itertext()).strip()


def _hijos(elemento) -> list:
    """Los hijos que llevan contenido."""
    return [hijo for hijo in elemento
            if _nombre(hijo) not in ("mspace", "mphantom", "none")]


def _varios_terminos(elemento) -> bool:
    """Indica si un trozo está formado por más de un término.

    Es lo que decide si hacen falta paréntesis auxiliares, y se mide por la
    **estructura** y no por el número de celdas: «x elevado a 2» son cuatro
    celdas y un solo término, y el código lo escribe sin paréntesis.  Un
    envoltorio con un único hijo no cuenta: se mira lo que hay dentro.
    """
    nombre = _nombre(elemento)
    if nombre in ("mn", "mi", "mtext", "mo"):
        return False
    hijos = _hijos(elemento)
    if len(hijos) == 1:
        return _varios_terminos(hijos[0])
    return len(hijos) > 1


def _agrupar(elemento, salida: _Salida, auxiliar: bool) -> None:
    """Escribe un trozo, entre paréntesis auxiliares si son varios términos.

    Es la regla del código: un índice o un radicando compuesto por varios
    términos se encierra entre paréntesis auxiliares, porque en una línea de
    braille no hay posición que lo agrupe.
    """
    hace_falta = auxiliar and _varios_terminos(elemento)
    if hace_falta:
        salida.poner(ABRIR_AUXILIAR)
    _escribir(elemento, salida)
    if hace_falta:
        salida.poner(CERRAR_AUXILIAR)


def _escribir(elemento, salida: _Salida) -> None:
    """Recorre un elemento de MathML escribiendo sus celdas braille."""
    nombre = _nombre(elemento)
    if nombre not in CONOCIDAS:
        raise Imposible("elemento no cubierto: %s" % nombre)

    if nombre in ("math", "mrow", "semantics", "mstyle", "mpadded"):
        for hijo in _hijos(elemento):
            _escribir(hijo, salida)
        return

    if nombre == "mn":
        texto = _texto(elemento)
        if not _es_numero(texto):
            raise Imposible("número que no se entiende: %r" % texto)
        _numero(texto, salida)
        return

    if nombre in ("mi", "mtext"):
        texto = _texto(elemento)
        if not texto:
            return
        if texto in ESPECIALES:
            salida.poner(*ESPECIALES[texto])
            return
        _letra(texto, salida)
        return

    if nombre == "mo":
        texto = _texto(elemento)
        if not texto:
            return
        if texto in ("(", "["):
            salida.poner(ABRIR_PARENTESIS if texto == "(" else ABRIR_CORCHETE)
            return
        if texto in (")", "]"):
            salida.poner(CERRAR_PARENTESIS if texto == ")" else CERRAR_CORCHETE)
            return
        if texto in ("·", "⋅"):
            salida.poner_con_hueco(_puntos(6))
            return
        celdas = OPERADORES.get(texto)
        if celdas is None:
            raise Imposible("operador no cubierto: %r" % texto)
        salida.poner(*celdas)
        return

    if nombre == "mfenced":
        salida.poner(ABRIR_PARENTESIS)
        for hijo in _hijos(elemento):
            _escribir(hijo, salida)
        salida.poner(CERRAR_PARENTESIS)
        return

    if nombre == "msup":
        partes = _hijos(elemento)
        if len(partes) != 2:
            raise Imposible("potencia mal formada")
        _escribir(partes[0], salida)
        salida.poner(SUPERINDICE)
        _agrupar(partes[1], salida, True)
        return

    if nombre == "msub":
        partes = _hijos(elemento)
        if len(partes) != 2:
            raise Imposible("subíndice mal formado")
        _escribir(partes[0], salida)
        salida.poner(SUBINDICE)
        _agrupar(partes[1], salida, True)
        return

    if nombre == "msubsup":
        partes = _hijos(elemento)
        if len(partes) != 3:
            raise Imposible("índices mal formados")
        # El orden lo fija el código: primero el subíndice y después el
        # superíndice, aunque en tinta se vean uno encima del otro.
        _escribir(partes[0], salida)
        salida.poner(SUBINDICE)
        _agrupar(partes[1], salida, True)
        salida.poner(SUPERINDICE)
        _agrupar(partes[2], salida, True)
        return

    if nombre == "mfrac":
        _fraccion(elemento, salida)
        return

    if nombre == "msqrt":
        salida.poner(ABRIR_RAIZ, CERRAR_RAIZ)
        hijos = _hijos(elemento)
        if len(hijos) == 1:
            _agrupar(hijos[0], salida, True)
        else:
            # Varios hijos sueltos bajo el trazo de la raíz son varios
            # términos, y ahí los paréntesis auxiliares son obligatorios.
            salida.poner(ABRIR_AUXILIAR)
            for hijo in hijos:
                _escribir(hijo, salida)
            salida.poner(CERRAR_AUXILIAR)
        return

    if nombre == "mroot":
        partes = _hijos(elemento)
        if len(partes) != 2:
            raise Imposible("raíz mal formada")
        salida.poner(ABRIR_RAIZ)
        _agrupar(partes[1], salida, False)
        salida.poner(CERRAR_RAIZ)
        _agrupar(partes[0], salida, True)
        return

    raise Imposible("elemento no cubierto: %s" % nombre)


def _fraccion(elemento, salida: _Salida) -> None:
    """Escribe una fracción, en su forma abreviada si es de números enteros.

    El código da dos formas.  La abreviada —numerador arriba, denominador
    abajo— es la que se usa para los números fraccionarios de toda la vida
    (``3/4``); la general, con la barra 256, sirve para cualquier otra cosa.
    Usar la abreviada cuando se puede no es un capricho: es lo que espera
    quien lee, y ocupa la mitad.
    """
    partes = _hijos(elemento)
    if len(partes) != 2:
        raise Imposible("fracción mal formada")
    arriba = _texto(partes[0])
    abajo = _texto(partes[1])
    if (_nombre(partes[0]) == "mn" and _nombre(partes[1]) == "mn"
            and arriba.isdigit() and abajo.isdigit()):
        salida.poner(NUMERO)
        for cifra in arriba:
            salida.poner(CIFRAS[cifra])
        for cifra in abajo:
            salida.poner(_bajar(CIFRAS[cifra]))
        salida.poner(BLANCO)
        return
    _agrupar(partes[0], salida, True)
    salida.poner(BARRA_FRACCION)
    _agrupar(partes[1], salida, True)


def celdas_de_mathml(elemento) -> list[int] | None:
    """Transcribe una fórmula MathML a celdas braille.

    :return: Las celdas, o ``None`` si la fórmula lleva algo que no se puede
             representar con exactitud.  Devolver ``None`` es una respuesta
             legítima y frecuente: en ese caso hay que escribir la fórmula
             hablada, que es lo que se hacía antes.
    """
    if elemento is None:
        return None
    salida = _Salida()
    try:
        _escribir(elemento, salida)
    except Imposible as motivo:
        log.info("Fórmula no transcrita a braille (%s)", motivo)
        return None
    except Exception as error:                       # pragma: no cover
        log.debug("Fallo al transcribir una fórmula: %s", error)
        return None
    return salida.celdas or None


def a_unicode(celdas) -> str:
    """Devuelve las celdas como signos braille de Unicode."""
    from .braille import UNICODE_BRAILLE

    return "".join(chr(UNICODE_BRAILLE + celda) for celda in celdas or ())


def a_brf(celdas) -> str:
    """Devuelve las celdas como caracteres de braille ASCII, para un BRF."""
    from .braille import ASCII_BRAILLE

    return "".join(ASCII_BRAILLE[celda] if 0 <= celda < len(ASCII_BRAILLE) else " "
                   for celda in celdas or ())


def transcribir(texto_mathml: str) -> str | None:
    """Transcribe una fórmula a braille ASCII a partir de su MathML.

    Es la puerta de entrada que usa la exportación: recibe el MathML que el
    programa guardó al leer el libro y devuelve la fórmula en braille, o
    ``None`` si no se puede.
    """
    if not (texto_mathml or "").strip():
        return None
    try:
        from lxml import etree

        elemento = etree.fromstring(texto_mathml.encode("utf-8"))
    except Exception as error:
        log.debug("El MathML de la fórmula no se ha podido leer: %s", error)
        return None
    celdas = celdas_de_mathml(elemento)
    return a_brf(celdas) if celdas else None


def descripcion() -> str:
    """Frase que explica qué se obtiene, para la ventana de opciones."""
    return _("Las fórmulas se escriben con el Código Matemático Unificado; las que "
             "usen notaciones que no cubre (integrales, matrices, sumatorios) se "
             "escriben habladas, como hasta ahora.")
