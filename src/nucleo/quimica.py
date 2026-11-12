# -*- coding: utf-8 -*-
"""Fórmulas químicas dichas en voz alta.

Las matemáticas ya se leían: el MathML se convierte en una frase y se puede
recorrer con ``E``.  La química no.  Una fórmula como ``H2SO4`` sale del
documento como texto suelto y el sintetizador la dice «hache dos ese o cuatro»
—cuando no «hache dos sooo cuatro»—, y ahí se acaba la clase de química.

El problema no es de este programa: es que el símbolo químico y la letra se
escriben igual.  Un lector de pantalla no tiene forma de saber que esa O es
oxígeno y no la letra o, ni que ese ``2`` iba en subíndice.  Lo que sí se puede
saber es que **el conjunto entero** se descompone en símbolos de la tabla
periódica, y esa es la comprobación que se hace aquí.

Qué se lee y cómo
-----------------

Se ofrecen dos formas de decirlo porque hay dos lectores distintos:

``nombres``
    ``H2SO4`` se dice «hidrógeno 2 azufre oxígeno 4».  Es lo que dicta un
    profesor en clase y **no tiene ambigüedad al oírlo**: la letra O y el
    número cero suenan igual, «oxígeno» no se confunde con nada.  Es lo que
    viene puesto.

``simbolos``
    ``H2SO4`` se dice «hache 2 ese o 4», deletreado con separaciones claras.
    Lo prefiere quien ya se sabe la tabla y quiere oír la fórmula tal como se
    escribe, para copiarla.

Además se leen los signos que acompañan a una fórmula y que, sueltos, no dicen
nada: la carga de un ion (``Na+`` → «catión sodio»), el estado de agregación
(``(ac)`` → «en disolución acuosa»), la flecha de reacción (``→`` → «da»
y ``⇌`` → «en equilibrio con») y el punto de los hidratos.

Por qué se exige un número
--------------------------

Aquí hay una decisión importante y deliberada.  Muchas palabras corrientes se
descomponen en símbolos químicos: «con» es C + O + N, «sin» es S + In, «no» es
N + O.  Leer «con» como «carbono oxígeno nitrógeno» en mitad de una novela
sería mucho peor que no leer bien una fórmula en un libro de química.

Por eso **solo se toma por fórmula lo que trae un número, una carga o un estado
de agregación**, que es lo que ninguna palabra normal lleva.  Las poquísimas
fórmulas comunes que no llevan número —``NaCl``, ``NaOH``…— se listan una a una
en :data:`SIN_NUMERO`; es una lista corta y revisada a mano, no una regla.

Nada de esto toca el texto del libro: se aplica **solo a lo que se dice**, igual
que el diccionario de pronunciación.  Lo que se ve, se copia y se busca sigue
siendo exactamente lo que escribió el autor.
"""

from __future__ import annotations

import re

from .idioma import _

#: Cómo se dice cada elemento.  Están los 118, porque dejarse los del final
#: obligaría a explicar por qué el berkelio no se lee y el bario sí.
ELEMENTOS = {
    "H": _("hidrógeno"), "He": _("helio"), "Li": _("litio"), "Be": _("berilio"),
    "B": _("boro"), "C": _("carbono"), "N": _("nitrógeno"), "O": _("oxígeno"),
    "F": _("flúor"), "Ne": _("neón"), "Na": _("sodio"), "Mg": _("magnesio"),
    "Al": _("aluminio"), "Si": _("silicio"), "P": _("fósforo"), "S": _("azufre"),
    "Cl": _("cloro"), "Ar": _("argón"), "K": _("potasio"), "Ca": _("calcio"),
    "Sc": _("escandio"), "Ti": _("titanio"), "V": _("vanadio"), "Cr": _("cromo"),
    "Mn": _("manganeso"), "Fe": _("hierro"), "Co": _("cobalto"), "Ni": _("níquel"),
    "Cu": _("cobre"), "Zn": _("cinc"), "Ga": _("galio"), "Ge": _("germanio"),
    "As": _("arsénico"), "Se": _("selenio"), "Br": _("bromo"), "Kr": _("kriptón"),
    "Rb": _("rubidio"), "Sr": _("estroncio"), "Y": _("itrio"), "Zr": _("circonio"),
    "Nb": _("niobio"), "Mo": _("molibdeno"), "Tc": _("tecnecio"), "Ru": _("rutenio"),
    "Rh": _("rodio"), "Pd": _("paladio"), "Ag": _("plata"), "Cd": _("cadmio"),
    "In": _("indio"), "Sn": _("estaño"), "Sb": _("antimonio"), "Te": _("telurio"),
    "I": _("yodo"), "Xe": _("xenón"), "Cs": _("cesio"), "Ba": _("bario"),
    "La": _("lantano"), "Ce": _("cerio"), "Pr": _("praseodimio"), "Nd": _("neodimio"),
    "Pm": _("prometio"), "Sm": _("samario"), "Eu": _("europio"), "Gd": _("gadolinio"),
    "Tb": _("terbio"), "Dy": _("disprosio"), "Ho": _("holmio"), "Er": _("erbio"),
    "Tm": _("tulio"), "Yb": _("iterbio"), "Lu": _("lutecio"), "Hf": _("hafnio"),
    "Ta": _("tantalio"), "W": _("wolframio"), "Re": _("renio"), "Os": _("osmio"),
    "Ir": _("iridio"), "Pt": _("platino"), "Au": _("oro"), "Hg": _("mercurio"),
    "Tl": _("talio"), "Pb": _("plomo"), "Bi": _("bismuto"), "Po": _("polonio"),
    "At": _("ástato"), "Rn": _("radón"), "Fr": _("francio"), "Ra": _("radio"),
    "Ac": _("actinio"), "Th": _("torio"), "Pa": _("protactinio"), "U": _("uranio"),
    "Np": _("neptunio"), "Pu": _("plutonio"), "Am": _("americio"), "Cm": _("curio"),
    "Bk": _("berkelio"), "Cf": _("californio"), "Es": _("einstenio"), "Fm": _("fermio"),
    "Md": _("mendelevio"), "No": _("nobelio"), "Lr": _("lawrencio"),
    "Rf": _("rutherfordio"), "Db": _("dubnio"), "Sg": _("seaborgio"),
    "Bh": _("bohrio"), "Hs": _("hasio"), "Mt": _("meitnerio"),
    "Ds": _("darmstadtio"), "Rg": _("roentgenio"), "Cn": _("copernicio"),
    "Nh": _("nihonio"), "Fl": _("flerovio"), "Mc": _("moscovio"),
    "Lv": _("livermorio"), "Ts": _("teneso"), "Og": _("oganesón"),
}

#: Cómo se deletrea cada símbolo cuando se pide oírlos como letras.  El punto
#: y el espacio detrás de cada letra son lo que hace que el sintetizador las
#: separe en vez de leerlas como una palabra inventada.
_LETRAS = {
    "A": _("a"), "B": _("be"), "C": _("ce"), "D": _("de"), "E": _("e"),
    "F": _("efe"), "G": _("ge"), "H": _("hache"), "I": _("i"), "J": _("jota"),
    "K": _("ka"), "L": _("ele"), "M": _("eme"), "N": _("ene"), "O": _("o"),
    "P": _("pe"), "Q": _("cu"), "R": _("erre"), "S": _("ese"), "T": _("te"),
    "U": _("u"), "V": _("uve"), "W": _("uve doble"), "X": _("equis"),
    "Y": _("i griega"), "Z": _("zeta"),
}

#: Fórmulas de uso diario que no llevan ningún número y que, aun así, se leen
#: como fórmulas.  La lista es corta y está revisada a mano justamente porque
#: es la excepción a la regla que evita los falsos positivos: cada entrada que
#: se añada aquí es una palabra que dejará de leerse como palabra.
SIN_NUMERO = frozenset((
    "NaCl", "KCl", "HCl", "HBr", "NaOH", "KOH", "LiOH", "CaO", "MgO", "ZnO",
    "CuO", "FeS", "AgCl", "NaF", "KI", "CaS", "HgS", "PbS", "SiC",
))

#: Subíndices y superíndices escritos con los caracteres propios de Unicode,
#: que es como salen de un PDF bien hecho.  Se pasan a cifras normales antes de
#: analizar: por dentro todo se trata igual venga como venga.
_SUBINDICES = str.maketrans("₀₁₂₃₄₅₆₇₈₉₊₋", "0123456789+-")
_SUPERINDICES = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻", "0123456789+-")

#: Flechas de reacción y cómo se dicen.
FLECHAS = {
    "→": _(" da "),
    "⟶": _(" da "),
    "->": _(" da "),
    "=>": _(" da "),
    "⇌": _(" en equilibrio con "),
    "⇄": _(" en equilibrio con "),
    "↔": _(" en equilibrio con "),
    "<->": _(" en equilibrio con "),
    "↑": _(" se desprende "),
    "↓": _(" precipita "),
}

#: Estados de agregación, tal como se escriben entre paréntesis detrás de una
#: fórmula.  Sin traducir suenan a error de lectura: «hache dos o paréntesis
#: ele» no se entiende.
ESTADOS = {
    "s": _(" en estado sólido"),
    "l": _(" en estado líquido"),
    "g": _(" en estado gaseoso"),
    "ac": _(" en disolución acuosa"),
    "aq": _(" en disolución acuosa"),
    "aq.": _(" en disolución acuosa"),
}

#: Un candidato a fórmula: letras, cifras, paréntesis, corchetes, cargas y el
#: punto de los hidratos.  Tiene que empezar por mayúscula o por una cifra de
#: coeficiente, que es como se escribe siempre una fórmula.
_CANDIDATO = re.compile(
    r"(?<![A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9])"
    r"([A-Z][A-Za-z0-9()\[\]·.]*(?:\^?[0-9]*[+-])?)"
    r"(?![A-Za-zÁÉÍÓÚÜÑáéíóúüñ])")

#: El estado de agregación escrito pegado al final de una fórmula.
_ESTADO_PEGADO = re.compile(r"\((s|l|g|ac|aq)\)$", re.IGNORECASE)

#: Un símbolo de elemento dentro de la fórmula: mayúscula y, como mucho, una
#: minúscula detrás.
_SIMBOLO = re.compile(r"[A-Z][a-z]?")

#: Modos en los que se puede leer la química, para la lista de opciones.
MODOS = ("auto", "nombres", "simbolos", "no")


def modos() -> list[tuple[str, str]]:
    """``(clave, texto)`` de cada forma de leer, para la lista de opciones."""
    return [
        ("auto", _("Automático: solo en los documentos que traen química")),
        ("nombres", _("Decir el nombre de cada elemento: «hidrógeno 2 azufre oxígeno 4»")),
        ("simbolos", _("Deletrear los símbolos: «hache 2 ese o 4»")),
        ("no", _("No tocar nada: leerlas como texto corriente")),
    ]


#: Una carga escrita con caracteres de superíndice: «SO₄²⁻».  Se reconoce
#: **antes** de pasarlo todo a cifras normales, porque una vez convertido ya no
#: hay forma de distinguir el 2 de la carga del 2 de un subíndice, y la
#: diferencia no es menor: uno cuenta átomos y el otro cuenta cargas.
_CARGA_ALTA = re.compile(r"([\u2070\u00b9\u00b2\u00b3\u2074-\u2079]*)([\u207a\u207b])")


def _sin_indices(texto: str) -> str:
    """Pasa a cifras normales los subíndices y superíndices de Unicode.

    La carga en superíndice se reescribe con el acento circunflejo delante
    —``SO₄²⁻`` pasa a ``SO4^2-``— para que el analizador sepa que ese número
    son cargas y no átomos.
    """
    def carga(coincidencia):
        numero = coincidencia.group(1).translate(_SUPERINDICES)
        signo = coincidencia.group(2).translate(_SUPERINDICES)
        return "^%s%s" % (numero, signo)

    marcado = _CARGA_ALTA.sub(carga, texto)
    return marcado.translate(_SUBINDICES).translate(_SUPERINDICES)


class _Analisis:
    """Lo que se ha entendido de un candidato a fórmula."""

    __slots__ = ("piezas", "numeros", "carga")

    def __init__(self) -> None:
        #: Trozos ya dichos, en orden.
        self.piezas: list[str] = []
        #: Si ha aparecido algún subíndice, que es lo que distingue una fórmula
        #: de una palabra que por casualidad se descompone en símbolos.
        self.numeros = False
        #: Si trae carga eléctrica.
        self.carga = False


def _analizar(texto: str, modo: str) -> _Analisis | None:
    """Descompone un candidato.  Devuelve ``None`` si no es una fórmula.

    Se exige que **todo** el texto se descomponga: basta un carácter que no
    encaje para descartarlo entero.  Es lo que impide que «Alberto» se lea como
    aluminio, berilio y torio: la «o» final sobra y tira toda la lectura.
    """
    analisis = _Analisis()
    posicion = 0
    largo = len(texto)
    while posicion < largo:
        caracter = texto[posicion]

        if caracter in "([":
            analisis.piezas.append(_(" abre paréntesis "))
            posicion += 1
            continue
        if caracter in ")]":
            analisis.piezas.append(_(" cierra paréntesis "))
            posicion += 1
            continue
        if caracter in "·.":
            # El punto de los hidratos: CuSO4·5H2O.  Un punto final de frase no
            # llega hasta aquí porque el candidato se recorta antes.
            analisis.piezas.append(_(" con "))
            posicion += 1
            continue
        if caracter in "+-":
            analisis.carga = True
            analisis.piezas.append(_(" con carga positiva")
                                   if caracter == "+" else _(" con carga negativa"))
            posicion += 1
            continue
        if caracter == "^":
            # Lo que va detrás del acento circunflejo es la carga, no un
            # subíndice: en «SO4^2-» ese 2 son dos cargas negativas, y decirlo
            # como si fueran dos átomos cambiaría la fórmula.
            posicion += 1
            numero = ""
            while posicion < largo and texto[posicion].isdigit():
                numero += texto[posicion]
                posicion += 1
            if posicion < largo and texto[posicion] in "+-":
                analisis.carga = True
                signo = _("positiva") if texto[posicion] == "+" else _("negativa")
                analisis.piezas.append(_(" con carga %(cuanta)s %(signo)s")
                                       % {"cuanta": numero or "1", "signo": signo})
                posicion += 1
            elif numero:
                analisis.numeros = True
                analisis.piezas.append(" %s" % numero)
            continue
        if caracter.isdigit():
            numero = ""
            while posicion < largo and texto[posicion].isdigit():
                numero += texto[posicion]
                posicion += 1
            # Un número al principio es el coeficiente de la ecuación —«2 H2O»
            # son dos moléculas—, y se dice como tal.
            if not analisis.piezas:
                analisis.piezas.append("%s " % numero)
            else:
                analisis.numeros = True
                analisis.piezas.append(" %s" % numero)
            continue

        coincidencia = _SIMBOLO.match(texto, posicion)
        if coincidencia is None:
            return None
        simbolo = coincidencia.group(0)
        if simbolo not in ELEMENTOS:
            # Puede que la minúscula no fuera parte del símbolo: «Hg» es
            # mercurio, pero en «Ho» de una fórmula rara podría ser H seguido
            # de algo.  Se prueba con la mayúscula sola antes de rendirse.
            if len(simbolo) == 2 and simbolo[0] in ELEMENTOS:
                simbolo = simbolo[0]
            else:
                return None
        analisis.piezas.append(_decir_simbolo(simbolo, modo))
        posicion += len(simbolo)

    if not analisis.piezas:
        return None
    return analisis


def _decir_simbolo(simbolo: str, modo: str) -> str:
    """Dice un símbolo, con el nombre del elemento o deletreado."""
    if modo == "simbolos":
        letras = [_LETRAS.get(letra.upper(), letra) for letra in simbolo]
        return " %s" % " ".join(letras)
    return " %s" % ELEMENTOS.get(simbolo, simbolo)


def _es_ion(texto: str) -> str:
    """Devuelve «catión» o «anión» si el texto acaba en carga, o cadena vacía."""
    limpio = texto.rstrip()
    if limpio.endswith("+"):
        return _("catión")
    if limpio.endswith("-"):
        return _("anión")
    return ""


def formula_a_texto(formula: str, modo: str = "nombres") -> str | None:
    """Convierte una fórmula suelta en la frase con la que se dice.

    Devuelve ``None`` si lo que se le pasa no es una fórmula química.  Es la
    función que se puede probar sola y la que hace todo el trabajo; el resto
    del módulo solo decide **dónde** aplicarla.
    """
    if modo == "no":
        return None
    crudo = _sin_indices((formula or "").strip())
    if not crudo:
        return None
    # Un ion se anuncia como tal antes de decirlo, que es como se nombra: «el
    # catión sodio», no «sodio con carga positiva».
    ion = _es_ion(crudo)
    analisis = _analizar(crudo, modo)
    if analisis is None:
        return None
    if not (analisis.numeros or analisis.carga) and crudo not in SIN_NUMERO:
        return None
    dicho = "".join(analisis.piezas)
    if ion:
        # Ya se ha dicho «con carga positiva» dentro; con el nombre del ion
        # delante sobra, así que se quita.
        dicho = dicho.replace(_(" con carga positiva"), "").replace(
            _(" con carga negativa"), "")
        dicho = "%s %s" % (ion, dicho.strip())
    return " ".join(dicho.split())


def leer(texto: str, modo: str = "nombres") -> str:
    """Devuelve el texto con las fórmulas químicas ya dichas en palabras.

    Es lo que se le pasa al sintetizador.  Lo que no sea una fórmula se queda
    exactamente igual, byte a byte.
    """
    if modo not in ("nombres", "simbolos") or not texto:
        return texto

    salida = texto
    # El «más» solo se dice cuando hay una flecha de reacción cerca.  Fuera de
    # una ecuación, un signo más entre dos palabras es una suma o un guion, y
    # decirlo estropearía el texto en vez de aclararlo.
    hay_reaccion = any(signo in salida for signo in FLECHAS)
    for signo, dicho in FLECHAS.items():
        if signo in salida:
            salida = salida.replace(signo, dicho)
    if hay_reaccion:
        salida = re.sub(r"(?<=[\s\w])\s\+\s(?=[\dA-Z])", _(" más "), salida)

    def sustituir(coincidencia: re.Match) -> str:
        crudo = coincidencia.group(1)
        # Un punto final de frase no forma parte de la fórmula.
        recortado = crudo.rstrip(".")
        # El estado de agregación va pegado —«H2O(l)»— y sin separarlo la
        # fórmula entera se descartaba, porque la «l» no es ningún elemento.
        estado = ""
        pegado = _ESTADO_PEGADO.search(recortado)
        if pegado is not None:
            estado = ESTADOS.get(pegado.group(1).lower(), "")
            if estado:
                recortado = recortado[:pegado.start()]
        dicho = formula_a_texto(recortado, modo)
        if dicho is None:
            return crudo
        return dicho + estado + crudo[len(recortado) + len(pegado.group(0) if estado else ""):]

    salida = _CANDIDATO.sub(sustituir, _sin_indices(salida))
    return _con_estados(salida)


def _con_estados(texto: str) -> str:
    """Dice los estados de agregación que van entre paréntesis."""
    def sustituir(coincidencia: re.Match) -> str:
        dentro = coincidencia.group(1)
        return ESTADOS.get(dentro.lower(), coincidencia.group(0))

    return re.sub(r"\((s|l|g|ac|aq|aq\.)\)", sustituir, texto)


#: Cuántas fórmulas hacen falta para dar por hecho que el documento es de
#: química.  Con una sola no basta: una novela puede mencionar el H2O o la
#: vitamina B12 y no por eso hay que ponerse a leer química en toda ella.
UMBRAL_AUTOMATICO = 5

#: Cuánto texto se mira para decidirlo.  Medio megabyte es un libro entero de
#: los normales y se recorre en unas centésimas; en uno de treinta millones de
#: caracteres, mirarlo todo se notaría al abrirlo y no diría nada nuevo.
MUESTRA = 500_000


def cuantas_formulas(texto: str, muestra: int = MUESTRA) -> int:
    """Cuenta las fórmulas químicas que hay en el principio del texto."""
    cuantas = 0
    for coincidencia in _CANDIDATO.finditer(_sin_indices((texto or "")[:muestra])):
        if formula_a_texto(coincidencia.group(1), "nombres"):
            cuantas += 1
    return cuantas


def modo_efectivo(preferencia: str, texto: str) -> str:
    """Resuelve el modo «automático» mirando el documento.

    El modo automático es lo que viene puesto, y es lo que hace que esto no
    moleste a nadie: en una novela no se activa nunca, y en un libro de química
    se activa solo, sin que haya que saber que la opción existe.  Eso último es
    justo lo que fallaba según las encuestas: **la función de accesibilidad que
    hay que activar no la encuentra quien la necesita**.
    """
    if preferencia in ("nombres", "simbolos", "no"):
        return preferencia
    return "nombres" if cuantas_formulas(texto) >= UMBRAL_AUTOMATICO else "no"


def hay_formulas(texto: str) -> bool:
    """Indica si en el texto hay al menos una fórmula química.

    Sirve para decidir si merece la pena ofrecer la lectura química de un
    documento sin molestar a quien lee una novela.
    """
    for coincidencia in _CANDIDATO.finditer(_sin_indices(texto or "")):
        if formula_a_texto(coincidencia.group(1), "nombres"):
            return True
    return False
