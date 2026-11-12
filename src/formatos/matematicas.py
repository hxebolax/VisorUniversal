# -*- coding: utf-8 -*-
"""Fórmulas matemáticas: MathML leído en voz y conservado tal cual.

Un libro técnico con fórmulas era hasta ahora ilegible.  Las fórmulas vienen de
dos formas y las dos acababan igual: como **imagen** —y entonces no hay nada
que leer— o como **MathML**, el lenguaje con el que se escriben las matemáticas
en la web, que el conversor descartaba porque sus etiquetas no son las de un
texto normal.

Este módulo resuelve la segunda, que es la que tiene arreglo, y lo hace por dos
caminos a la vez:

* **En el texto** la fórmula se convierte en una frase que se puede oír:
  ``x² + 3x − 5 = 0`` se lee «x elevado a 2 más 3 x menos 5 igual a 0».  No es
  lo que diría un matemático, pero es infinitamente mejor que el silencio o que
  oír los símbolos sueltos sin ninguna relación entre ellos.
* **La fórmula original se guarda entera** y se puede abrir con ``Control+H``
  en el visor HTML.  Ahí el MathML llega intacto al lector de pantalla, que lo
  lee **con su propio motor matemático** —el de NVDA o el de JAWS, que saben de
  esto mucho más que este programa— y permite recorrer la fórmula por partes.

Es la misma solución que ya se usaba con las tablas: en el texto, una versión
que se pueda oír de corrido; en el visor, el original navegable.

Lo que se cubre es el MathML de presentación, que es el que traen los libros:
fracciones, raíces, potencias, subíndices, sumatorios con sus límites,
matrices y los operadores habituales.  El MathML de contenido —mucho más raro—
cae en el mismo camino y al menos se leen sus símbolos.
"""

from __future__ import annotations

import re

from nucleo.idioma import _

#: Espacio de nombres de MathML.  Las etiquetas llegan como
#: ``{http://www.w3.org/1998/Math/MathML}mi`` cuando el capítulo declara el
#: espacio de nombres, y como ``mi`` a secas cuando no lo declara (que pasa,
#: sobre todo en libros viejos), así que hay que admitir las dos formas.
ESPACIO = "http://www.w3.org/1998/Math/MathML"

#: Cómo se lee cada operador.  Sin esta tabla, el lector de pantalla dice el
#: nombre Unicode del carácter —«signo de mayor o igual que»— o directamente lo
#: calla, y una fórmula se vuelve una lista de letras sin relación.
OPERADORES = {
    "+": _(" más "),
    "-": _(" menos "),
    "−": _(" menos "),
    "±": _(" más o menos "),
    "∓": _(" menos o más "),
    "*": _(" por "),
    "×": _(" por "),
    "·": _(" por "),
    "⋅": _(" por "),
    "/": _(" partido por "),
    "÷": _(" entre "),
    "=": _(" igual a "),
    "≠": _(" distinto de "),
    "≈": _(" aproximadamente igual a "),
    "≡": _(" idéntico a "),
    "<": _(" menor que "),
    ">": _(" mayor que "),
    "≤": _(" menor o igual que "),
    "≥": _(" mayor o igual que "),
    "≪": _(" mucho menor que "),
    "≫": _(" mucho mayor que "),
    "→": _(" tiende a "),
    "⇒": _(" implica "),
    "⇔": _(" si y solo si "),
    "∈": _(" pertenece a "),
    "∉": _(" no pertenece a "),
    "⊂": _(" contenido en "),
    "⊆": _(" contenido o igual a "),
    "∪": _(" unión "),
    "∩": _(" intersección "),
    "∅": _(" conjunto vacío "),
    "∞": _(" infinito "),
    "∑": _(" sumatorio de "),
    "∏": _(" productorio de "),
    "∫": _(" integral de "),
    "∬": _(" integral doble de "),
    "∮": _(" integral de contorno de "),
    "√": _(" raíz cuadrada de "),
    "∂": _(" derivada parcial de "),
    "∇": _(" nabla "),
    "∀": _(" para todo "),
    "∃": _(" existe "),
    "¬": _(" no "),
    "∧": _(" y "),
    "∨": _(" o "),
    "!": _(" factorial "),
    "%": _(" por ciento "),
    "°": _(" grados "),
    "′": _(" prima "),
    "″": _(" segunda "),
    "…": _(" etcétera "),
    "⋯": _(" etcétera "),
    "|": _(" valor absoluto de "),
    "∥": _(" paralelo a "),
    "⊥": _(" perpendicular a "),
    "∠": _(" ángulo "),
}

#: Letras griegas con su nombre.  Un lector de pantalla en español suele decir
#: «alfa» sin problema, pero muchos leen «letra griega minúscula alfa» entera, y
#: en una fórmula con seis griegas eso es insoportable.
GRIEGAS = {
    "α": "alfa", "β": "beta", "γ": "gamma", "δ": "delta", "ε": "épsilon",
    "ζ": "dseta", "η": "eta", "θ": "theta", "ι": "iota", "κ": "kappa",
    "λ": "lambda", "μ": "mu", "ν": "nu", "ξ": "xi", "π": "pi", "ρ": "ro",
    "σ": "sigma", "τ": "tau", "υ": "úpsilon", "φ": "fi", "χ": "ji",
    "ψ": "psi", "ω": "omega",
    "Γ": _("gamma mayúscula"), "Δ": _("delta mayúscula"),
    "Θ": _("theta mayúscula"), "Λ": _("lambda mayúscula"),
    "Ξ": _("xi mayúscula"), "Π": _("pi mayúscula"), "Σ": _("sigma mayúscula"),
    "Φ": _("fi mayúscula"), "Ψ": _("psi mayúscula"), "Ω": _("omega mayúscula"),
}

#: Nombres de función que no hay que deletrear.  Sin esto, ``sen`` se lee como
#: una palabra cualquiera —lo cual está bien— pero ``lim`` o ``arctan`` salen
#: partidos y no se entienden.
FUNCIONES = {
    "sin": "seno", "sen": "seno", "cos": "coseno", "tan": "tangente",
    "tg": "tangente", "cot": "cotangente", "sec": "secante", "csc": "cosecante",
    "arcsin": "arcoseno", "arcsen": "arcoseno", "arccos": "arcocoseno",
    "arctan": "arcotangente", "sinh": _("seno hiperbólico"),
    "cosh": _("coseno hiperbólico"), "tanh": _("tangente hiperbólica"),
    "log": "logaritmo", "ln": _("logaritmo neperiano"), "lg": "logaritmo",
    "exp": "exponencial", "lim": "límite", "max": "máximo", "min": "mínimo",
    "sup": "supremo", "inf": "ínfimo", "det": "determinante",
    "mod": "módulo", "mcd": _("máximo común divisor"),
    "mcm": _("mínimo común múltiplo"),
}


def nombre_local(etiqueta) -> str:
    """Devuelve el nombre de la etiqueta sin el espacio de nombres."""
    if not isinstance(etiqueta, str):
        return ""
    return etiqueta.rsplit("}", 1)[-1].lower()


def es_formula(etiqueta) -> bool:
    """Indica si un elemento es una fórmula MathML."""
    return nombre_local(etiqueta) == "math"


def _simbolo(texto: str) -> str:
    """Traduce un símbolo suelto a cómo se dice."""
    texto = texto.strip()
    if not texto:
        return ""
    if texto in OPERADORES:
        return OPERADORES[texto]
    if texto in GRIEGAS:
        return " %s " % GRIEGAS[texto]
    minuscula = texto.lower()
    if minuscula in FUNCIONES:
        return " %s de " % FUNCIONES[minuscula]
    # Una letra griega dentro de una palabra más larga se traduce igual.
    if len(texto) == 1:
        return texto
    return texto


def _sin_de(texto: str) -> str:
    """Quita el «de» final de un operador que va a llevar límites detrás.

    El sumatorio se lee «sumatorio de», que está bien suelto; pero con límites
    delante saldría «sumatorio de desde i igual a 1 hasta n», con un «de desde»
    que sobra.
    """
    limpio = " ".join(texto.split())
    return limpio[:-3].strip() if limpio.endswith(" de") else limpio


def _hijos(elemento) -> list:
    """Hijos del elemento, saltándose comentarios e instrucciones."""
    return [hijo for hijo in elemento if isinstance(hijo.tag, str)]


def _texto_de(elemento) -> str:
    """Texto directo de un elemento, con los espacios colapsados."""
    return " ".join((elemento.text or "").split())


def _leer(elemento, profundidad: int = 0) -> str:
    """Convierte un elemento MathML en algo que se pueda decir.

    Se recorre el árbol de forma recursiva.  El límite de profundidad no es
    por eficiencia sino por prudencia: una fórmula generada por un programa
    puede venir con cientos de niveles anidados y no conviene agotar la pila
    del intérprete por una ecuación.
    """
    if profundidad > 40:
        return _(" (fórmula demasiado anidada) ")

    nombre = nombre_local(elemento.tag)
    hijos = _hijos(elemento)

    # --- hojas: identificadores, números, operadores y texto ---------------
    if nombre in ("mi", "mn", "ms"):
        # Con espacios alrededor: sin ellos, «3» seguido de «x» sale «3x» y el
        # sintetizador lo lee como una palabra sola en vez de como un número y
        # una incógnita.  Al final se colapsan todos de una vez.
        return " %s " % _simbolo(_texto_de(elemento))
    if nombre == "mo":
        return _simbolo(_texto_de(elemento))
    if nombre == "mtext":
        return " %s " % _texto_de(elemento)
    if nombre in ("mspace", "none"):
        return " "

    # --- agrupaciones -------------------------------------------------------
    if nombre in ("math", "mrow", "mstyle", "mpadded", "mphantom", "semantics",
                  "merror", "menclose"):
        return "".join(_leer(hijo, profundidad + 1) for hijo in hijos)

    # De <semantics> cuelgan anotaciones (LaTeX, por ejemplo) que no hay que
    # leer: son la misma fórmula escrita de otra manera.
    if nombre in ("annotation", "annotation-xml"):
        return ""

    # --- fracción -----------------------------------------------------------
    if nombre == "mfrac":
        if len(hijos) >= 2:
            arriba = _leer(hijos[0], profundidad + 1).strip()
            abajo = _leer(hijos[1], profundidad + 1).strip()
            return _(" la fracción %(arriba)s partido por %(abajo)s, fin de la fracción ") % {
                "arriba": arriba, "abajo": abajo}
        return "".join(_leer(hijo, profundidad + 1) for hijo in hijos)

    # --- raíces -------------------------------------------------------------
    if nombre == "msqrt":
        dentro = "".join(_leer(hijo, profundidad + 1) for hijo in hijos).strip()
        return _(" raíz cuadrada de %s, fin de la raíz ") % dentro
    if nombre == "mroot":
        if len(hijos) >= 2:
            dentro = _leer(hijos[0], profundidad + 1).strip()
            indice = _leer(hijos[1], profundidad + 1).strip()
            return _(" raíz de índice %(indice)s de %(dentro)s, fin de la raíz ") % {
                "indice": indice, "dentro": dentro}
        return "".join(_leer(hijo, profundidad + 1) for hijo in hijos)

    # --- potencias y subíndices ---------------------------------------------
    if nombre == "msup" and len(hijos) >= 2:
        base = _leer(hijos[0], profundidad + 1).strip()
        exponente = _leer(hijos[1], profundidad + 1).strip()
        if exponente == "2":
            return _(" %s al cuadrado ") % base
        if exponente == "3":
            return _(" %s al cubo ") % base
        return _(" %(base)s elevado a %(exponente)s ") % {
            "base": base, "exponente": exponente}
    if nombre == "msub" and len(hijos) >= 2:
        return _(" %(base)s sub %(indice)s ") % {
            "base": _leer(hijos[0], profundidad + 1).strip(),
            "indice": _leer(hijos[1], profundidad + 1).strip()}
    if nombre == "msubsup" and len(hijos) >= 3:
        return _(" %(base)s sub %(indice)s elevado a %(exponente)s ") % {
            "base": _leer(hijos[0], profundidad + 1).strip(),
            "indice": _leer(hijos[1], profundidad + 1).strip(),
            "exponente": _leer(hijos[2], profundidad + 1).strip()}

    # --- límites de sumatorios e integrales ----------------------------------
    if nombre == "munder" and len(hijos) >= 2:
        return _(" %(base)s con %(abajo)s debajo ") % {
            "base": _sin_de(_leer(hijos[0], profundidad + 1)),
            "abajo": _leer(hijos[1], profundidad + 1).strip()}
    if nombre == "mover" and len(hijos) >= 2:
        return _(" %(base)s con %(arriba)s encima ") % {
            "base": _leer(hijos[0], profundidad + 1).strip(),
            "arriba": _leer(hijos[1], profundidad + 1).strip()}
    if nombre == "munderover" and len(hijos) >= 3:
        return _(" %(base)s desde %(abajo)s hasta %(arriba)s ") % {
            "base": _sin_de(_leer(hijos[0], profundidad + 1)),
            "abajo": _leer(hijos[1], profundidad + 1).strip(),
            "arriba": _leer(hijos[2], profundidad + 1).strip()}

    # --- paréntesis explícitos (MathML 2) -----------------------------------
    if nombre == "mfenced":
        abre = elemento.get("open", "(")
        cierra = elemento.get("close", ")")
        separador = elemento.get("separators", ",") or ","
        partes = [_leer(hijo, profundidad + 1).strip() for hijo in hijos]
        return " %s%s%s " % (abre, (separador + " ").join(p for p in partes if p), cierra)

    # --- matrices -----------------------------------------------------------
    if nombre == "mtable":
        filas = [_leer(hijo, profundidad + 1) for hijo in hijos]
        cuerpo = "; ".join(f.strip() for f in filas if f.strip())
        return _(" matriz de %(filas)d filas: %(cuerpo)s, fin de la matriz ") % {
            "filas": len(filas), "cuerpo": cuerpo}
    if nombre in ("mtr", "mlabeledtr"):
        celdas = [_leer(hijo, profundidad + 1).strip() for hijo in hijos]
        return ", ".join(celda for celda in celdas if celda)
    if nombre == "mtd":
        return "".join(_leer(hijo, profundidad + 1) for hijo in hijos)

    # --- cualquier otra cosa -------------------------------------------------
    propio = _texto_de(elemento)
    dentro = "".join(_leer(hijo, profundidad + 1) for hijo in hijos)
    return (_simbolo(propio) if propio else "") + dentro


def a_texto(elemento) -> str:
    """Convierte una fórmula MathML en una frase legible.

    Si el árbol no da nada aprovechable se recurre al atributo ``alttext``, que
    muchos libros traen con la fórmula en LaTeX: no es cómodo de oír, pero es
    mejor que nada.
    """
    try:
        crudo = _leer(elemento)
    except Exception:
        crudo = ""
    # Los espacios se colapsan al final y de una vez: durante el recorrido se
    # generan de sobra a propósito, para que las palabras nunca se peguen.
    texto = re.sub(r"\s+", " ", crudo).strip()
    texto = re.sub(r"\s+([,;.])", r"\1", texto)
    if texto:
        return texto
    alterno = " ".join((elemento.get("alttext") or "").split())
    return alterno or _("fórmula")


def a_html(elemento) -> str:
    """Devuelve la fórmula como MathML, para enseñarla en el visor.

    Se serializa el elemento tal cual, con su espacio de nombres declarado, que
    es lo que necesita el navegador para reconocerlo como matemáticas y lo que
    permite que el lector de pantalla lo lea con su motor matemático.
    """
    from lxml import etree

    try:
        crudo = etree.tostring(elemento, encoding="unicode", method="xml")
    except Exception:
        return ""
    # lxml escribe el espacio de nombres como un prefijo (``<ns0:math ...>``)
    # cuando el elemento venía de un documento que lo declaraba arriba del
    # todo.  Los navegadores solo reconocen las matemáticas con el espacio de
    # nombres puesto en la propia etiqueta ``math``, así que se normaliza.
    crudo = re.sub(r"</?(?:ns\d+|m|mml):", lambda c: c.group(0).split(":")[0] + ":", crudo)
    crudo = re.sub(r"<(/?)(?:ns\d+|m|mml):", r"<\1", crudo)
    crudo = re.sub(r'\sxmlns:(?:ns\d+|m|mml)="[^"]*"', "", crudo)
    if "xmlns" not in crudo:
        crudo = crudo.replace("<math", '<math xmlns="%s"' % ESPACIO, 1)
    return crudo
