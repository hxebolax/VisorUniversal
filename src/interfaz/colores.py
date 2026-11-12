# -*- coding: utf-8 -*-
"""Paleta de colores con nombre.

El selector de color del sistema muestra una rejilla y valores numéricos, que
no sirven de nada si no se ve la pantalla: al llegar a él, el lector de
pantalla solo dice «botón», y dentro solo hay números.

Por eso los colores se eligen aquí de una **lista con nombres** —«Amarillo»,
«Negro», «Azul cielo»…—, que es una lista desplegable corriente y por tanto
perfectamente accesible: se recorre con las flechas y cada opción se anuncia
por su nombre.

La lista está ordenada por familias (primero los neutros, después los cálidos
y los fríos) para que recorrerla con las flechas resulte previsible, e incluye
las combinaciones de alto contraste que se usan habitualmente.
"""

from __future__ import annotations
from nucleo.idioma import _

#: Colores disponibles, como pares (nombre, valor hexadecimal).
PALETA: tuple[tuple[str, str], ...] = (
    (_("Negro"), "#000000"),
    (_("Gris muy oscuro"), "#1E1E1E"),
    (_("Gris oscuro"), "#404040"),
    (_("Gris"), "#808080"),
    (_("Gris claro"), "#C0C0C0"),
    (_("Blanco"), "#FFFFFF"),
    (_("Crema"), "#FFFDD0"),
    (_("Beige"), "#F5F0DC"),
    (_("Amarillo"), "#FFFF00"),
    (_("Amarillo pálido"), "#FFFFA0"),
    (_("Naranja"), "#FF8C00"),
    (_("Rojo"), "#FF0000"),
    (_("Rojo oscuro"), "#800000"),
    (_("Rosa"), "#FF80C0"),
    (_("Magenta"), "#FF00FF"),
    (_("Violeta"), "#8000FF"),
    (_("Azul"), "#0000FF"),
    (_("Azul marino"), "#000080"),
    (_("Azul cielo"), "#80C0FF"),
    (_("Cian"), "#00FFFF"),
    (_("Verde"), "#00C000"),
    (_("Verde claro"), "#80FF80"),
    (_("Verde oscuro"), "#004000"),
    (_("Marrón"), "#804000"),
)

#: Texto de la última opción, que abre el selector de color del sistema para
#: quien quiera un color exacto que no esté en la lista.
PERSONALIZADO = _("Otro color…")


def nombres() -> list[str]:
    """Nombres de la paleta, en orden, con la opción «Otro color» al final."""
    return [nombre for nombre, _ in PALETA] + [PERSONALIZADO]


def valor_de(nombre: str) -> str:
    """Valor hexadecimal de un color por su nombre, o cadena vacía."""
    for candidato, valor in PALETA:
        if candidato == nombre:
            return valor
    return ""


def nombre_de(valor: str) -> str:
    """Nombre del color que corresponde a un valor hexadecimal.

    Si el valor no está en la paleta (porque el usuario eligió uno a medida)
    se devuelve una descripción con el propio valor, para que el lector de
    pantalla anuncie algo con sentido en lugar de quedarse callado.
    """
    if not valor:
        return ""
    normalizado = valor.strip().upper()
    if not normalizado.startswith("#"):
        normalizado = "#" + normalizado
    for nombre, candidato in PALETA:
        if candidato.upper() == normalizado:
            return nombre
    return _("Color propio %s") % normalizado


def indice_de(valor: str) -> int:
    """Posición en la lista del color indicado, o ``-1`` si no está."""
    normalizado = (valor or "").strip().upper()
    if not normalizado:
        return -1
    if not normalizado.startswith("#"):
        normalizado = "#" + normalizado
    for numero, (_, candidato) in enumerate(PALETA):
        if candidato.upper() == normalizado:
            return numero
    return -1
