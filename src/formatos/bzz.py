# -*- coding: utf-8 -*-
"""BZZ: el compresor con el que van los textos de un DjVu.

Un DjVu de biblioteca casi siempre lleva dentro el texto que se reconocio al
digitalizarlo. Para quien no ve, **ese texto es el libro entero**: no hacen
falta las imagenes de las paginas. Sacarlo pasa por descomprimir unos trozos
del archivo, y todos van en BZZ.

BZZ son dos piezas encadenadas, y hay que deshacerlas en orden inverso:

1. Un **codificador aritmetico binario adaptativo** --el <<codificador ZP>>--,
   que convierte el chorro de bits en decisiones de si o no. Es adaptativo:
   cada decision se toma mirando una *variable de contexto* que va aprendiendo,
   sola, que es probable en ese sitio concreto.
2. Una **transformada de Burrows-Wheeler** con un ordenamiento por frecuencias
   parecido al <<mover al frente>> de bzip2, que es lo que agrupa las letras
   que se repiten para que la primera pieza tenga algo que aprovechar.

Esta escrito siguiendo al pie de la letra ``ZPCodec.cpp`` y ``BSByteStream.cpp``
de DjVuLibre, que es la unica descripcion completa que existe: el formato no
tiene norma publicada, y los resumenes que circulan se dejan justo los detalles
que deciden si funciona o no.

**Los tres detalles que lo hacen funcionar**, escritos aqui porque cada uno
costo un dia:

- El **atajo de la valla** (``valla``) no es una optimizacion que se pueda
  quitar. La ruta rapida devuelve el bit sin renormalizar y dejando ``a = z``;
  la ruta larga renormaliza. Si se toma siempre la larga, el codificador se
  desincroniza a los pocos bits. Por eso descodificar *sin* contexto
  --``decodificar_directo``, que nunca pasa por la valla-- salia bien y
  descodificar *con* contexto salia mal.
- La variable de contexto **es a la vez estado y prediccion**: su bit bajo es
  el simbolo mas probable y el numero entero indexa la tabla. Al adaptarse hay
  que **escribirla de vuelta** en el sitio del que salio, o lo aprendido se
  pierde y el modelo deja de coincidir con el del compresor.
- Toda la aritmetica es de **16 bits** (``a`` y ``codigo``), con un deposito de
  32 (``deposito``). En C eso lo hace el tipo; aqui hay que enmascarar a mano.
"""

from __future__ import annotations

#: Probabilidad del simbolo menos probable en cada estado, en 1/65536.
_P = (
    0x8000, 0x8000, 0x8000, 0x6bbd, 0x6bbd, 0x5d45, 0x5d45, 0x51b9,
    0x51b9, 0x4813, 0x4813, 0x3fd5, 0x3fd5, 0x38b1, 0x38b1, 0x3275,
    0x3275, 0x2cfd, 0x2cfd, 0x2825, 0x2825, 0x23ab, 0x23ab, 0x1f87,
    0x1f87, 0x1bbb, 0x1bbb, 0x1845, 0x1845, 0x1523, 0x1523, 0x1253,
    0x1253, 0x0fcf, 0x0fcf, 0x0d95, 0x0d95, 0x0b9d, 0x0b9d, 0x09e3,
    0x09e3, 0x0861, 0x0861, 0x0711, 0x0711, 0x05f1, 0x05f1, 0x04f9,
    0x04f9, 0x0425, 0x0425, 0x0371, 0x0371, 0x02d9, 0x02d9, 0x0259,
    0x0259, 0x01ed, 0x01ed, 0x0193, 0x0193, 0x0149, 0x0149, 0x010b,
    0x010b, 0x00d5, 0x00d5, 0x00a5, 0x00a5, 0x007b, 0x007b, 0x0057,
    0x0057, 0x003b, 0x003b, 0x0023, 0x0023, 0x0013, 0x0013, 0x0007,
    0x0007, 0x0001, 0x0001, 0x5695, 0x24ee, 0x8000, 0x0d30, 0x481a,
    0x0481, 0x3579, 0x017a, 0x24ef, 0x007b, 0x1978, 0x0028, 0x10ca,
    0x000d, 0x0b5d, 0x0034, 0x078a, 0x00a0, 0x050f, 0x0117, 0x0358,
    0x01ea, 0x0234, 0x0144, 0x0173, 0x0234, 0x00f5, 0x0353, 0x00a1,
    0x05c5, 0x011a, 0x03cf, 0x01aa, 0x0285, 0x0286, 0x01ab, 0x03d3,
    0x011a, 0x05c5, 0x00ba, 0x08ad, 0x007a, 0x0ccc, 0x01eb, 0x1302,
    0x02e6, 0x1b81, 0x045e, 0x24ef, 0x0690, 0x2865, 0x09de, 0x3987,
    0x0dc8, 0x2c99, 0x10ca, 0x3b5f, 0x0b5d, 0x5695, 0x078a, 0x8000,
    0x050f, 0x24ee, 0x0358, 0x0d30, 0x0234, 0x0481, 0x0173, 0x017a,
    0x00f5, 0x007b, 0x00a1, 0x0028, 0x011a, 0x000d, 0x01aa, 0x0034,
    0x0286, 0x00a0, 0x03d3, 0x0117, 0x05c5, 0x01ea, 0x08ad, 0x0144,
    0x0ccc, 0x0234, 0x1302, 0x0353, 0x1b81, 0x05c5, 0x24ef, 0x03cf,
    0x2b74, 0x0285, 0x201d, 0x01ab, 0x1715, 0x011a, 0x0fb7, 0x00ba,
    0x0a67, 0x01eb, 0x06e7, 0x02e6, 0x0496, 0x045e, 0x030d, 0x0690,
    0x0206, 0x09de, 0x0155, 0x0dc8, 0x00e1, 0x2b74, 0x0094, 0x201d,
    0x0188, 0x1715, 0x0252, 0x0fb7, 0x0383, 0x0a67, 0x0547, 0x06e7,
    0x07e2, 0x0496, 0x0bc0, 0x030d, 0x1178, 0x0206, 0x19da, 0x0155,
    0x24ef, 0x00e1, 0x320e, 0x0094, 0x432a, 0x0188, 0x447d, 0x0252,
    0x5ece, 0x0383, 0x8000, 0x0547, 0x481a, 0x07e2, 0x3579, 0x0bc0,
    0x24ef, 0x1178, 0x1978, 0x19da, 0x2865, 0x24ef, 0x3987, 0x320e,
    0x2c99, 0x432a, 0x3b5f, 0x447d, 0x5695, 0x5ece, 0x8000, 0x8000,
    0x5695, 0x481a, 0x481a,
)

#: Umbral de holgura por encima del cual el estado sube a otro mas confiado.
_M = (
    0x0000, 0x0000, 0x0000, 0x10a5, 0x10a5, 0x1f28, 0x1f28, 0x2bd3,
    0x2bd3, 0x36e3, 0x36e3, 0x408c, 0x408c, 0x48fd, 0x48fd, 0x505d,
    0x505d, 0x56d0, 0x56d0, 0x5c71, 0x5c71, 0x615b, 0x615b, 0x65a5,
    0x65a5, 0x6962, 0x6962, 0x6ca2, 0x6ca2, 0x6f74, 0x6f74, 0x71e6,
    0x71e6, 0x7404, 0x7404, 0x75d6, 0x75d6, 0x7768, 0x7768, 0x78c2,
    0x78c2, 0x79ea, 0x79ea, 0x7ae7, 0x7ae7, 0x7bbe, 0x7bbe, 0x7c75,
    0x7c75, 0x7d0f, 0x7d0f, 0x7d91, 0x7d91, 0x7dfe, 0x7dfe, 0x7e5a,
    0x7e5a, 0x7ea6, 0x7ea6, 0x7ee6, 0x7ee6, 0x7f1a, 0x7f1a, 0x7f45,
    0x7f45, 0x7f6b, 0x7f6b, 0x7f8d, 0x7f8d, 0x7faa, 0x7faa, 0x7fc3,
    0x7fc3, 0x7fd7, 0x7fd7, 0x7fe7, 0x7fe7, 0x7ff2, 0x7ff2, 0x7ffa,
    0x7ffa, 0x7fff, 0x7fff, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000,
    0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000,
    0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000,
    0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000,
    0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000,
    0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000,
    0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000,
    0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000,
    0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000,
    0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000,
    0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000,
    0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000,
    0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000,
    0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000,
    0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000,
    0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000,
    0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000,
    0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000,
    0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000,
    0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000,
    0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000,
    0x0000, 0x0000, 0x0000,
)

#: Estado al que se pasa al acertar (sale el simbolo mas probable).
_SUBE = (
    84, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13,
    14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25,
    26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37,
    38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49,
    50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61,
    62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73,
    74, 75, 76, 77, 78, 79, 80, 81, 82, 81, 82, 9,
    86, 5, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97,
    82, 99, 76, 101, 70, 103, 66, 105, 106, 107, 66, 109,
    60, 111, 56, 69, 114, 65, 116, 61, 118, 57, 120, 53,
    122, 49, 124, 43, 72, 39, 60, 33, 56, 29, 52, 23,
    48, 23, 42, 137, 38, 21, 140, 15, 142, 9, 144, 141,
    146, 147, 148, 149, 150, 151, 152, 153, 154, 155, 70, 157,
    66, 81, 62, 75, 58, 69, 54, 65, 50, 167, 44, 65,
    40, 59, 34, 55, 30, 175, 24, 177, 178, 179, 180, 181,
    182, 183, 184, 69, 186, 59, 188, 55, 190, 51, 192, 47,
    194, 41, 196, 37, 198, 199, 72, 201, 62, 203, 58, 205,
    54, 207, 50, 209, 46, 211, 40, 213, 36, 215, 30, 217,
    26, 219, 20, 71, 14, 61, 14, 57, 8, 53, 228, 49,
    230, 45, 232, 39, 234, 35, 138, 29, 24, 25, 240, 19,
    22, 13, 16, 13, 10, 7, 244, 249, 10, 89, 230,
)

#: Estado al que se pasa al fallar (sale el menos probable).
_BAJA = (
    145, 4, 3, 1, 2, 3, 4, 5, 6, 7, 8, 9,
    10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21,
    22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33,
    34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45,
    46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57,
    58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69,
    70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 85,
    226, 6, 176, 143, 138, 141, 112, 135, 104, 133, 100, 129,
    98, 127, 72, 125, 102, 123, 60, 121, 110, 119, 108, 117,
    54, 115, 48, 113, 134, 59, 132, 55, 130, 51, 128, 47,
    126, 41, 62, 37, 66, 31, 54, 25, 50, 131, 46, 17,
    40, 15, 136, 7, 32, 139, 172, 9, 170, 85, 168, 248,
    166, 247, 164, 197, 162, 95, 160, 173, 158, 165, 156, 161,
    60, 159, 56, 71, 52, 163, 48, 59, 42, 171, 38, 169,
    32, 53, 26, 47, 174, 193, 18, 191, 222, 189, 218, 187,
    216, 185, 214, 61, 212, 53, 210, 49, 208, 45, 206, 39,
    204, 195, 202, 31, 200, 243, 64, 239, 56, 237, 52, 235,
    48, 233, 44, 231, 38, 229, 34, 227, 28, 225, 22, 223,
    16, 221, 220, 63, 8, 55, 224, 51, 2, 47, 87, 43,
    246, 37, 244, 33, 238, 27, 236, 21, 16, 15, 8, 241,
    242, 7, 10, 245, 2, 1, 83, 250, 2, 143, 246,
)

#: Cuantos unos seguidos hay en la cabecera de cada byte. Sirve para saber de
#: golpe cuanto hay que renormalizar, en vez de ir bit a bit.
_UNOS = tuple(8 - len(bin(256 + b)[3:].lstrip("1")) for b in range(256))

#: Cuantos contextos usa la vuelta de Burrows-Wheeler. Sale de sumar los que
#: gasta el arbol de decision de mas abajo: 3 + 3 + 2 + 4 + 8 + 16 + 32 + 64 +
#: 128. Se redondea como en el original.
_CONTEXTOS = 300

#: Bloque mas grande que se admite, en bytes. Lo fija el formato, y sirve
#: ademas para que un archivo estropeado no pida gigabytes de memoria.
_MAXIMO_BLOQUE = 4096 * 1024

#: Cuantas frecuencias se llevan contadas para reordenar el alfabeto.
_FRECUENCIAS = 4

#: Contextos que distinguen <<lo mismo que la ultima vez>> de <<algo nuevo>>.
_IDS = 3


class Corrupto(Exception):
    """El chorro no es BZZ valido, o se acaba antes de tiempo."""


class CodificadorZP:
    """Descodificador aritmetico binario adaptativo del DjVu.

    Se construye sobre un bloque de bytes y va devolviendo bits. No sabe nada
    de lo que significan: quien lo usa decide, para cada bit, con que variable
    de contexto se pregunta, y de ahi sale toda la compresion.
    """

    __slots__ = ("datos", "posicion", "fin", "a", "codigo", "deposito",
                 "cuantos", "valla", "margen")

    def __init__(self, datos: bytes, posicion: int = 0, fin: int | None = None):
        self.datos = datos
        self.posicion = posicion
        # Donde acaba **este** chorro. Es imprescindible cuando el chorro es un
        # trozo de un archivo mayor: el codificador solo para al leer un tamano
        # de bloque cero, y si se le deja seguir, lo primero que encuentra
        # detras --el trozo siguiente-- lo toma por mas bloques y devuelve
        # basura o revienta. Sin esto, el indice de un DjVu se descomprime bien
        # y acto seguido se estropea con lo que tiene al lado.
        self.fin = len(datos) if fin is None else min(fin, len(datos))
        self.a = 0
        # Los dos primeros bytes son el codigo de arranque. Si el chorro se
        # acaba se sigue con 0xff: el compresor escribe menos bytes de los que
        # el descodificador lee, y eso es deliberado en el formato.
        self.codigo = (self._byte() << 8) | self._byte()
        self.deposito = 0
        self.cuantos = 0
        self.margen = 25
        self._rellenar()
        self.valla = 0x7fff if self.codigo >= 0x8000 else self.codigo

    def _byte(self) -> int:
        """El siguiente byte, o 0xff cuando ya no queda ninguno."""
        if self.posicion < self.fin:
            octeto = self.datos[self.posicion]
            self.posicion += 1
            return octeto
        return 0xff

    def _rellenar(self) -> None:
        """Deja al menos 25 bits en el deposito.

        Pasado el final se siguen dando bytes de relleno, pero solo unos
        cuantos: si se dieran sin limite, un archivo truncado se leeria como un
        chorro infinito de basura en lugar de dar error.
        """
        while self.cuantos <= 24:
            if self.posicion < self.fin:
                octeto = self.datos[self.posicion]
                self.posicion += 1
            else:
                octeto = 0xff
                self.margen -= 1
                if self.margen < 1:
                    raise Corrupto("el chorro BZZ se acaba antes de tiempo")
            self.deposito = ((self.deposito << 8) | octeto) & 0xffffffff
            self.cuantos += 8

    def decodificar(self, contextos: list, indice: int) -> int:
        """Un bit, preguntando por la variable ``contextos[indice]``.

        La variable se actualiza en su sitio: es lo que hace que el
        descodificador aprenda exactamente lo mismo que aprendio el compresor.
        """
        contexto = contextos[indice]
        z = self.a + _P[contexto]
        if z <= self.valla:
            # Ruta rapida: el intervalo cabe entero por debajo del codigo, asi
            # que sale el simbolo mas probable y no hay que renormalizar.
            self.a = z
            return contexto & 1
        return self._decodificar_largo(contextos, indice, z)

    def _decodificar_largo(self, contextos: list, indice: int, z: int) -> int:
        """La ruta larga: la que renormaliza y adapta el estado."""
        contexto = contextos[indice]
        bit = contexto & 1
        # Evita que el intervalo se de la vuelta.
        tope = 0x6000 + ((z + self.a) >> 2)
        if z > tope:
            z = tope
        if z > self.codigo:
            # Ha salido el simbolo menos probable: el estado desconfia.
            z = 0x10000 - z
            self.a = (self.a + z) & 0xffff
            self.codigo = (self.codigo + z) & 0xffff
            contextos[indice] = _BAJA[contexto]
            desplazamiento = _UNOS[self.a & 0xff] + 8 \
                if self.a >= 0xff00 else _UNOS[(self.a >> 8) & 0xff]
            self.cuantos -= desplazamiento
            self.a = (self.a << desplazamiento) & 0xffff
            self.codigo = ((self.codigo << desplazamiento)
                           | ((self.deposito >> self.cuantos)
                              & ((1 << desplazamiento) - 1))) & 0xffff
            if self.cuantos < 16:
                self._rellenar()
            self.valla = 0x7fff if self.codigo >= 0x8000 else self.codigo
            return bit ^ 1
        # Ha salido el mas probable: si ya hay holgura de sobra, el estado se
        # confia un paso mas.
        if self.a >= _M[contexto]:
            contextos[indice] = _SUBE[contexto]
        self.cuantos -= 1
        self.a = (z << 1) & 0xffff
        self.codigo = ((self.codigo << 1)
                       | ((self.deposito >> self.cuantos) & 1)) & 0xffff
        if self.cuantos < 16:
            self._rellenar()
        self.valla = 0x7fff if self.codigo >= 0x8000 else self.codigo
        return bit

    def decodificar_directo(self) -> int:
        """Un bit **sin** contexto, partiendo el intervalo por la mitad.

        Se usa para lo que no tiene estructura que aprender --el tamano de un
        bloque, un signo--, donde un modelo adaptativo no ganaria nada. Nunca
        pasa por la valla: aqui siempre toca renormalizar.
        """
        return self._sin_contexto(0x8000 + (self.a >> 1))

    def decodificar_iw(self) -> int:
        """Un bit sin contexto, pero partiendo por **tres octavos**.

        Es el que usa la compresion de imagenes en ondiculas para el signo de
        un coeficiente y para su bit de mantisa mas alto. El punto de corte no
        es la mitad porque esos bits no salen mitad y mitad: un coeficiente que
        acaba de aparecer es mas probable que se quede cerca del umbral que que
        lo doble.
        """
        return self._sin_contexto(0x8000 + ((self.a + self.a + self.a) >> 3))

    def _sin_contexto(self, z: int) -> int:
        """El cuerpo comun de los dos anteriores: decidir y renormalizar."""
        if z > self.codigo:
            z = 0x10000 - z
            self.a = (self.a + z) & 0xffff
            self.codigo = (self.codigo + z) & 0xffff
            desplazamiento = _UNOS[self.a & 0xff] + 8 \
                if self.a >= 0xff00 else _UNOS[(self.a >> 8) & 0xff]
            self.cuantos -= desplazamiento
            self.a = (self.a << desplazamiento) & 0xffff
            self.codigo = ((self.codigo << desplazamiento)
                           | ((self.deposito >> self.cuantos)
                              & ((1 << desplazamiento) - 1))) & 0xffff
            bit = 1
        else:
            self.a = (z << 1) & 0xffff
            self.cuantos -= 1
            self.codigo = ((self.codigo << 1)
                           | ((self.deposito >> self.cuantos) & 1)) & 0xffff
            bit = 0
        if self.cuantos < 16:
            self._rellenar()
        self.valla = 0x7fff if self.codigo >= 0x8000 else self.codigo
        return bit


def _numero_directo(zp: CodificadorZP, bits: int) -> int:
    """Un numero de ``bits`` bits, sin modelo: se usa para los tamanos."""
    n = 1
    tope = 1 << bits
    while n < tope:
        n = (n << 1) | zp.decodificar_directo()
    return n - tope


def _numero(zp: CodificadorZP, contextos: list, base: int, bits: int) -> int:
    """Un numero de ``bits`` bits con un arbol de contextos.

    Cada bit se pregunta con la variable que corresponde a los bits que ya han
    salido, asi que <<un dos detras de un uno>> y <<un dos detras de un tres>>
    aprenden por separado.
    """
    n = 1
    tope = 1 << bits
    while n < tope:
        n = (n << 1) | zp.decodificar(contextos, base + n - 1)
    return n - tope


def descomprimir(datos: bytes, posicion: int = 0, fin: int | None = None) -> bytes:
    """Descomprime un chorro BZZ entero y devuelve los bytes originales.

    ``fin`` acota el chorro cuando esta metido dentro de un archivo mayor, que
    es siempre el caso en un DjVu. Conviene darlo: sin el, el descompresor
    sigue leyendo lo que venga detras.
    """
    zp = CodificadorZP(datos, posicion, fin)
    contextos = [0] * _CONTEXTOS
    salida = bytearray()
    while True:
        bloque = _descomprimir_bloque(zp, contextos)
        if bloque is None:
            return bytes(salida)
        salida += bloque


def _descomprimir_bloque(zp: CodificadorZP, contextos: list):
    """Un bloque, o ``None`` cuando se llega al final del chorro."""
    tamano = _numero_directo(zp, 24)
    if not tamano:
        return None
    if tamano > _MAXIMO_BLOQUE:
        raise Corrupto("bloque BZZ imposible: %d bytes" % tamano)

    # Con cuanta prisa envejecen las frecuencias. Va en dos bits sueltos.
    prisa = 0
    if zp.decodificar_directo():
        prisa += 1
        if zp.decodificar_directo():
            prisa += 1

    datos = _rangos(zp, contextos, tamano, prisa)
    return _deshacer_bwt(datos)


def _rangos(zp: CodificadorZP, contextos: list, tamano: int, prisa: int):
    """Saca los bytes transformados, deshaciendo el <<mover al frente>>.

    El alfabeto se lleva ordenado por lo reciente que es cada letra, y lo que
    se codifica es la *posicion* en esa lista, no la letra. Como el texto
    transformado repite mucho, casi siempre sale la posicion 0 o la 1, que
    ocupan un bit. El orden no es un <<mover al frente>> puro: cada letra sube
    hasta donde le toque por frecuencia, que comprime algo mejor.
    """
    orden = bytearray(range(256))
    frecuencias = [0] * _FRECUENCIAS
    incremento = 4
    rango = 3
    marca = -1
    datos = bytearray(tamano)

    for i in range(tamano):
        # El arbol de decision: primero <<lo mismo que la ultima vez>>, luego
        # <<lo de justo detras>>, y solo si no, un numero cada vez mas ancho.
        id_contexto = rango if rango < _IDS - 1 else _IDS - 1
        if zp.decodificar(contextos, id_contexto):
            rango = 0
        elif zp.decodificar(contextos, _IDS + id_contexto):
            rango = 1
        else:
            base = _IDS + _IDS
            for anchura in range(1, 8):
                if zp.decodificar(contextos, base):
                    rango = (1 << anchura) + _numero(zp, contextos,
                                                     base + 1, anchura)
                    break
                base += 1 + ((1 << anchura) - 1)
            else:
                # La marca: el sitio por donde se corta la vuelta de la BWT.
                rango = 256
                datos[i] = 0
                marca = i
                continue
        datos[i] = orden[rango]

        # Recolocar la letra segun su frecuencia recien actualizada.
        incremento += incremento >> prisa
        if incremento > 0x10000000:
            incremento >>= 24
            for k in range(_FRECUENCIAS):
                frecuencias[k] >>= 24
        cuenta = incremento
        if rango < _FRECUENCIAS:
            cuenta += frecuencias[rango]
        k = rango
        while k >= _FRECUENCIAS:
            orden[k] = orden[k - 1]
            k -= 1
        while k > 0 and cuenta >= frecuencias[k - 1]:
            orden[k] = orden[k - 1]
            frecuencias[k] = frecuencias[k - 1]
            k -= 1
        orden[k] = datos[i]
        frecuencias[k] = cuenta

    if marca < 1 or marca >= tamano:
        raise Corrupto("al bloque BZZ le falta la marca de corte")
    return _Bloque(datos, tamano, marca)


class _Bloque:
    """Los bytes transformados de un bloque, con su marca de corte."""

    __slots__ = ("datos", "tamano", "marca")

    def __init__(self, datos, tamano, marca):
        self.datos = datos
        self.tamano = tamano
        self.marca = marca


def _deshacer_bwt(bloque: _Bloque) -> bytes:
    """Deshace la transformada de Burrows-Wheeler.

    La BWT ordena todas las rotaciones del texto y se queda con la ultima
    columna. Para volver atras basta con saber, de cada letra, cuantas iguales
    van delante: eso da una cadena de saltos que recorre el texto **del final
    al principio**, que es como se rellena aqui.
    """
    datos = bloque.datos
    tamano = bloque.tamano
    marca = bloque.marca
    posiciones = [0] * tamano
    cuenta = [0] * 256

    for i in range(marca):
        c = datos[i]
        posiciones[i] = (c << 24) | (cuenta[c] & 0xffffff)
        cuenta[c] += 1
    for i in range(marca + 1, tamano):
        c = datos[i]
        posiciones[i] = (c << 24) | (cuenta[c] & 0xffffff)
        cuenta[c] += 1

    ultimo = 1
    for i in range(256):
        cuantas = cuenta[i]
        cuenta[i] = ultimo
        ultimo += cuantas

    salida = bytearray(tamano - 1)
    i = 0
    ultimo = tamano - 1
    while ultimo > 0:
        n = posiciones[i]
        c = n >> 24
        ultimo -= 1
        salida[ultimo] = c
        i = cuenta[c] + (n & 0xffffff)
    if i != marca:
        raise Corrupto("la vuelta de la transformada no cierra")
    return bytes(salida)
