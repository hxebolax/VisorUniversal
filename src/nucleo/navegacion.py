# -*- coding: utf-8 -*-
"""Motor de navegación por elementos del documento.

Reproduce el comportamiento al que están acostumbrados los usuarios de
lectores de pantalla: teclas de una sola letra que saltan al siguiente
elemento de un tipo (``H`` para encabezados, ``T`` para tablas, ``G`` para
imágenes...) y las mismas con ``Mayús`` para ir hacia atrás.

Cada consulta es una búsqueda binaria sobre la lista ordenada de posiciones
de ese tipo de marca, de modo que el coste no depende del tamaño del libro.

El resultado de cada salto es un :class:`ResultadoNavegacion`, que además de
la posición trae ya redactado el mensaje que hay que anunciar al usuario.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from .documento import Documento
from .idioma import _, _n
from .marcas import (
    FORMATO,
    Marca,
    TipoMarca,
    nivel_de_encabezado,
    tipo_de_encabezado,
)

#: Valores numéricos de las marcas de formato, para descartarlas rápidamente.
_TIPOS_DE_FORMATO = frozenset(int(tipo) for tipo in FORMATO)


class Objetivo(Enum):
    """Clase de elemento a la que se quiere saltar."""

    SECCION = auto()
    PAGINA = auto()
    ENCABEZADO = auto()
    ENLACE = auto()
    LISTA = auto()
    ELEMENTO_LISTA = auto()
    TABLA = auto()
    SEPARADOR = auto()
    IMAGEN = auto()
    FIGURA = auto()
    CITA = auto()
    FORMULA = auto()
    NOTA_PIE = auto()
    CODIGO = auto()


#: Correspondencia entre objetivo y tipo de marca (los encabezados se tratan
#: aparte porque admiten filtro de nivel).
_TIPOS = {
    Objetivo.SECCION: TipoMarca.SALTO_SECCION,
    Objetivo.PAGINA: TipoMarca.SALTO_PAGINA,
    Objetivo.ENLACE: TipoMarca.ENLACE,
    Objetivo.LISTA: TipoMarca.LISTA,
    Objetivo.ELEMENTO_LISTA: TipoMarca.ELEMENTO_LISTA,
    Objetivo.TABLA: TipoMarca.TABLA,
    Objetivo.SEPARADOR: TipoMarca.SEPARADOR,
    Objetivo.IMAGEN: TipoMarca.IMAGEN,
    Objetivo.FIGURA: TipoMarca.FIGURA,
    Objetivo.CITA: TipoMarca.CITA,
    Objetivo.CODIGO: TipoMarca.CODIGO,
    Objetivo.FORMULA: TipoMarca.FORMULA,
    Objetivo.NOTA_PIE: TipoMarca.NOTA_PIE,
}

#: Género de cada tipo de elemento, para que los anuncios concuerden.  El
#: nombre no se guarda aquí: se pide traducido en el momento con
#: :func:`nombre_de`, porque una constante de módulo se congelaría con el
#: idioma que hubiera al importar.
_GENERO = {
    Objetivo.SECCION: "f", Objetivo.PAGINA: "f", Objetivo.ENCABEZADO: "m",
    Objetivo.ENLACE: "m", Objetivo.LISTA: "f", Objetivo.ELEMENTO_LISTA: "m",
    Objetivo.TABLA: "f", Objetivo.SEPARADOR: "m", Objetivo.IMAGEN: "f",
    Objetivo.FIGURA: "f", Objetivo.CITA: "f",
}


def nombre_de(objetivo: Objetivo, plural: bool = False) -> str:
    """Cómo se llama un tipo de elemento, para decirlo en voz alta."""
    nombres = {
        Objetivo.SECCION: (_("sección"), _("secciones")),
        Objetivo.PAGINA: (_("página"), _("páginas")),
        Objetivo.ENCABEZADO: (_("encabezado"), _("encabezados")),
        Objetivo.ENLACE: (_("enlace"), _("enlaces")),
        Objetivo.LISTA: (_("lista"), _("listas")),
        Objetivo.ELEMENTO_LISTA: (_("elemento de lista"), _("elementos de lista")),
        Objetivo.TABLA: (_("tabla"), _("tablas")),
        Objetivo.SEPARADOR: (_("separador"), _("separadores")),
        Objetivo.IMAGEN: (_("imagen"), _("imágenes")),
        Objetivo.FIGURA: (_("figura"), _("figuras")),
        Objetivo.CITA: (_("cita"), _("citas")),
    }
    pareja = nombres.get(objetivo)
    if pareja is None:
        return _("elemento")
    return pareja[1 if plural else 0]


@dataclass
class ResultadoNavegacion:
    """Lo que ocurrió al intentar un salto de navegación.

    :param encontrado: Si se ha llegado a algún elemento.
    :param posicion: Posición de destino (solo válida si ``encontrado``).
    :param mensaje: Texto ya redactado para anunciar al usuario.
    :param tipo: Tipo de marca alcanzada, para elegir el sonido.
    :param dio_la_vuelta: Si la búsqueda continuó desde el otro extremo.
    :param indice: Número de orden del elemento dentro de los de su tipo.
    """

    encontrado: bool = False
    posicion: int = 0
    mensaje: str = ""
    tipo: TipoMarca | None = None
    dio_la_vuelta: bool = False
    indice: int = -1


def _sin_elementos(objetivo: Objetivo, nivel: int) -> str:
    """Mensaje para un documento que no tiene ese tipo de elemento.

    La frase se elige entera según el género en vez de pegar el artículo por
    delante.  Pegarlo obliga al traductor a encajar dos trozos sueltos —y en
    inglés ni siquiera hay géneros—, así que cada forma es su propio texto.
    """
    if objetivo is Objetivo.ENCABEZADO and nivel:
        return _("No hay encabezados de nivel %d.") % nivel
    nombre = nombre_de(objetivo)
    if _GENERO.get(objetivo) == "f":
        return _("No hay ninguna %s en el documento.") % nombre
    return _("No hay ningún %s en el documento.") % nombre


def _no_encontrado(objetivo: Objetivo, nivel: int, siguiente: bool) -> str:
    """Mensaje cuando no queda ningún elemento en esa dirección."""
    if objetivo is Objetivo.ENCABEZADO and nivel:
        return (_("No hay más encabezados de nivel %d hacia adelante.") % nivel if siguiente
                else _("No hay más encabezados de nivel %d hacia atrás.") % nivel)
    nombre = nombre_de(objetivo, plural=True)
    if siguiente:
        return _("No hay más %s hacia adelante.") % nombre
    return _("No hay más %s hacia atrás.") % nombre


def _describir(documento: Documento, marca: Marca, objetivo: Objetivo, indice: int) -> str:
    """Redacta el anuncio del elemento al que se ha saltado."""
    texto = (marca.texto or "").strip()
    if objetivo is Objetivo.ENCABEZADO:
        if not texto:
            texto = documento.texto_de_linea(marca.posicion).strip()
        return _("%s. Encabezado de nivel %d.") % (texto, marca.nivel or nivel_de_encabezado(marca.tipo))
    if objetivo is Objetivo.PAGINA:
        rotulo = texto or str(indice + 1)
        contenido = documento.primera_linea_con_texto(marca.posicion)
        return _("Página %s. %s") % (rotulo, contenido) if contenido else _("Página %s.") % rotulo
    if objetivo is Objetivo.SECCION:
        contenido = documento.primera_linea_con_texto(marca.posicion)
        return contenido if contenido else (texto or _("Sección."))
    if objetivo is Objetivo.ENLACE:
        return "%s. Enlace." % (texto or documento.texto_de_linea(marca.posicion).strip())
    if objetivo is Objetivo.IMAGEN:
        return "Imagen. %s" % texto if texto and texto != "Imagen" else _("Imagen sin descripción.")
    if objetivo is Objetivo.FIGURA:
        return "Figura. %s" % texto if texto and texto != "Figura" else _("Figura sin descripción.")
    if objetivo is Objetivo.TABLA:
        return "Tabla. %s" % texto if texto else "Tabla."
    if objetivo is Objetivo.LISTA:
        cantidad = marca.nivel  # en las listas se guarda aquí el número de elementos
        if not cantidad:
            return _("Lista.")
        return _n("Lista con %d elemento.", "Lista con %d elementos.", cantidad) % cantidad
    if objetivo is Objetivo.ELEMENTO_LISTA:
        return texto or documento.texto_de_linea(marca.posicion).strip()
    if objetivo is Objetivo.SEPARADOR:
        return "Separador."
    if objetivo is Objetivo.CITA:
        return "Cita. %s" % documento.primera_linea_con_texto(marca.posicion)
    return texto or documento.texto_de_linea(marca.posicion).strip()


def navegar(documento: Documento, posicion: int, objetivo: Objetivo, siguiente: bool,
            circular: bool = False, nivel: int = 0) -> ResultadoNavegacion:
    """Salta al elemento anterior o siguiente del tipo indicado.

    :param documento: Libro en el que se navega.
    :param posicion: Posición actual del cursor.
    :param objetivo: Tipo de elemento buscado.
    :param siguiente: ``True`` para avanzar, ``False`` para retroceder.
    :param circular: Si al llegar al final se continúa desde el principio.
    :param nivel: Filtro de nivel para los encabezados (0 = cualquiera).
    """
    if objetivo is Objetivo.ENCABEZADO:
        if nivel:
            grupo = documento.marcas.grupo(tipo_de_encabezado(nivel))
        else:
            grupo = documento.marcas.encabezados
    else:
        grupo = documento.marcas.grupo(_TIPOS[objetivo])

    if not grupo:
        return ResultadoNavegacion(mensaje=_sin_elementos(objetivo, nivel))

    indice = grupo.indice_siguiente(posicion) if siguiente else grupo.indice_anterior(posicion)
    dio_la_vuelta = False
    if indice < 0:
        if not circular:
            return ResultadoNavegacion(mensaje=_no_encontrado(objetivo, nivel, siguiente))
        indice = 0 if siguiente else len(grupo) - 1
        dio_la_vuelta = True

    marca = grupo[indice]
    mensaje = _describir(documento, marca, objetivo, indice)
    if dio_la_vuelta:
        prefijo = _("Se continúa desde el principio. ") if siguiente else _("Se continúa desde el final. ")
        mensaje = prefijo + mensaje
    return ResultadoNavegacion(
        encontrado=True,
        posicion=marca.posicion,
        mensaje=mensaje,
        tipo=marca.tipo,
        dio_la_vuelta=dio_la_vuelta,
        indice=indice,
    )


def navegar_contenedor(documento: Documento, posicion: int, al_final: bool) -> ResultadoNavegacion:
    """Salta al principio de la lista o tabla actual, o más allá de su final.

    Es la orden que permite «salirse» rápidamente de una tabla larga sin
    tener que recorrerla entera.
    """
    contenedor = documento.marcas.contenedor_en(posicion)
    if contenedor is None:
        return ResultadoNavegacion(mensaje=_("El cursor no está dentro de ninguna lista ni tabla."))
    nombre = "tabla" if contenedor.tipo is TipoMarca.TABLA else "lista"
    if al_final:
        # Se coloca al principio de la línea siguiente al contenedor, para que
        # el cursor quede en contenido normal y no en la última celda.
        final = contenedor.posicion + contenedor.longitud
        numero = documento.linea_de(min(final, max(len(documento.texto) - 1, 0)))
        destino = documento.inicio_de_linea(numero + 1)
        mensaje = _("Fin de la %s.") % nombre
    else:
        destino = contenedor.posicion
        mensaje = _("Principio de la %s.") % nombre
    return ResultadoNavegacion(
        encontrado=True, posicion=min(destino, len(documento.texto)),
        mensaje=mensaje, tipo=contenedor.tipo,
    )


def elementos_en_linea(documento: Documento, posicion: int) -> list[Marca]:
    """Devuelve las marcas que empiezan en la línea que contiene ``posicion``.

    Es la consulta que alimenta el sistema de sonidos: al desplazarse por el
    texto, indica qué tipos de elemento hay en la línea a la que se acaba de
    llegar para reproducir el sonido correspondiente.
    """
    numero = documento.linea_de(posicion)
    inicio = documento.inicio_de_linea(numero)
    fin = documento.fin_de_linea(numero)
    encontradas: list[Marca] = []
    for tipo, grupo in documento.marcas.grupos.items():
        # La negrita y la cursiva no son elementos navegables ni tienen sonido,
        # y en una novela hay decenas de miles: recorrerlas sería trabajo tirado.
        if not grupo or tipo in _TIPOS_DE_FORMATO:
            continue
        indice = grupo.indice_siguiente(inicio - 1)
        while 0 <= indice < len(grupo):
            marca = grupo[indice]
            if marca.posicion >= fin:
                break
            if marca.posicion >= inicio:
                encontradas.append(marca)
            indice += 1
    encontradas.sort(key=lambda marca: marca.posicion)
    return encontradas


def resumen_posicion(documento: Documento, posicion: int) -> str:
    """Texto de la barra de estado: línea, porcentaje, página y sección."""
    linea = documento.linea_de(posicion) + 1
    columna = posicion - documento.inicio_de_linea(linea - 1) + 1
    partes = [
        _("Línea %d de %d") % (linea, max(documento.total_lineas, 1)),
        "columna %d" % columna,
        "%d %%" % documento.porcentaje_en(posicion),
    ]
    if documento.total_paginas:
        indice = documento.indice_de_pagina(posicion)
        if indice >= 0:
            marca = documento.marcas.grupo(TipoMarca.SALTO_PAGINA)[indice]
            partes.append(_("página %s") % (marca.texto or str(indice + 1)))
    return " | ".join(partes)


def encabezado_actual(documento: Documento, posicion: int) -> Marca | None:
    """Devuelve el encabezado bajo el que se está leyendo, si existe."""
    grupo = documento.marcas.encabezados
    indice = grupo.indice_actual(posicion)
    return grupo[indice] if indice >= 0 else None


def contexto_de_lectura(documento: Documento, posicion: int) -> str:
    """Describe dónde está el lector: capítulo, página y porcentaje.

    Es lo que se anuncia con la orden «¿dónde estoy?».
    """
    partes: list[str] = []
    encabezado = encabezado_actual(documento, posicion)
    if encabezado is not None and encabezado.texto:
        partes.append(encabezado.texto)
    if documento.total_paginas:
        indice = documento.indice_de_pagina(posicion)
        if indice >= 0:
            marca = documento.marcas.grupo(TipoMarca.SALTO_PAGINA)[indice]
            partes.append(_("página %s de %d") % (marca.texto or str(indice + 1), documento.total_paginas))
    partes.append("%d por ciento" % documento.porcentaje_en(posicion))
    partes.append(_("línea %d de %d") % (documento.linea_de(posicion) + 1, max(documento.total_lineas, 1)))
    return ". ".join(partes) + "."
