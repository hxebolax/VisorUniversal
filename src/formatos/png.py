# -*- coding: utf-8 -*-
"""Codificador de PNG, para pasarle una página rasterizada al OCR.

Los dos motores de reconocimiento —el de Windows y el de la inteligencia
artificial— quieren la imagen en un formato conocido, y lo que devuelve el
motor de PDF es un mapa de bits en crudo.  Hace falta algo que traduzca de uno
a otro.

Lo habitual sería tirar de Pillow, pero para esto es desproporcionado: un PNG
sin filtros ni entrelazado son cuatro bloques con una cabecera, los datos
comprimidos con :mod:`zlib` —que ya viene con Python— y una suma de
comprobación.  Escribirlo aquí son treinta líneas y ahorra una dependencia de
varios megabytes que además habría que empaquetar en el ejecutable.

El PNG que sale no está optimizado: se comprime rápido y sin filtros por línea.
Da igual, porque la imagen no se guarda en ningún sitio: se genera, se manda al
OCR y se tira.
"""

from __future__ import annotations

import struct
import zlib

#: Formato de mapa de bits de PDFium en el que los canales van en orden BGR.
#: PDFium devuelve los píxeles así, y el PNG los quiere en RGB.
FORMATO_BGR = 2
FORMATO_BGRA = 3
FORMATO_BGRX = 4


def _bloque(tipo: bytes, datos: bytes) -> bytes:
    """Arma un bloque de PNG con su longitud y su suma de comprobación."""
    return (struct.pack(">I", len(datos)) + tipo + datos
            + struct.pack(">I", zlib.crc32(tipo + datos) & 0xFFFFFFFF))


def codificar(ancho: int, alto: int, filas: list[bytes]) -> bytes:
    """Arma un PNG en color verdadero a partir de sus filas en RGB.

    :param filas: Una entrada por fila, con ``ancho * 3`` bytes en orden RGB.
    """
    crudo = b"".join(b"\x00" + fila for fila in filas)   # 0 = sin filtro
    cabecera = struct.pack(">IIBBBBB", ancho, alto, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n"
            + _bloque(b"IHDR", cabecera)
            + _bloque(b"IDAT", zlib.compress(crudo, 6))
            + _bloque(b"IEND", b""))


def codificar_un_bit(ancho: int, alto: int, filas: list[bytes]) -> bytes:
    """Arma un PNG en blanco y negro de verdad: un bit por píxel.

    Es lo que sale de la máscara de un DjVu, y guardarla como una imagen en
    color la haría veinticuatro veces más grande sin añadir ni un matiz: en la
    máscara solo hay tinta y papel.  Un uno es blanco y un cero, negro, que es
    como lo entiende el PNG con un bit de profundidad.

    :param filas: Una entrada por fila, de arriba abajo, con los píxeles
        empaquetados a ocho por byte y el primero en el bit más alto.
    """
    crudo = b"".join(b"\x00" + fila for fila in filas)   # 0 = sin filtro
    cabecera = struct.pack(">IIBBBBB", ancho, alto, 1, 0, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n"
            + _bloque(b"IHDR", cabecera)
            + _bloque(b"IDAT", zlib.compress(crudo, 6))
            + _bloque(b"IEND", b""))


def desde_bitmap(bitmap) -> bytes:
    """Convierte un mapa de bits de ``pypdfium2`` en un PNG.

    Se atiende al formato que declare el mapa: PDFium entrega los canales en
    orden **BGR**, al revés de lo que quiere el PNG, y a veces con un cuarto
    canal de transparencia que aquí sobra.
    """
    ancho, alto = bitmap.width, bitmap.height
    canales = bitmap.n_channels
    paso = bitmap.stride
    crudo = bytes(bitmap.buffer)
    invertido = bitmap.format in (FORMATO_BGR, FORMATO_BGRA, FORMATO_BGRX)

    filas = []
    for numero in range(alto):
        principio = numero * paso
        linea = crudo[principio:principio + ancho * canales]
        if canales == 3 and not invertido:
            filas.append(linea)
            continue
        salida = bytearray(ancho * 3)
        for columna in range(ancho):
            origen = columna * canales
            destino = columna * 3
            if invertido:
                salida[destino] = linea[origen + 2]
                salida[destino + 1] = linea[origen + 1]
                salida[destino + 2] = linea[origen]
            else:
                salida[destino:destino + 3] = linea[origen:origen + 3]
        filas.append(bytes(salida))
    return codificar(ancho, alto, filas)
