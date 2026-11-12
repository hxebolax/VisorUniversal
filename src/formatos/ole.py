# -*- coding: utf-8 -*-
"""El envoltorio de los archivos de Office de hace veinte años.

Un `.doc`, un `.xls` o un `.ppt` de Office 97 no son un archivo: son **un
sistema de archivos dentro de un archivo**.  Microsoft lo llamó *Compound File
Binary*, y por dentro se parece muchísimo a un disquete formateado en FAT: hay
un sector de arranque, una tabla de asignación que dice qué sector va detrás de
cuál, un directorio con nombres, y hasta una segunda tabla más pequeña para los
flujos diminutos, que es lo mismo que hacía el DOS para no desperdiciar un
sector entero en un archivo de doscientos bytes.

Este módulo lee ese envoltorio.  No entiende de textos ni de párrafos: lo único
que hace es dar los flujos que hay dentro, por su nombre, y de ahí para arriba
ya se ocupa cada formato.

**Por qué está escrito aquí y no se usa una biblioteca.**  Es la misma razón que
con el LZX de los archivos de ayuda y con el BZZ de los DjVu: son doscientas
líneas que no van a cambiar nunca —el formato lleva congelado desde 1997— y
meter una dependencia por esto significaría arrastrarla en el ejecutable, en la
licencia y en cada actualización.  El material de consulta está en
``adjuntos/Estudio/olefile`` y en ``adjuntos/Estudio/catdoc``.

**Lo que no hace, a propósito.**  No escribe, no descifra y no toca el archivo.
Y ante un archivo roto no revienta: devuelve lo que se pueda leer, porque un
`.doc` de hace veinte años recuperado de un disquete es exactamente el caso para
el que hace falta esto.
"""

from __future__ import annotations

import struct
from pathlib import Path

from nucleo.registro import obtener_registro

log = obtener_registro(__name__)

#: Los ocho bytes con los que empieza cualquier archivo de estos.
FIRMA = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

#: Marcas especiales de la tabla de asignación.
LIBRE = 0xFFFFFFFF
FIN_DE_CADENA = 0xFFFFFFFE
SECTOR_TABLA = 0xFFFFFFFD
SECTOR_DIFAT = 0xFFFFFFFC

#: Tope de sectores que se siguen en una cadena.  Un archivo sano nunca llega;
#: uno corrupto puede tener una cadena que se muerde la cola, y sin este tope se
#: leería para siempre.
MAXIMOS_SECTORES = 1 << 20

#: Tamaño máximo que se acepta de un flujo, para no vaciar la memoria con un
#: archivo mal formado que diga que un flujo ocupa cuatro gigabytes.
MAXIMO_FLUJO = 256 * 1024 * 1024


class ErrorOLE(Exception):
    """El archivo no es un contenedor OLE o está demasiado roto."""


class Entrada:
    """Una entrada del directorio: un flujo o una carpeta.

    :param nombre: Cómo se llama.  Los nombres internos empiezan a menudo por un
        carácter de control —``\\x05SummaryInformation``—, y se conservan tal
        cual porque es como hay que pedirlos.
    :param tipo: 1 carpeta, 2 flujo, 5 la raíz.
    :param inicio: Primer sector de su cadena.
    :param tamano: Cuántos bytes ocupa.
    """

    __slots__ = ("nombre", "tipo", "inicio", "tamano", "izquierda", "derecha",
                 "hijo")

    def __init__(self, nombre: str, tipo: int, inicio: int, tamano: int,
                 izquierda: int, derecha: int, hijo: int) -> None:
        self.nombre = nombre
        self.tipo = tipo
        self.inicio = inicio
        self.tamano = tamano
        self.izquierda = izquierda
        self.derecha = derecha
        self.hijo = hijo

    @property
    def es_flujo(self) -> bool:
        return self.tipo == 2


class Contenedor:
    """Un archivo compuesto abierto, con sus flujos accesibles por nombre."""

    def __init__(self, datos: bytes) -> None:
        self.datos = datos
        if not datos.startswith(FIRMA):
            raise ErrorOLE("no empieza por la firma de un archivo compuesto")
        if len(datos) < 512:
            raise ErrorOLE("el archivo se corta antes de la cabecera")
        self._leer_cabecera()
        self._tabla = self._leer_tabla()
        self._entradas = self._leer_directorio()
        self._mini_tabla = self._leer_mini_tabla()
        self._mini_flujo = self._leer_mini_flujo()

    # -- la cabecera ---------------------------------------------------------

    def _leer_cabecera(self) -> None:
        """Los datos del sector de arranque."""
        cabecera = self.datos[:512]
        (self.desplazamiento_sector,
         self.desplazamiento_mini) = struct.unpack_from("<HH", cabecera, 30)
        if not 7 <= self.desplazamiento_sector <= 20:
            raise ErrorOLE("tamaño de sector imposible: 2^%d"
                           % self.desplazamiento_sector)
        self.tamano_sector = 1 << self.desplazamiento_sector
        self.tamano_mini = 1 << self.desplazamiento_mini
        (self.cuantas_tabla,) = struct.unpack_from("<I", cabecera, 44)
        (self.primer_directorio,) = struct.unpack_from("<I", cabecera, 48)
        (self.corte_mini,) = struct.unpack_from("<I", cabecera, 56)
        (self.primera_mini_tabla,) = struct.unpack_from("<I", cabecera, 60)
        (self.cuantas_mini_tabla,) = struct.unpack_from("<I", cabecera, 64)
        (self.primera_difat,) = struct.unpack_from("<I", cabecera, 68)
        (self.cuantas_difat,) = struct.unpack_from("<I", cabecera, 72)

    def _sector(self, numero: int) -> bytes:
        """Los bytes de un sector. El sector 0 va justo detrás de la cabecera."""
        inicio = (numero + 1) * self.tamano_sector
        return self.datos[inicio:inicio + self.tamano_sector]

    def _enteros(self, bloque: bytes) -> list[int]:
        """Un sector interpretado como una lista de números de cuatro bytes."""
        cuantos = len(bloque) // 4
        return list(struct.unpack_from("<%dI" % cuantos, bloque, 0))

    # -- la tabla de asignación ----------------------------------------------

    def _sectores_de_la_tabla(self) -> list[int]:
        """Dónde están los sectores que forman la tabla de asignación.

        Los primeros ciento nueve caben en la propia cabecera; si hacen falta
        más, se encadenan en sectores aparte, y el último número de cada uno
        apunta al siguiente.  Es el mismo truco de la FAT del DOS, y por la
        misma razón: la cabecera tiene un tamaño fijo.
        """
        listado = self._enteros(self.datos[76:512])
        sectores = [numero for numero in listado if numero < SECTOR_DIFAT]
        siguiente = self.primera_difat
        vueltas = 0
        while siguiente < SECTOR_DIFAT and vueltas < MAXIMOS_SECTORES:
            bloque = self._enteros(self._sector(siguiente))
            if not bloque:
                break
            sectores.extend(numero for numero in bloque[:-1]
                            if numero < SECTOR_DIFAT)
            siguiente = bloque[-1]
            vueltas += 1
        return sectores[:max(self.cuantas_tabla, len(sectores))]

    def _leer_tabla(self) -> list[int]:
        """La tabla entera: para cada sector, cuál es el siguiente."""
        tabla: list[int] = []
        for numero in self._sectores_de_la_tabla():
            tabla.extend(self._enteros(self._sector(numero)))
        if not tabla:
            raise ErrorOLE("el archivo no tiene tabla de asignación")
        return tabla

    def _cadena(self, inicio: int, tabla: list[int]) -> list[int]:
        """Los sectores de un flujo, siguiendo la tabla desde el primero."""
        salida: list[int] = []
        actual = inicio
        vistos = set()
        while (actual < len(tabla) and actual not in vistos
               and len(salida) < MAXIMOS_SECTORES):
            vistos.add(actual)
            salida.append(actual)
            actual = tabla[actual]
            if actual >= SECTOR_DIFAT:
                break
        return salida

    # -- el directorio -------------------------------------------------------

    def _leer_directorio(self) -> list[Entrada]:
        """Las entradas del directorio, en el orden en que están guardadas."""
        crudo = b"".join(self._sector(numero) for numero
                         in self._cadena(self.primer_directorio, self._tabla))
        entradas = []
        for inicio in range(0, len(crudo) - 127, 128):
            trozo = crudo[inicio:inicio + 128]
            (largo_nombre,) = struct.unpack_from("<H", trozo, 64)
            largo_nombre = max(0, min(largo_nombre, 64))
            nombre = trozo[:largo_nombre].decode("utf-16-le", "replace")
            nombre = nombre.rstrip("\x00")
            tipo = trozo[66]
            izquierda, derecha, hijo = struct.unpack_from("<III", trozo, 68)
            (primero,) = struct.unpack_from("<I", trozo, 116)
            (tamano,) = struct.unpack_from("<Q", trozo, 120)
            if tamano > MAXIMO_FLUJO:
                # En los archivos de la versión 3 los cuatro bytes de arriba no
                # son parte del tamaño: son relleno que a veces trae basura.
                tamano = struct.unpack_from("<I", trozo, 120)[0]
            entradas.append(Entrada(nombre, tipo, primero, tamano,
                                    izquierda, derecha, hijo))
        if not entradas:
            raise ErrorOLE("el directorio está vacío")
        return entradas

    def _leer_mini_tabla(self) -> list[int]:
        """La tabla de los flujos pequeños."""
        tabla: list[int] = []
        for numero in self._cadena(self.primera_mini_tabla, self._tabla):
            tabla.extend(self._enteros(self._sector(numero)))
        return tabla

    def _leer_mini_flujo(self) -> bytes:
        """Dónde viven los flujos pequeños: todos juntos, en uno grande.

        Los flujos por debajo del corte —normalmente cuatro kilobytes— no ocupan
        sectores propios: se guardan seguidos dentro de un único flujo que
        cuelga de la raíz, y se trocean con su propia tabla.  Es exactamente lo
        que hacían los sistemas de archivos para no desperdiciar espacio.
        """
        raiz = self._entradas[0]
        if raiz.tipo != 5 or not raiz.tamano:
            return b""
        return b"".join(self._sector(numero) for numero
                        in self._cadena(raiz.inicio, self._tabla))

    # -- lo que se usa desde fuera -------------------------------------------

    def nombres(self) -> list[str]:
        """Los nombres de los flujos que hay dentro."""
        return [entrada.nombre for entrada in self._entradas if entrada.es_flujo]

    def existe(self, nombre: str) -> bool:
        return self._buscar(nombre) is not None

    def _buscar(self, nombre: str):
        """La entrada que se llama así, mirando también sin distinguir mayúsculas."""
        for entrada in self._entradas:
            if entrada.es_flujo and entrada.nombre == nombre:
                return entrada
        plano = nombre.lower()
        for entrada in self._entradas:
            if entrada.es_flujo and entrada.nombre.lower() == plano:
                return entrada
        return None

    def flujo(self, nombre: str) -> bytes:
        """El contenido de un flujo, o vacío si no está.

        Un flujo que no está no es un error: los formatos antiguos guardan cosas
        opcionales, y preguntar y no encontrarlas es lo normal.
        """
        entrada = self._buscar(nombre)
        if entrada is None:
            return b""
        return self._contenido(entrada)

    def _contenido(self, entrada: Entrada) -> bytes:
        """Junta los trozos de un flujo, del sitio que le toque."""
        tamano = min(entrada.tamano, MAXIMO_FLUJO)
        if tamano == 0:
            return b""
        if tamano < self.corte_mini and self._mini_flujo:
            trozos = []
            for numero in self._cadena(entrada.inicio, self._mini_tabla):
                inicio = numero * self.tamano_mini
                trozos.append(self._mini_flujo[inicio:inicio + self.tamano_mini])
            return b"".join(trozos)[:tamano]
        trozos = [self._sector(numero)
                  for numero in self._cadena(entrada.inicio, self._tabla)]
        return b"".join(trozos)[:tamano]


def es_compuesto(ruta) -> bool:
    """Dice si un archivo es un contenedor OLE, mirando sus ocho primeros bytes."""
    try:
        with open(ruta, "rb") as archivo:
            return archivo.read(8) == FIRMA
    except OSError:
        return False


def abrir(ruta) -> Contenedor:
    """Abre un archivo compuesto entero.

    Se lee de una vez y no por trozos: los `.doc` y los `.xls` de esta época
    ocupan megabytes, no gigabytes, y tenerlo entero en memoria evita miles de
    saltos por el disco para recomponer una cadena de sectores.

    :raises ErrorOLE: Si no es uno de estos archivos o está irrecuperable.
    """
    try:
        datos = Path(ruta).read_bytes()
    except OSError as error:
        raise ErrorOLE("no se ha podido leer: %s" % error) from error
    return Contenedor(datos)
