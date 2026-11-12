# -*- coding: utf-8 -*-
"""Marcas de capítulo dentro de un MP3.

Al exportar un libro a un solo archivo de audio salían diez horas seguidas sin
un solo punto por el que agarrarse.  En un reproductor corriente eso significa
que volver al capítulo siete es adelantar a ciegas y comprobar; y quien no ve no
tiene ni la barra de progreso para hacerse una idea de por dónde va.

Un MP3 **sí puede llevar capítulos**: lo define el «ID3v2 Chapter Frame
Addendum», y lo entienden los reproductores de audiolibros y de pódcast —que es
lo que la gente usa para escuchar libros— además de VLC y foobar2000.

Cómo es una etiqueta con capítulos
----------------------------------

La etiqueta va **delante** de los datos de audio y se compone de:

* una cabecera ``ID3`` con la versión y el tamaño de todo lo que sigue;
* los datos de siempre: título (``TIT2``), autor (``TPE1``), álbum (``TALB``);
* un marco ``CHAP`` **por capítulo**, con el instante en que empieza y el
  instante en que acaba, en milisegundos, y dentro de él otro ``TIT2`` con su
  título;
* un marco ``CTOC`` que enumera los capítulos en orden y dice que él es el
  índice principal.

Se escribe **ID3v2.3** y no la 2.4, que es más nueva, porque los reproductores
de audiolibros la aceptan mejor: la 2.4 cambió cómo se escriben los tamaños de
los marcos y hay programas que todavía se atragantan.  El tamaño de la
cabecera, en cambio, va «a prueba de sincronización» en las dos versiones —siete
bits por byte, para que no se pueda confundir con el comienzo de un trozo de
audio—, y así se escribe aquí.

Todo se escribe a mano, con la biblioteca estándar.  Es un formato de campos de
longitud fija y cadenas terminadas en cero: traerse una biblioteca entera para
esto sería más código de terceros que código propio.
"""

from __future__ import annotations

import struct
from pathlib import Path

from .registro import obtener_registro

log = obtener_registro(__name__)

#: Codificación con la que se escriben los textos: UTF-16 con marca de orden,
#: que es la única de la ID3v2.3 que admite acentos y eñes.  La otra es
#: Latin-1, y un título con una «ñ» saldría roto en cualquier reproductor.
UTF16 = 1

#: Cuántos capítulos caben en el índice.  No es una decisión propia: el campo
#: que cuenta las entradas del ``CTOC`` ocupa **un byte**, y no da para más.
MAXIMO_EN_INDICE = 255


def _sincroseguro(valor: int) -> bytes:
    """Escribe un número con siete bits por byte, como pide la cabecera ID3.

    Es lo que impide que el tamaño de la etiqueta contenga por casualidad la
    secuencia con la que empieza un trozo de audio, cosa que haría que un
    reproductor se pusiera a sonar en mitad de la etiqueta.
    """
    valor = max(0, min(valor, 0x0FFFFFFF))
    return bytes(((valor >> 21) & 0x7F, (valor >> 14) & 0x7F,
                  (valor >> 7) & 0x7F, valor & 0x7F))


def _texto(valor: str) -> bytes:
    """Un texto tal como va dentro de un marco: su codificación y él."""
    return bytes([UTF16]) + (valor or "").encode("utf-16") + b"\x00\x00"


def _marco(identificador: str, cuerpo: bytes) -> bytes:
    """Un marco completo: su nombre, su tamaño, sus banderas y su contenido."""
    return (identificador.encode("ascii") + struct.pack(">L", len(cuerpo))
            + b"\x00\x00" + cuerpo)


def _marco_de_texto(identificador: str, valor: str) -> bytes:
    """Un marco de los normales: título, autor, álbum..."""
    return _marco(identificador, _texto(valor))


def _identificador(numero: int) -> bytes:
    """Nombre interno de un capítulo.  No se ve: solo enlaza el índice."""
    return ("cap%03d" % numero).encode("ascii") + b"\x00"


class Capitulo:
    """Un capítulo del audio: dónde empieza, dónde acaba y cómo se llama.

    :param titulo: Lo que enseña el reproductor.
    :param inicio: Milisegundos desde el principio del archivo.
    :param fin: Milisegundos en los que termina.
    """

    __slots__ = ("titulo", "inicio", "fin")

    def __init__(self, titulo: str, inicio: int, fin: int) -> None:
        self.titulo = (titulo or "").strip()
        self.inicio = max(0, int(inicio))
        self.fin = max(self.inicio, int(fin))


def _marco_capitulo(numero: int, capitulo: Capitulo) -> bytes:
    """Escribe un ``CHAP`` con su título dentro."""
    # Los desplazamientos en bytes se dejan en «no se sabe», que es lo que
    # significa poner todos los bits a uno.  Calcularlos exigiría recorrer el
    # MP3 trozo a trozo, y los reproductores usan los tiempos.
    cuerpo = (_identificador(numero)
              + struct.pack(">LLLL", capitulo.inicio, capitulo.fin,
                            0xFFFFFFFF, 0xFFFFFFFF)
              + _marco_de_texto("TIT2", capitulo.titulo))
    return _marco("CHAP", cuerpo)


def _marco_indice(cuantos: int, titulo: str) -> bytes:
    """Escribe el ``CTOC`` que enumera los capítulos.

    Las banderas valen ``0b11``: el primer bit dice que este es **el** índice
    del archivo, y el segundo que sus entradas van seguidas y en orden, que es
    lo que hace que el reproductor las trate como capítulos de un libro y no
    como pistas sueltas.
    """
    hijos = b"".join(_identificador(numero) for numero in range(cuantos))
    cuerpo = (b"indice\x00" + bytes([0b11, cuantos]) + hijos
              + _marco_de_texto("TIT2", titulo))
    return _marco("CTOC", cuerpo)


def etiqueta(capitulos, titulo: str = "", autor: str = "",
             album: str = "") -> bytes:
    """Arma la etiqueta ID3v2.3 entera, lista para ir delante del audio."""
    marcos = []
    if titulo:
        marcos.append(_marco_de_texto("TIT2", titulo))
    if autor:
        marcos.append(_marco_de_texto("TPE1", autor))
    if album or titulo:
        marcos.append(_marco_de_texto("TALB", album or titulo))
    # El índice va antes que los capítulos: no lo exige la norma, pero es el
    # orden en que lo escriben los programas de pódcast y el que más
    # reproductores han probado alguna vez.
    en_indice = min(len(capitulos), MAXIMO_EN_INDICE)
    if capitulos:
        marcos.append(_marco_indice(en_indice, titulo or album))
    for numero, capitulo in enumerate(capitulos):
        marcos.append(_marco_capitulo(numero, capitulo))
    cuerpo = b"".join(marcos)
    return b"ID3\x03\x00\x00" + _sincroseguro(len(cuerpo)) + cuerpo


def _sin_etiqueta(datos: bytes) -> bytes:
    """Devuelve el audio sin la etiqueta ID3 que ya trajera.

    El compresor puede haber puesto una suya; dejar dos seguidas hace que
    algunos reproductores lean la primera y no vean los capítulos.
    """
    if len(datos) < 10 or datos[:3] != b"ID3":
        return datos
    tamano = 0
    for byte in datos[6:10]:
        tamano = (tamano << 7) | (byte & 0x7F)
    return datos[10 + tamano:]


def escribir_capitulos(archivo, capitulos, titulo: str = "", autor: str = "",
                       album: str = "") -> int:
    """Le pone las marcas de capítulo a un MP3 que ya existe.

    :param archivo: Ruta del MP3.
    :param capitulos: Lista de :class:`Capitulo` en orden.
    :return: Cuántos capítulos han quedado en el índice.  Puede ser menos que
             los que se pidieron, porque el índice no admite más de 255.
    :raises OSError: Si no se puede leer o escribir el archivo.
    """
    ruta = Path(archivo)
    datos = ruta.read_bytes()
    audio = _sin_etiqueta(datos)
    ruta.write_bytes(etiqueta(list(capitulos), titulo, autor, album) + audio)
    en_indice = min(len(capitulos), MAXIMO_EN_INDICE)
    if len(capitulos) > MAXIMO_EN_INDICE:
        log.warning("El índice del MP3 solo admite %d capítulos y el libro tiene %d: "
                    "los demás quedan escritos pero fuera del índice",
                    MAXIMO_EN_INDICE, len(capitulos))
    log.info("Marcas de capítulo escritas en %s: %d", ruta.name, en_indice)
    return en_indice


# ---------------------------------------------------------------------------
# La hoja de pistas, para cuando el archivo es un WAV
# ---------------------------------------------------------------------------

def _tiempo_cue(milisegundos: int) -> str:
    """Un instante como lo escribe una hoja de pistas: ``mm:ss:ff``.

    Los «ff» son fotogramas de setenta y cinco por segundo, que es la unidad
    del disco compacto y la que heredó este formato.
    """
    total = max(0, milisegundos)
    minutos, resto = divmod(total // 1000, 60)
    fotogramas = int((total % 1000) * 75 / 1000)
    return "%02d:%02d:%02d" % (minutos, resto, fotogramas)


def hoja_de_pistas(capitulos, nombre_audio: str, titulo: str = "",
                   autor: str = "") -> str:
    """Escribe una hoja de pistas (``.cue``) con los capítulos.

    Un WAV no admite capítulos por dentro, así que para ese formato se deja al
    lado un archivo ``.cue``, que es lo que entienden foobar2000, VLC y los
    programas de audio.  No es tan cómodo como llevarlos dentro, pero es lo que
    hay, y es mejor que quedarse sin ellos.
    """
    lineas = []
    if autor:
        lineas.append('PERFORMER "%s"' % _sin_comillas(autor))
    if titulo:
        lineas.append('TITLE "%s"' % _sin_comillas(titulo))
    lineas.append('FILE "%s" WAVE' % _sin_comillas(nombre_audio))
    for numero, capitulo in enumerate(capitulos, start=1):
        lineas.append("  TRACK %02d AUDIO" % numero)
        lineas.append('    TITLE "%s"' % _sin_comillas(capitulo.titulo))
        lineas.append("    INDEX 01 %s" % _tiempo_cue(capitulo.inicio))
    return "\n".join(lineas) + "\n"


def _sin_comillas(texto: str) -> str:
    """Quita lo que rompería una línea de la hoja de pistas."""
    return " ".join((texto or "").replace('"', "'").split())
