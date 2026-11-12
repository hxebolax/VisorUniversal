# -*- coding: utf-8 -*-
"""Hallazgos: lo que se ha encontrado en un PDF y qué se puede hacer al respecto.

Hasta ahora el programa decía de un PDF una frase —«PDF etiquetado: 12 de 12
páginas con estructura»— y poco más.  Está bien para saber a qué atenerse, pero
no sirve para lo otro que hace falta: **saber qué le pasa al archivo y quién lo
puede arreglar**.

Un hallazgo es exactamente eso.  No es un error del programa, es una
observación sobre el documento:

* «La página 34 es una fotografía sin texto: hay que reconocerla.»
* «Hay 12 imágenes sin descripción.  Se pueden describir con Control+Alt+D.»
* «El documento no declara su idioma, así que la voz lo leerá en el del
  programa.»
* «Las tablas de la página 7 no marcan cuál es su fila de encabezados: al
  recorrerlas con las órdenes de tabla no se anunciará de qué columna es cada
  número.»

Cada uno lleva **dónde** (página, elemento), **cuánto importa**
(:class:`Severidad`), **qué lo detectó** y, cuando existe, **qué hacer**.  Esa
última parte es la que convierte un informe en algo útil: quien lee sabe si
merece la pena insistir, y quien publica sabe qué volver a exportar.

Las normas se citan por su cláusula (``ISO 14289-1, 7.4``) porque es lo que
permite ir al texto original y porque un número de cláusula no envejece: la
redacción de una regla cambia entre versiones, su sitio en la norma no.

El módulo no depende de ningún motor de PDF a propósito: lo usan por igual el
diagnóstico (:mod:`formatos.pdf_diagnostico`), la auditoría de accesibilidad
(:mod:`formatos.pdf_auditoria`) y la reparación
(:mod:`formatos.pdf_reparacion`).
"""

from __future__ import annotations

from enum import IntEnum
from typing import Iterable, Iterator, NamedTuple

from nucleo.idioma import _


class Severidad(IntEnum):
    """Cuánto importa un hallazgo.

    El orden numérico es el de gravedad creciente, para poder ordenar la lista
    con ``sorted`` y quedarse con lo peor con ``max``.  Los valores son
    estables porque se guardan en la caché del documento.
    """

    #: Un dato de interés que no impide nada.  «El PDF está linealizado.»
    INFORMACION = 0

    #: Algo que empeora la lectura pero que tiene arreglo o alternativa.
    #: «Doce imágenes sin descripción.»
    AVISO = 1

    #: Algo que impide leer una parte del documento.  «La página 34 no se ha
    #: podido convertir.»
    ERROR = 2

    #: Algo que impide leer el documento entero.  «El archivo está cifrado y
    #: hace falta una contraseña.»
    GRAVE = 3


#: Nombre de cada severidad tal como se anuncia.  Se resuelve al usarlo, no
#: aquí, porque el idioma de la interfaz puede cambiar sin reiniciar.
_NOMBRES = {
    Severidad.INFORMACION: lambda: _("información"),
    Severidad.AVISO: lambda: _("aviso"),
    Severidad.ERROR: lambda: _("error"),
    Severidad.GRAVE: lambda: _("grave"),
}


def nombre_severidad(severidad: Severidad) -> str:
    """Devuelve el nombre de una severidad en el idioma de la interfaz."""
    return _NOMBRES.get(severidad, lambda: _("aviso"))()


class Hallazgo(NamedTuple):
    """Una observación sobre el documento, con su sitio y su remedio.

    :param codigo: Identificador estable y corto, en mayúsculas, del tipo de
                   hallazgo (``"IMAGEN_SIN_ALTERNATIVA"``).  No se traduce: es
                   lo que permite agrupar, contar y filtrar sin depender del
                   idioma en que esté escrito el mensaje.
    :param mensaje: La frase que lee el usuario.  Va ya traducida.
    :param severidad: Cuánto importa.
    :param pagina: Página del PDF (empezando en 1) o ``0`` si es del documento
                   entero.
    :param cantidad: Cuántas veces ocurre.  Doce imágenes sin describir son un
                     hallazgo con ``cantidad=12``, no doce hallazgos: en un
                     informe hablado, doce líneas iguales son ruido.
    :param remedio: Qué puede hacer quien lee.  Vacío si no hay nada que hacer
                    desde el programa.
    :param norma: Cláusula de la norma que lo respalda, si la hay
                  (``"ISO 14289-1, 7.4"``).  Es una referencia, no una
                  certificación: véase :mod:`formatos.pdf_auditoria`.
    :param detalle: Información técnica para el registro.  No se anuncia.
    """

    codigo: str
    mensaje: str
    severidad: Severidad = Severidad.AVISO
    pagina: int = 0
    cantidad: int = 1
    remedio: str = ""
    norma: str = ""
    detalle: str = ""

    def redactar(self, con_norma: bool = False) -> str:
        """Escribe el hallazgo en una frase, con su sitio y su remedio.

        :param con_norma: Añadir la cláusula de la norma.  Interesa a quien
                          publica el documento y estorba a quien solo quiere
                          leerlo, así que va apagado por omisión.
        """
        partes = [self.mensaje]
        if self.pagina:
            partes.append(_("Página %d.") % self.pagina)
        if self.remedio:
            partes.append(self.remedio)
        if con_norma and self.norma:
            partes.append("(%s)" % self.norma)
        return " ".join(parte.strip() for parte in partes if parte.strip())


class ColeccionHallazgos:
    """Los hallazgos de un documento, agrupados y sin repeticiones.

    Agrupa por sí sola: añadir doce veces el mismo código con la misma página
    no da doce entradas, da una con ``cantidad=12``.  Eso importa porque el
    informe se lee en voz alta y porque un PDF de mil páginas mal etiquetado
    produciría, sin agrupar, miles de líneas idénticas.

    Se conserva el orden en que se encontraron: es el orden del documento, que
    es el que espera quien lo está revisando.
    """

    __slots__ = ("_por_clave", "_orden")

    def __init__(self, hallazgos: Iterable[Hallazgo] = ()) -> None:
        self._por_clave: dict[tuple[str, int], Hallazgo] = {}
        self._orden: list[tuple[str, int]] = []
        for hallazgo in hallazgos:
            self.anadir(hallazgo)

    def anadir(self, hallazgo: Hallazgo) -> None:
        """Añade un hallazgo, sumándolo al que ya hubiera igual."""
        clave = (hallazgo.codigo, hallazgo.pagina)
        existente = self._por_clave.get(clave)
        if existente is None:
            self._por_clave[clave] = hallazgo
            self._orden.append(clave)
            return
        self._por_clave[clave] = existente._replace(
            cantidad=existente.cantidad + hallazgo.cantidad,
            # Si el mismo hallazgo llega con dos severidades distintas, manda
            # la peor: si una página falló del todo, da igual que otra vez solo
            # avisara.
            severidad=max(existente.severidad, hallazgo.severidad),
        )

    def extender(self, hallazgos: Iterable[Hallazgo]) -> None:
        """Añade varios hallazgos de una vez."""
        for hallazgo in hallazgos:
            self.anadir(hallazgo)

    def __iter__(self) -> Iterator[Hallazgo]:
        """Recorre los hallazgos en el orden en que se encontraron."""
        return (self._por_clave[clave] for clave in self._orden)

    def __len__(self) -> int:
        """Cuántos hallazgos distintos hay."""
        return len(self._orden)

    def __bool__(self) -> bool:
        """Indica si hay algún hallazgo."""
        return bool(self._orden)

    def de_severidad(self, minima: Severidad) -> list[Hallazgo]:
        """Devuelve los hallazgos de esa severidad o peor, del peor al mejor.

        Dentro de la misma severidad se conserva el orden del documento.
        """
        elegidos = [h for h in self if h.severidad >= minima]
        return sorted(elegidos, key=lambda h: -int(h.severidad))

    def peor(self) -> Severidad:
        """Devuelve la severidad más alta encontrada."""
        return max((h.severidad for h in self), default=Severidad.INFORMACION)

    def cuantos(self, codigo: str) -> int:
        """Suma las veces que ha ocurrido un código, en todas las páginas."""
        return sum(h.cantidad for h in self if h.codigo == codigo)

    def redactar(self, maximo: int = 8, minima: Severidad = Severidad.AVISO,
                 con_norma: bool = False) -> str:
        """Escribe los hallazgos que merece la pena contar, en varias líneas.

        :param maximo: Cuántos como mucho.  El resto se resume en una línea
                       final: una lista de cuarenta avisos no la escucha nadie,
                       y los que importan están al principio porque van
                       ordenados por gravedad.
        :param minima: Severidad a partir de la cual se cuenta.
        :param con_norma: Añadir las cláusulas de la norma.
        """
        elegidos = self.de_severidad(minima)
        if not elegidos:
            return ""
        lineas = [h.redactar(con_norma) for h in elegidos[:maximo]]
        restantes = len(elegidos) - len(lineas)
        if restantes > 0:
            lineas.append(_("Y %d observaciones más en el registro.") % restantes)
        return "\n".join(lineas)


def informativo(codigo: str, mensaje: str, **extra) -> Hallazgo:
    """Atajo para un hallazgo informativo."""
    return Hallazgo(codigo, mensaje, Severidad.INFORMACION, **extra)


def aviso(codigo: str, mensaje: str, **extra) -> Hallazgo:
    """Atajo para un aviso."""
    return Hallazgo(codigo, mensaje, Severidad.AVISO, **extra)


def error(codigo: str, mensaje: str, **extra) -> Hallazgo:
    """Atajo para un error."""
    return Hallazgo(codigo, mensaje, Severidad.ERROR, **extra)


def grave(codigo: str, mensaje: str, **extra) -> Hallazgo:
    """Atajo para un hallazgo grave."""
    return Hallazgo(codigo, mensaje, Severidad.GRAVE, **extra)
