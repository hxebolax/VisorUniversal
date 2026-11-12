# -*- coding: utf-8 -*-
"""Utilidades de manipulación de texto usadas por los conversores.

Aquí vive todo lo relacionado con dos asuntos delicados:

1. **Normalización de espacios en blanco.**  El HTML colapsa cualquier
   secuencia de espacios, tabuladores y saltos de línea en un único espacio.
   Reproducir ese comportamiento es imprescindible para que el texto plano
   resultante se lea igual que el libro original.

2. **Unidades de posición.**  Las marcas del documento (encabezados, enlaces,
   imágenes...) guardan su posición como índice de *carácter de Python*.  El
   control de texto de Windows, en cambio, cuenta en *unidades UTF-16*: los
   caracteres fuera del plano básico (emoji, algunos símbolos musicales o
   matemáticos) ocupan **dos** unidades en lugar de una.

   La clase :class:`MapaUtf16` traduce entre ambos sistemas.  Como la inmensa
   mayoría de los libros no contiene ningún carácter de ese tipo, la clase
   detecta ese caso y se convierte en una traducción de coste cero.
"""

from __future__ import annotations

import bisect
import re
import sys

#: Guion blando: marca de división silábica invisible.  Se elimina porque
#: rompe las búsquedas de texto sin aportar nada en un lector de texto plano.
GUION_BLANDO = "­"

#: Espacio de anchura cero.  Se elimina por el mismo motivo.
ESPACIO_ANCHURA_CERO = "​"

#: Tabla de traducción aplicada a todo el texto que entra en el conversor.
#: Usar ``str.translate`` es notablemente más rápido que encadenar ``replace``.
_TABLA_LIMPIEZA = {
    ord(GUION_BLANDO): None,
    ord(ESPACIO_ANCHURA_CERO): None,
    ord(" "): " ",   # espacio duro -> espacio normal
    ord("﻿"): None,  # marca de orden de bytes perdida dentro del texto
    ord("\r"): "\n",      # fin de línea de Windows/Mac clásico
}

#: Línea que representa un separador temático (la etiqueta ``<hr>``).
LINEA_SEPARADOR = "-" * 40

#: Detecta caracteres fuera del plano multilingüe básico (los que ocupan dos
#: unidades UTF-16).  Se usa para decidir si hace falta traducir posiciones.
_PATRON_ASTRALES = re.compile(r"[\U00010000-\U0010FFFF]")

#: Solo Windows y macOS indexan el control de texto en unidades UTF-16.
#: En GTK (Linux) el índice es directamente el carácter Unicode.
PLATAFORMA_UTF16 = sys.platform in ("win32", "darwin")


def limpiar(texto: str) -> str:
    """Aplica la limpieza básica de caracteres invisibles a un texto."""
    return texto.translate(_TABLA_LIMPIEZA)


def colapsar_espacios(texto: str) -> str:
    """Reduce toda secuencia de espacios en blanco a un único espacio.

    Conserva un espacio inicial y otro final si los había, porque en HTML
    esos espacios sí separan palabras cuando hay etiquetas en línea de por
    medio (``palabra <em>otra</em>``).
    """
    if not texto:
        return ""
    inicial = " " if texto[:1].isspace() else ""
    final = " " if texto[-1:].isspace() else ""
    nucleo = " ".join(texto.split())
    if not nucleo:
        return " " if (inicial or final) else ""
    return inicial + nucleo + final


def numero_a_letras(numero: int, mayusculas: bool = False) -> str:
    """Convierte un número en su equivalente alfabético (1→a, 27→aa).

    Se usa para las listas ordenadas con ``type="a"`` o ``type="A"``.
    """
    if numero <= 0:
        return str(numero)
    base = ord("A") if mayusculas else ord("a")
    resultado = ""
    while numero > 0:
        numero -= 1
        resultado = chr(base + numero % 26) + resultado
        numero //= 26
    return resultado


_VALORES_ROMANOS = (
    (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
    (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
    (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
)


def numero_a_romano(numero: int, mayusculas: bool = True) -> str:
    """Convierte un número a numeración romana (para listas ``type="i"``)."""
    if numero <= 0 or numero > 3999:
        return str(numero)
    partes = []
    resto = numero
    for valor, simbolo in _VALORES_ROMANOS:
        while resto >= valor:
            partes.append(simbolo)
            resto -= valor
    romano = "".join(partes)
    return romano if mayusculas else romano.lower()


def formatear_elemento_lista(numero: int, tipo: str) -> str:
    """Devuelve la marca de un elemento de lista ordenada.

    :param numero: Número de orden del elemento (empezando en 1, o en el
                   valor del atributo ``start``).
    :param tipo: Valor del atributo ``type`` de la lista: ``1``, ``a``,
                 ``A``, ``i`` o ``I``.
    """
    if tipo == "a":
        return numero_a_letras(numero, False)
    if tipo == "A":
        return numero_a_letras(numero, True)
    if tipo == "i":
        return numero_a_romano(numero, False)
    if tipo == "I":
        return numero_a_romano(numero, True)
    return str(numero)


def vinneta_para_nivel(nivel: int) -> str:
    """Devuelve el símbolo de viñeta correspondiente a un nivel de anidamiento."""
    if nivel <= 1:
        return "•"   # bola negra
    if nivel == 2:
        return "◦"   # bola blanca
    return "-"


class MapaUtf16:
    """Traductor entre índices de carácter de Python e índices del control de texto.

    En Windows el control de texto cuenta posiciones en unidades UTF-16.  Un
    carácter «normal» ocupa una unidad; los caracteres del plano astral
    (emoji, etc.) ocupan dos.  Esta clase traduce en ambos sentidos.

    Cuando el texto no contiene ningún carácter astral —lo habitual en un
    libro— la clase entra en «modo directo» y las traducciones son la
    identidad, sin coste alguno.
    """

    __slots__ = ("_astrales", "directo")

    def __init__(self, texto: str) -> None:
        """Analiza el texto y decide si hace falta traducir posiciones.

        La comprobación previa (``codificar a UTF-16 y comparar longitudes``)
        se ejecuta dentro de la biblioteca estándar en C, por lo que es
        órdenes de magnitud más rápida que recorrer el texto en Python.
        """
        if not PLATAFORMA_UTF16 or texto.isascii():
            self.directo = True
            self._astrales: list[int] = []
            return
        # Si el texto codificado en UTF-16 ocupa exactamente dos bytes por
        # carácter, no hay ningún carácter astral y la traducción es directa.
        if len(texto.encode("utf-16-le", "surrogatepass")) == len(texto) * 2:
            self.directo = True
            self._astrales = []
            return
        self.directo = False
        self._astrales = [coincidencia.start() for coincidencia in _PATRON_ASTRALES.finditer(texto)]

    def a_control(self, posicion: int) -> int:
        """Traduce un índice de carácter de Python a posición del control."""
        if self.directo:
            return posicion
        return posicion + bisect.bisect_left(self._astrales, posicion)

    def desde_control(self, posicion: int) -> int:
        """Traduce una posición del control a índice de carácter de Python.

        Se resuelve por búsqueda binaria sobre la propia función
        :meth:`a_control`, que es monótona creciente.
        """
        if self.directo:
            return posicion
        bajo, alto = 0, posicion
        while bajo < alto:
            medio = (bajo + alto) // 2
            if self.a_control(medio) < posicion:
                bajo = medio + 1
            else:
                alto = medio
        return bajo
