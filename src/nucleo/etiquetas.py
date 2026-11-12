# -*- coding: utf-8 -*-
"""Etiquetas para agrupar notas y resaltados por tema, no por libro.

Quien prepara una asignatura con seis libros no necesita las notas *del libro
tercero*: necesita **todo lo del tema cuatro**, esté donde esté. Esa es la
diferencia entre una lista de notas y un material de estudio, y es lo único que
faltaba una vez que las notas ya se escriben, se buscan y se exportan.

Una etiqueta es una palabra o dos —«examen», «capítulo 4», «dudas»— que se le
pone a una nota o a un resaltado. Se escriben separadas por comas en el mismo
sitio donde se escribe la nota, sin ningún diálogo aparte.

**Las decisiones que importan, y por qué:**

- **Se comparan sin tildes y sin mayúsculas.** Quien escribe «Examen» un día y
  «examen» otro quiere la misma etiqueta, y quien escribe «Análisis» y «analisis»
  también. Pero **se guarda tal como se escribió la primera vez**: al leerla en
  voz alta, «Análisis» se pronuncia bien y «analisis» no.
- **No se parten por espacios.** «capítulo 4» es una etiqueta, no dos. Se separan
  solo por comas, que es lo que la gente escribe sin pensar.
- **No hay lista cerrada ni hay que crearlas antes.** Se escribe una etiqueta
  nueva y ya existe; se deja de usar y desaparece sola.
"""

from __future__ import annotations

import unicodedata

#: Lo más larga que puede ser una etiqueta. Por encima de esto ya no es una
#: etiqueta, es una nota escrita en el sitio equivocado, y conviene decirlo
#: antes de que se llene la lista de frases enteras.
MAXIMA = 40

#: Cuántas admite una nota. El límite no es técnico: una nota con quince
#: etiquetas no está clasificada, está repetida quince veces, y al leerla en voz
#: alta son quince palabras antes de llegar a lo escrito.
MAXIMAS_POR_NOTA = 8


def normalizar(etiqueta: str) -> str:
    """La forma con la que se compara una etiqueta: sin tildes ni mayúsculas.

    No es lo que se enseña ni lo que se guarda: solo sirve para saber si dos
    etiquetas escritas distinto son la misma.
    """
    plano = unicodedata.normalize("NFKD", (etiqueta or "").strip().lower())
    sin_tildes = "".join(c for c in plano if not unicodedata.combining(c))
    return " ".join(sin_tildes.split())


def limpiar(etiqueta: str) -> str:
    """Deja una etiqueta escrita como se va a guardar y a enseñar."""
    return " ".join((etiqueta or "").strip().split())[:MAXIMA]


def leer(texto: str) -> list[str]:
    """Convierte lo que se escribe en el campo en una lista de etiquetas.

    Se separan por comas; los espacios de sobra se quitan, las repetidas se
    dejan una vez —comparando sin tildes— y se conserva el orden en que se
    escribieron, que es el que quien las escribió tiene en la cabeza.
    """
    salida: list[str] = []
    vistas: set[str] = set()
    for trozo in (texto or "").replace(";", ",").split(","):
        etiqueta = limpiar(trozo)
        if not etiqueta:
            continue
        clave = normalizar(etiqueta)
        if not clave or clave in vistas:
            continue
        vistas.add(clave)
        salida.append(etiqueta)
        if len(salida) >= MAXIMAS_POR_NOTA:
            break
    return salida


def escribir(etiquetas) -> str:
    """Lo contrario de :func:`leer`: la lista tal como se ve en el campo."""
    return ", ".join(etiquetas or [])


def de(marcador) -> list[str]:
    """Las etiquetas de un marcador, aunque sea de una versión anterior."""
    return list(getattr(marcador, "etiquetas", None) or [])


def tiene(marcador, etiqueta: str) -> bool:
    """Dice si un marcador lleva esa etiqueta, escrita como se escriba."""
    clave = normalizar(etiqueta)
    if not clave:
        return True
    return any(normalizar(suya) == clave for suya in de(marcador))


def filtrar(marcadores, etiqueta: str) -> list:
    """Los marcadores que llevan esa etiqueta. Sin etiqueta, todos."""
    if not (etiqueta or "").strip():
        return list(marcadores)
    return [m for m in marcadores if tiene(m, etiqueta)]


def recuento(marcadores) -> list[tuple[str, int]]:
    """Las etiquetas que hay y cuántas notas lleva cada una.

    Se ordena por número de notas y, a igualdad, por orden alfabético: quien
    abre la lista busca casi siempre el tema en el que más ha trabajado, y
    tenerlo el primero ahorra recorrer la lista entera de oído.

    De cada etiqueta se enseña **la primera forma con que se escribió**, no la
    normalizada: se lee en voz alta y las tildes importan.
    """
    cuantas: dict[str, int] = {}
    como_se_escribio: dict[str, str] = {}
    for marcador in marcadores:
        for etiqueta in de(marcador):
            clave = normalizar(etiqueta)
            if not clave:
                continue
            cuantas[clave] = cuantas.get(clave, 0) + 1
            como_se_escribio.setdefault(clave, etiqueta)
    return sorted(((como_se_escribio[clave], numero)
                   for clave, numero in cuantas.items()),
                  key=lambda par: (-par[1], normalizar(par[0])))


def sugerencias(marcadores) -> list[str]:
    """Las etiquetas ya usadas, para ofrecerlas al escribir una nota nueva.

    Que estén a mano es lo que evita acabar con «examen», «exámenes» y «para el
    examen» siendo tres cosas distintas.
    """
    return [etiqueta for etiqueta, _cuantas in recuento(marcadores)]
