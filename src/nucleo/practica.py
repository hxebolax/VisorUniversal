# -*- coding: utf-8 -*-
"""Modo de práctica: hacer las cosas, no leer cómo se hacen.

El recorrido guiado explica una tecla por pantalla y deja pulsarla en un
recuadro.  Está bien, y no basta: pulsar `H` en un recuadro que dice «pulsa H»
no es lo mismo que **ir al tercer encabezado de un libro de verdad**, que es lo
que hará falta mañana.  Es la diferencia entre reconocer una tecla y saber usarla,
y es lo que piden las encuestas de quien empieza.

Aquí están los ejercicios, y están **fuera de la ventana** a propósito.  El
enunciado, el que decide si ha salido y el que elige cuáles caben en este
documento son funciones sobre datos, así que se pueden probar sin abrir nada.
Lo único que pone la ventana es mirar cómo está el documento cada poco y
preguntar aquí si ya está.

**Se practica sobre el documento que se tenga abierto**, no sobre un texto de
mentira.  Un texto de ejemplo con tres encabezados enseñaría a moverse por un
texto de ejemplo; el libro que uno tiene delante es el que hay que aprender a
recorrer, y además así se ve enseguida cuáles de estas cosas trae de verdad.

**Y solo se proponen los ejercicios que este documento admite.** Pedir «ve al
tercer encabezado» en una novela sin encabezados es enseñar que el programa no
funciona.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Callable
from typing import NamedTuple

from .idioma import _
from .registro import obtener_registro

log = obtener_registro(__name__)

#: A qué encabezado se manda ir. El tercero y no el primero: al primero se llega
#: pulsando una vez desde arriba, y eso no enseña a contar ni a volver atrás.
ENCABEZADO_OBJETIVO = 3

#: Qué línea se pide en el ejercicio de «ir a la línea». Bastante adentro como
#: para que no se llegue con la flecha abajo.
LINEA_OBJETIVO = 25

#: Cuánto texto tiene que tener el documento para que valga la pena mandar a
#: recorrerlo entero.
SUFICIENTE = 2000

#: Longitud mínima de la palabra que se manda buscar. Las cortas salen en
#: cualquier sitio y no enseñan nada del buscador.
LETRAS_MINIMAS = 6


class Estado(NamedTuple):
    """Cómo está el documento en un instante.

    Es lo que la ventana mira y lo único que los ejercicios reciben.  Tenerlo en
    una tupla —y no preguntarle a la ventana— es lo que permite probar los
    ejercicios sin wxPython.
    """

    posicion: int = 0
    total: int = 0
    linea: int = 0
    #: Índice del encabezado en cuyo tramo cae el cursor; -1 antes del primero.
    encabezado: int = -1
    encabezados: int = 0
    marcadores: int = 0
    notas: int = 0
    resaltados: int = 0
    #: Lo último que se buscó, tal cual se escribió.
    busqueda: str = ""


class Ejercicio(NamedTuple):
    """Un ejercicio: qué hay que hacer y cómo se sabe que ha salido.

    :param clave: Nombre corto, para el registro y para las pruebas.
    :param enunciado: Lo que se pide, ya con los datos de este documento.
    :param pista: Con qué tecla se hace.  Va aparte del enunciado porque se dice
                  al repetirlo, y quien ya lo sabe no tiene que volver a oírlo.
    :param hecho: ``(inicial, ahora) -> bool``.  Recibe los dos estados porque
                  «poner un marcador» no es tener marcadores: es tener **uno
                  más** que al empezar, y en un libro ya trabajado eso no se
                  puede saber mirando solo el estado de ahora.
    """

    clave: str
    enunciado: str
    pista: str
    hecho: Callable[[Estado, Estado], bool]


def _sin_tildes(texto: str) -> str:
    """El texto en minúsculas y sin tildes, para comparar lo que se ha buscado."""
    plano = unicodedata.normalize("NFD", (texto or "").lower())
    return "".join(letra for letra in plano if not unicodedata.combining(letra))


def palabra_para_buscar(texto: str) -> str:
    """Elige una palabra del documento que valga para practicar la búsqueda.

    Se busca **una que salga varias veces**: encontrar una y que no haya
    siguiente no enseña que ``F3`` repite la búsqueda, que es la mitad de lo que
    hay que aprender.  Y se descartan las cortas, que salen en todas partes.
    """
    cuenta: dict[str, int] = {}
    for palabra in re.findall(r"[^\W\d_]{%d,}" % LETRAS_MINIMAS, texto or "",
                              re.UNICODE):
        clave = palabra.lower()
        cuenta[clave] = cuenta.get(clave, 0) + 1
    repetidas = [(veces, palabra) for palabra, veces in cuenta.items() if veces >= 3]
    if not repetidas:
        # Sin ninguna repetida, sirve la más larga: al menos existe.
        return max(cuenta, key=len) if cuenta else ""
    # La más repetida, y a igualdad la más larga: cuanto más frecuente, más
    # probable es que el ejercicio se pueda terminar sin buscar mucho.
    repetidas.sort(key=lambda par: (par[0], len(par[1])), reverse=True)
    return repetidas[0][1]


def estado_de(documento, posicion: int, marcadores=(), resaltados=(),
              busqueda: str = "") -> Estado:
    """Arma el estado a partir del documento y de lo que la ventana sabe.

    Está aquí y no en la ventana para que las pruebas puedan construirlo igual
    que lo construye el programa, que es la única forma de que las dos cosas no
    se separen con el tiempo.
    """
    if documento is None:
        return Estado()
    encabezados = documento.marcas.encabezados
    marcados = list(marcadores)
    return Estado(
        posicion=posicion,
        total=len(documento.texto),
        linea=documento.linea_de(posicion),
        encabezado=encabezados.indice_actual(posicion),
        encabezados=len(encabezados),
        marcadores=len(marcados),
        notas=sum(1 for marcador in marcados
                  if getattr(marcador, "es_nota", False)),
        resaltados=len(list(resaltados)),
        busqueda=busqueda or "")


# ---------------------------------------------------------------------------
# Los ejercicios
# ---------------------------------------------------------------------------

def preparar(documento, inicial: Estado) -> list[Ejercicio]:
    """Los ejercicios que este documento admite, en el orden en que se proponen.

    Van de menos a más: primero moverse, que es lo que se usa en cada página;
    después marcar y buscar, que ya es trabajo de estudio.
    """
    if documento is None:
        return []
    ejercicios: list[Ejercicio] = []

    if inicial.encabezados >= ENCABEZADO_OBJETIVO:
        titulo = documento.marcas.encabezados[ENCABEZADO_OBJETIVO - 1].texto
        ejercicios.append(Ejercicio(
            "encabezado",
            _("Ve al tercer encabezado del documento, el que se llama «%s».")
            % (titulo or _("(sin título)")),
            _("Con la tecla H se salta de encabezado en encabezado; "
              "con Mayús+H, hacia atrás."),
            lambda inicio, ahora: ahora.encabezado == ENCABEZADO_OBJETIVO - 1))

    if inicial.total >= SUFICIENTE:
        ejercicios.append(Ejercicio(
            "final",
            _("Ahora vete al final del documento, de una vez."),
            _("Control+Fin lleva al final; Control+Inicio, al principio."),
            lambda inicio, ahora: ahora.posicion >= ahora.total - 2))
        ejercicios.append(Ejercicio(
            "principio",
            _("Y vuelve al principio."),
            _("Control+Inicio."),
            lambda inicio, ahora: ahora.posicion == 0))

    if inicial.linea >= 0 and documento.texto.count("\n") >= LINEA_OBJETIVO:
        ejercicios.append(Ejercicio(
            "linea",
            _("Ve a la línea %d.") % LINEA_OBJETIVO,
            _("Control+L pregunta a qué línea ir."),
            lambda inicio, ahora: ahora.linea == LINEA_OBJETIVO - 1))

    palabra = palabra_para_buscar(documento.texto)
    if palabra:
        ejercicios.append(Ejercicio(
            "buscar",
            _("Busca la palabra «%s» en el documento.") % palabra,
            _("Control+F abre la búsqueda; después, F3 va a la siguiente y "
              "Mayús+F3 a la anterior."),
            lambda inicio, ahora, esperada=palabra:
                _sin_tildes(ahora.busqueda) == _sin_tildes(esperada)))

    ejercicios.append(Ejercicio(
        "marcador",
        _("Pon un marcador donde estés."),
        _("Control+M pone o quita un marcador. Después, la tecla B salta al "
          "marcador siguiente."),
        lambda inicio, ahora: ahora.marcadores > inicio.marcadores))
    ejercicios.append(Ejercicio(
        "nota",
        _("Escribe una nota con lo que quieras."),
        _("Control+Mayús+M escribe una nota, que es un marcador con un texto "
          "tuyo. La tecla N salta a la nota siguiente."),
        lambda inicio, ahora: ahora.notas > inicio.notas))
    ejercicios.append(Ejercicio(
        "resaltado",
        _("Resalta un trozo de texto: selecciónalo y guárdalo."),
        _("Se selecciona con Mayús y las flechas, y se resalta con Control+R. "
          "Los resaltados se sacan luego a un archivo."),
        lambda inicio, ahora: ahora.resaltados > inicio.resaltados))
    return ejercicios


def resumen(hechos: int, saltados: int, total: int) -> str:
    """Cómo ha ido la sesión, para decirlo al terminar."""
    if not total:
        return _("No hay nada que practicar con este documento.")
    if hechos == total:
        return _("Los has hecho todos. Con esto ya te manejas por un documento.")
    if not hechos:
        return _("No has terminado ninguno. Se puede volver cuando quieras: "
                 "Ayuda, Practicar.")
    return _("Hechos %(hechos)d de %(total)d; saltados %(saltados)d.") % {
        "hechos": hechos, "total": total, "saltados": saltados}
