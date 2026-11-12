# -*- coding: utf-8 -*-
"""Marcas: las posiciones etiquetadas que dan estructura al texto plano.

La idea central del visor —copiada del comportamiento que hace tan rápido a
Paperback— es que **el libro se convierte en un único texto plano** y toda su
estructura (encabezados, listas, tablas, imágenes, enlaces...) se guarda
aparte como una lista de *marcas*: pares «tipo de elemento + posición».

Ventajas frente a renderizar HTML:

* El control de texto solo maneja texto plano, que es lo que mejor y más
  rápido sabe hacer.
* Los lectores de pantalla leen el contenido de forma natural, sin depender
  de la accesibilidad de un motor de renderizado.
* Saltar al siguiente encabezado, imagen o tabla es una búsqueda binaria
  sobre una lista ordenada de enteros: instantáneo incluso en libros enormes.

Este módulo define los tipos de marca y la colección que los agrupa e indexa.
"""

from __future__ import annotations

from .idioma import _
import bisect
from enum import IntEnum
from typing import Iterable, NamedTuple


class TipoMarca(IntEnum):
    """Clase de elemento estructural al que corresponde una marca.

    Los valores numéricos son estables: se guardan en la caché de libros
    analizados, de modo que no deben reordenarse (solo añadirse al final).
    """

    ENCABEZADO1 = 0
    ENCABEZADO2 = 1
    ENCABEZADO3 = 2
    ENCABEZADO4 = 3
    ENCABEZADO5 = 4
    ENCABEZADO6 = 5
    SALTO_PAGINA = 6
    SALTO_SECCION = 7
    ENLACE = 8
    LISTA = 9
    ELEMENTO_LISTA = 10
    TABLA = 11
    SEPARADOR = 12
    IMAGEN = 13
    FIGURA = 14
    NEGRITA = 15
    CURSIVA = 16
    SUBRAYADO = 17
    CITA = 18
    FORMULA = 19
    NOTA_PIE = 20
    IDIOMA = 21
    CODIGO = 22


#: Marcas de encabezado, ordenadas del nivel 1 al 6.
ENCABEZADOS = (
    TipoMarca.ENCABEZADO1,
    TipoMarca.ENCABEZADO2,
    TipoMarca.ENCABEZADO3,
    TipoMarca.ENCABEZADO4,
    TipoMarca.ENCABEZADO5,
    TipoMarca.ENCABEZADO6,
)

#: Marcas que no señalan un elemento, sino un tramo de texto escrito en otro
#: idioma.  No se navega por ellas: sirven para que la lectura en voz alta
#: cambie de voz al llegar a una cita en inglés dentro de un informe en
#: español, que es lo que hacen los lectores de pantalla.
IDIOMAS = (TipoMarca.IDIOMA,)

#: Marcas que representan formato de carácter y no elementos navegables.
FORMATO = (TipoMarca.NEGRITA, TipoMarca.CURSIVA, TipoMarca.SUBRAYADO)

#: Marcas «contenedoras»: el cursor puede estar *dentro* de ellas, y por eso
#: admiten las órdenes «ir al principio / más allá del final del contenedor».
#: El bloque de código está aquí porque un listado de cuarenta renglones es
#: justo donde hace falta poder saltárselo entero.
CONTENEDORES = (TipoMarca.LISTA, TipoMarca.TABLA, TipoMarca.CODIGO)

#: Nombre legible de cada tipo, usado en anuncios y en la lista de elementos.
NOMBRES = {
    TipoMarca.ENCABEZADO1: _("encabezado de nivel 1"),
    TipoMarca.ENCABEZADO2: _("encabezado de nivel 2"),
    TipoMarca.ENCABEZADO3: _("encabezado de nivel 3"),
    TipoMarca.ENCABEZADO4: _("encabezado de nivel 4"),
    TipoMarca.ENCABEZADO5: _("encabezado de nivel 5"),
    TipoMarca.ENCABEZADO6: _("encabezado de nivel 6"),
    TipoMarca.SALTO_PAGINA: _("página"),
    TipoMarca.SALTO_SECCION: _("sección"),
    TipoMarca.ENLACE: "enlace",
    TipoMarca.LISTA: "lista",
    TipoMarca.ELEMENTO_LISTA: _("elemento de lista"),
    TipoMarca.TABLA: "tabla",
    TipoMarca.SEPARADOR: "separador",
    TipoMarca.IMAGEN: "imagen",
    TipoMarca.FIGURA: "figura",
    TipoMarca.NEGRITA: "negrita",
    TipoMarca.CURSIVA: "cursiva",
    TipoMarca.SUBRAYADO: "subrayado",
    TipoMarca.CITA: "cita",
    TipoMarca.FORMULA: _("fórmula"),
    TipoMarca.NOTA_PIE: _("llamada de nota"),
    TipoMarca.IDIOMA: _("idioma"),
    TipoMarca.CODIGO: _("bloque de código"),
}


#: Elementos que merece la pena señalar al pasar por encima de ellos, del que
#: más dice al que menos.  Es la misma lista para el sonido y para la voz:
#: decide qué pitido suena —solo uno, porque un acorde de pitidos no dice
#: nada— y en qué orden se nombran los elementos cuando se anuncian hablados.
#:
#: Lo que **no** está aquí es tan deliberado como lo que está.  La negrita, la
#: cursiva, el subrayado y los cambios de idioma se quedan fuera porque en un
#: libro normal aparecen en casi cada línea: señalarlos convertiría el aviso en
#: un ruido continuo que habría que apagar, y con él se perdería el de los
#: elementos que sí importan.
#:
#: La llamada de nota va por delante del enlace porque una llamada de nota *es*
#: un enlace —se marca como las dos cosas— y de las dos es la que dice algo.
ORDEN_DE_INTERES: tuple[TipoMarca, ...] = (
    TipoMarca.ENCABEZADO1,
    TipoMarca.ENCABEZADO2,
    TipoMarca.ENCABEZADO3,
    TipoMarca.ENCABEZADO4,
    TipoMarca.ENCABEZADO5,
    TipoMarca.ENCABEZADO6,
    TipoMarca.TABLA,
    TipoMarca.IMAGEN,
    TipoMarca.FIGURA,
    TipoMarca.LISTA,
    TipoMarca.CODIGO,
    TipoMarca.SALTO_PAGINA,
    TipoMarca.SALTO_SECCION,
    TipoMarca.SEPARADOR,
    TipoMarca.CITA,
    TipoMarca.ELEMENTO_LISTA,
    TipoMarca.NOTA_PIE,
    TipoMarca.ENLACE,
)


def nombrar(tipos, maximo: int = 3) -> str:
    """Nombra los elementos de una línea para decirlos en voz alta.

    A diferencia del sonido, que solo puede ser uno, la voz **sí puede
    enumerar**, y ahí está su ventaja: en una línea que lleva un salto de
    página y una llamada de nota, el pitido tiene que elegir y elige el salto
    de página, con lo que la nota se queda sin señalar.  Dicha, se oyen las
    dos.

    :param tipos: Tipos presentes en la línea, en cualquier orden.
    :param maximo: Cuántos se nombran como mucho.  Más de tres seguidos ya no
                   se retienen y retrasan la lectura de la línea, que es lo que
                   de verdad se quería oír.
    """
    presentes = set(tipos)
    nombres = [NOMBRES[tipo] for tipo in ORDEN_DE_INTERES
               if tipo in presentes and tipo in NOMBRES]
    return ", ".join(nombres[:maximo])


def es_encabezado(tipo: TipoMarca) -> bool:
    """Indica si un tipo de marca corresponde a un encabezado."""
    return TipoMarca.ENCABEZADO1 <= tipo <= TipoMarca.ENCABEZADO6


def nivel_de_encabezado(tipo: TipoMarca) -> int:
    """Devuelve el nivel (1-6) de un tipo de marca de encabezado."""
    return int(tipo) - int(TipoMarca.ENCABEZADO1) + 1


def tipo_de_encabezado(nivel: int) -> TipoMarca:
    """Devuelve el tipo de marca correspondiente a un nivel de encabezado."""
    nivel = max(1, min(6, nivel))
    return TipoMarca(int(TipoMarca.ENCABEZADO1) + nivel - 1)


class Marca(NamedTuple):
    """Una posición etiquetada dentro del texto del documento.

    :param tipo: Clase de elemento (:class:`TipoMarca`).
    :param posicion: Índice del primer carácter del elemento en el texto.
    :param texto: Texto asociado; por ejemplo el título de un encabezado, la
                  descripción de una imagen o el rótulo de un enlace.
    :param referencia: Dato auxiliar dependiente del tipo: destino de un
                       enlace, ruta del archivo de una imagen o de la sección.
    :param nivel: Nivel de anidamiento (encabezados y elementos de lista).
    :param longitud: Extensión del elemento en caracteres.  Solo la usan las
                     marcas de formato y las contenedoras (listas y tablas).
    """

    tipo: TipoMarca
    posicion: int
    texto: str = ""
    referencia: str = ""
    nivel: int = 0
    longitud: int = 0


class GrupoMarcas:
    """Todas las marcas de un mismo tipo, indexadas por posición.

    Guardar las posiciones en una lista propia y ordenada permite responder
    a «¿cuál es la siguiente imagen?» con una búsqueda binaria (:mod:`bisect`)
    en lugar de recorrer todas las marcas del libro.  En un libro con cientos
    de miles de marcas la diferencia es la que hay entre una pulsación de
    tecla instantánea y una perceptiblemente lenta.
    """

    __slots__ = ("posiciones", "marcas")

    def __init__(self, marcas: Iterable[Marca] = ()) -> None:
        ordenadas = sorted(marcas, key=lambda marca: marca.posicion)
        self.marcas: list[Marca] = ordenadas
        self.posiciones: list[int] = [marca.posicion for marca in ordenadas]

    def __len__(self) -> int:
        return len(self.marcas)

    def __bool__(self) -> bool:
        return bool(self.marcas)

    def __iter__(self):
        return iter(self.marcas)

    def __getitem__(self, indice: int) -> Marca:
        return self.marcas[indice]

    def indice_siguiente(self, posicion: int) -> int:
        """Índice de la primera marca situada *estrictamente después* de ``posicion``.

        Devuelve ``-1`` si no hay ninguna.
        """
        indice = bisect.bisect_right(self.posiciones, posicion)
        return indice if indice < len(self.posiciones) else -1

    def indice_anterior(self, posicion: int) -> int:
        """Índice de la última marca situada *estrictamente antes* de ``posicion``.

        Devuelve ``-1`` si no hay ninguna.
        """
        indice = bisect.bisect_left(self.posiciones, posicion) - 1
        return indice if indice >= 0 else -1

    def indice_actual(self, posicion: int) -> int:
        """Índice de la última marca que empieza en ``posicion`` o antes.

        Sirve para responder «¿en qué página / sección estoy?».
        """
        indice = bisect.bisect_right(self.posiciones, posicion) - 1
        return indice if indice >= 0 else -1

    def indice_mas_cercano(self, posicion: int) -> int:
        """Índice de la marca más próxima a ``posicion``, sea anterior o posterior.

        Se usa para preseleccionar la entrada correcta al abrir el índice o
        la lista de elementos.
        """
        if not self.posiciones:
            return -1
        indice = bisect.bisect_left(self.posiciones, posicion)
        if indice == 0:
            return 0
        if indice >= len(self.posiciones):
            return len(self.posiciones) - 1
        antes = self.posiciones[indice - 1]
        despues = self.posiciones[indice]
        return indice - 1 if (posicion - antes) <= (despues - posicion) else indice


class ColeccionMarcas:
    """Todas las marcas de un documento, agrupadas por tipo.

    Además de los grupos por tipo mantiene:

    * ``encabezados``: todos los encabezados juntos, para la navegación con
      ``H`` sin filtro de nivel y para construir el árbol del índice.
    * ``contenedores``: listas y tablas ordenadas por posición, para saber en
      qué contenedor está el cursor.
    """

    __slots__ = ("grupos", "encabezados", "contenedores", "formato")

    def __init__(self, marcas: Iterable[Marca] = ()) -> None:
        por_tipo: dict[int, list[Marca]] = {}
        for marca in marcas:
            por_tipo.setdefault(int(marca.tipo), []).append(marca)
        self.grupos: dict[int, GrupoMarcas] = {
            tipo: GrupoMarcas(lista) for tipo, lista in por_tipo.items()
        }
        todos_encabezados: list[Marca] = []
        for tipo in ENCABEZADOS:
            todos_encabezados.extend(por_tipo.get(int(tipo), ()))
        self.encabezados = GrupoMarcas(todos_encabezados)
        contenedores: list[Marca] = []
        for tipo in CONTENEDORES:
            contenedores.extend(
                marca for marca in por_tipo.get(int(tipo), ()) if marca.longitud > 0
            )
        self.contenedores = GrupoMarcas(contenedores)
        # Las marcas de formato se agrupan y ordenan aquí una sola vez.  El
        # panel de lectura las consulta cada vez que carga un tramo de texto,
        # y en un libro con decenas de miles de cursivas rehacer la lista en
        # cada consulta sería el mayor coste de todo el desplazamiento.
        tramos_formato: list[Marca] = []
        for tipo in FORMATO:
            tramos_formato.extend(por_tipo.get(int(tipo), ()))
        self.formato = GrupoMarcas(tramos_formato)

    def grupo(self, tipo: TipoMarca) -> GrupoMarcas:
        """Devuelve el grupo de un tipo (vacío si el documento no tiene ninguno)."""
        existente = self.grupos.get(int(tipo))
        if existente is None:
            existente = GrupoMarcas(())
            self.grupos[int(tipo)] = existente
        return existente

    def cantidad(self, tipo: TipoMarca) -> int:
        """Número de marcas de un tipo."""
        grupo = self.grupos.get(int(tipo))
        return len(grupo) if grupo else 0

    def tiene(self, tipo: TipoMarca) -> bool:
        """Indica si el documento contiene al menos una marca de ese tipo."""
        return self.cantidad(tipo) > 0

    def contenedor_en(self, posicion: int) -> Marca | None:
        """Devuelve la lista o tabla más interna que contiene ``posicion``.

        Cuando hay contenedores anidados (una lista dentro de otra) se
        devuelve el más interno, que es el que empieza más tarde.
        """
        candidatos = [
            marca
            for marca in self.contenedores
            if marca.posicion <= posicion < marca.posicion + marca.longitud
        ]
        if not candidatos:
            return None
        # El más interno: el que empieza más tarde; a igualdad, el más corto.
        return min(candidatos, key=lambda m: (-m.posicion, m.longitud))

    def formato_en_rango(self, inicio: int, fin: int, maximo: int) -> list[Marca] | None:
        """Marcas de formato que se solapan con el tramo ``[inicio, fin)``.

        Devuelve ``None`` si hay más de ``maximo``, para que quien llama pueda
        renunciar a aplicarlas en lugar de bloquear la interfaz.

        La búsqueda arranca en el primer tramo que puede alcanzar ``inicio``
        (localizado con búsqueda binaria) y no en el principio del libro.
        """
        grupo = self.formato
        if not grupo:
            return []
        # Los tramos de formato son cortos, pero para no depender de ello se
        # retrocede un poco antes del punto de inicio y se filtra después.
        primero = max(bisect.bisect_left(grupo.posiciones, inicio) - 64, 0)
        resultado: list[Marca] = []
        for indice in range(primero, len(grupo)):
            marca = grupo[indice]
            if marca.posicion >= fin:
                break
            if marca.posicion + marca.longitud > inicio:
                resultado.append(marca)
                if len(resultado) > maximo:
                    return None
        return resultado

    def marca_que_cubre(self, tipo: TipoMarca, posicion: int) -> Marca | None:
        """Marca de ese tipo dentro de la cual cae ``posicion``, o ``None``.

        Se busca con :mod:`bisect` la última marca que empieza en ``posicion``
        o antes y se retrocede un poco, porque las marcas de idioma pueden
        anidarse —una frase en latín dentro de una cita en inglés— y en ese
        caso la que vale es la más interna, que es la que empieza más tarde.
        """
        grupo = self.grupos.get(int(tipo))
        if not grupo:
            return None
        indice = grupo.indice_actual(posicion)
        for atras in range(indice, max(indice - 32, -1), -1):
            marca = grupo[atras]
            if marca.posicion <= posicion < marca.posicion + max(marca.longitud, 1):
                return marca
        return None

    def todas(self) -> list[Marca]:
        """Todas las marcas del documento en una única lista ordenada."""
        resultado: list[Marca] = []
        for grupo in self.grupos.values():
            resultado.extend(grupo.marcas)
        resultado.sort(key=lambda marca: marca.posicion)
        return resultado
