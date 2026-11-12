# -*- coding: utf-8 -*-
"""IW44: las capas en color de un DjVu.

Una página de DjVu va en **tres capas**. La máscara en blanco y negro —el texto
y los dibujos de línea— se comprime con JB2 y la descomprime :mod:`formatos.jb2`.
Las otras dos, el **fondo** (``BG44``) y el **primer plano** (``FG44``), llevan
el color: el papel, las fotografías, las láminas. Van comprimidas en ondículas,
y eso es lo que descomprime este módulo.

**Para qué hace falta.** Para el texto no hace falta: la máscara ya lo trae, y
además llega más limpia. Hace falta para lo que **no** está en la máscara: una
lámina fotográfica, un mapa en color, una reproducción de un cuadro. Una página
así no tiene ni una letra en la máscara, y hasta ahora no se podía ni ver ni
mandar a describir. En un libro de texto es una página de cada cincuenta, pero
en un atlas o en un catálogo de museo son todas.

**Cómo comprime, en una idea.** No guarda píxeles: guarda la imagen
descompuesta en **escalas**. Primero una versión diminuta, y después, para cada
paso de ampliación, solo el detalle que hay que añadir para llegar al siguiente
tamaño. En una fotografía la mayoría de esos detalles son casi cero, y ahí está
el ahorro. Encima va un refinamiento por **pasadas**: la primera deja la imagen
reconocible y cada una siguiente le añade precisión, así que un archivo cortado
por la mitad da una imagen borrosa y no media imagen. Por eso una página trae
cuatro o cinco trozos ``BG44`` seguidos en vez de uno.

Va sobre el mismo codificador ZP de ``bzz.py`` y ``jb2.py``. Es el tercer
formato que se apoya en él, y es la razón de que este módulo quepa en lo que
cabe: lo difícil estaba escrito.

**Los cuatro sitios donde es fácil equivocarse:**

- La imagen se guarda en **bloques de 32 por 32** y dentro de cada bloque los
  coeficientes van en **zigzag**, no por filas. La tabla del zigzag no se copia:
  se genera entrelazando los bits del índice, que es de donde sale.
- Los coeficientes se van **afinando pasada a pasada**, y el umbral se parte por
  la mitad al acabar cada banda. Quedarse con el primer valor da una imagen que
  parece bien y está a la mitad de contraste.
- Los cubos de coeficientes **se reservan según hacen falta**. Que un cubo no
  exista no es lo mismo que que valga cero: cambia el estado con el que se
  pregunta al codificador, y confundirlos desincroniza.
- El color va en **YCbCr con la transformada de Pigeon**, no con la del JPEG.
  Se parecen lo justo para que una foto salga reconocible y con los colores
  cambiados, que es la peor manera de equivocarse.

Escrito siguiendo ``IW44Image.cpp`` y ``IW44Image.h`` de DjVuLibre, guardados en
``adjuntos/Estudio/djvulibre``. El formato no tiene norma publicada.
"""
from __future__ import annotations

import struct

from .bzz import CodificadorZP, Corrupto

#: Cuánto se cuantifica cada una de las dieciséis subbandas.  Son los números de
#: DjVuLibre y no se pueden tocar: el compresor usa los mismos para decidir qué
#: bit toca en cada pasada.
_CUANTIF = (
    0x004000,
    0x008000, 0x008000, 0x010000,
    0x010000, 0x010000, 0x020000,
    0x020000, 0x020000, 0x040000,
    0x040000, 0x040000, 0x080000,
    0x040000, 0x040000, 0x080000,
)

#: Qué cubos ocupa cada banda: dónde empieza y cuántos son.  La banda cero lleva
#: la versión diminuta de la imagen entera; las demás, el detalle de cada
#: escala, y por eso van creciendo de cuatro en cuatro y de dieciséis en
#: dieciséis.
_BANDAS = ((0, 1), (1, 1), (2, 1), (3, 1), (4, 4), (8, 4), (12, 4),
           (16, 16), (32, 16), (48, 16))

#: Estado de un coeficiente mientras se descodifica.  Se combinan con «o», así
#: que son banderas y no valores.
_CERO = 1        # en esta pasada no puede aparecer
_ACTIVO = 2      # ya tiene valor y toca afinarlo
_NUEVO = 4       # aparece justo ahora
_DESCONOCIDO = 8  # podría aparecer

#: Cuánto se escala antes de descomponer, y el redondeo que le corresponde.
_ESCALA = 6
_REDONDEO = 1 << (_ESCALA - 1)

#: Tope de píxeles de una capa.  Un archivo corrupto puede declarar una imagen
#: de treinta mil por treinta mil y dejar el programa sin memoria antes de que
#: nadie pueda cancelar nada.
_MAXIMO = 40 * 1024 * 1024


def _zigzag() -> tuple:
    """Dónde cae en el bloque de 32×32 el coeficiente número ``n``.

    No es una tabla que haya que copiar: es **entrelazar los bits**.  Los bits
    pares del índice, leídos del revés, dan la columna; los impares, la fila.
    Así los coeficientes de las escalas gruesas —los que más pesan— quedan
    juntos al principio, que es lo que permite cortar el archivo por donde sea.
    """
    salida = []
    for numero in range(1024):
        n, x, y = numero, 0, 0
        for _ in range(5):
            x = (x << 1) | (n & 1)
            n >>= 1
            y = (y << 1) | (n & 1)
            n >>= 1
        salida.append(y * 32 + x)
    return tuple(salida)


ZIGZAG = _zigzag()


class Mapa:
    """Los coeficientes de una capa, en bloques de 32×32.

    Cada bloque son 64 **cubos** de 16 coeficientes.  Un cubo que no se ha
    tocado nunca no se reserva: en una fotografía la mayoría son cero enteros, y
    guardarlos costaría más memoria que la imagen.
    """

    __slots__ = ("ancho", "alto", "ancho_bloques", "alto_bloques", "cuantos",
                 "bloques")

    def __init__(self, ancho: int, alto: int) -> None:
        if ancho <= 0 or alto <= 0 or ancho * alto > _MAXIMO:
            raise Corrupto("tamaño de imagen imposible: %dx%d" % (ancho, alto))
        self.ancho = ancho
        self.alto = alto
        self.ancho_bloques = (ancho + 31) & ~31
        self.alto_bloques = (alto + 31) & ~31
        self.cuantos = (self.ancho_bloques * self.alto_bloques) // 1024
        self.bloques = [[None] * 64 for _ in range(self.cuantos)]

    def coeficientes(self):
        """Los coeficientes puestos ya en su rejilla, deshecho el zigzag.

        Devuelve una lista de filas de ``ancho_bloques`` enteros, de arriba
        abajo, que es lo que espera la transformada inversa.
        """
        anchura = self.ancho_bloques
        rejilla = [[0] * anchura for _ in range(self.alto_bloques)]
        por_fila = anchura // 32
        for numero, bloque in enumerate(self.bloques):
            base_y = (numero // por_fila) * 32
            base_x = (numero % por_fila) * 32
            n = 0
            for cubo in bloque:
                if cubo is None:
                    n += 16
                    continue
                for valor in cubo:
                    if valor:
                        sitio = ZIGZAG[n]
                        rejilla[base_y + (sitio >> 5)][base_x + (sitio & 31)] = valor
                    n += 1
        return rejilla


class _Descodificador:
    """Una capa que se va afinando trozo a trozo.

    Vive entre trozos a propósito: una página trae cuatro o cinco ``BG44``
    seguidos y cada uno continúa donde lo dejó el anterior, con los mismos
    umbrales y en la misma banda.  Empezar de cero en cada trozo daría una
    imagen plana.
    """

    __slots__ = ("mapa", "banda", "pasada", "umbral_alto", "umbral_bajo",
                 "estado", "estado_cubo", "ctx_inicio", "ctx_cubo",
                 "ctx_mantisa", "ctx_raiz")

    def __init__(self, mapa: Mapa) -> None:
        self.mapa = mapa
        self.banda = 0
        self.pasada = 1
        # Los umbrales de la banda cero son uno por coeficiente; los de las
        # demás, uno por banda.  Salen de repartir la tabla de cuantificación
        # como manda DjVuLibre.
        self.umbral_bajo = [_CUANTIF[0], _CUANTIF[1], _CUANTIF[2], _CUANTIF[3],
                            _CUANTIF[4], _CUANTIF[4], _CUANTIF[4], _CUANTIF[4],
                            _CUANTIF[5], _CUANTIF[5], _CUANTIF[5], _CUANTIF[5],
                            _CUANTIF[6], _CUANTIF[6], _CUANTIF[6], _CUANTIF[6]]
        self.umbral_alto = [0] + list(_CUANTIF[7:16])
        self.estado = [0] * 256
        self.estado_cubo = [0] * 16
        self.ctx_inicio = [0] * 16
        self.ctx_cubo = [0] * 80
        self.ctx_mantisa = [0]
        self.ctx_raiz = [0]

    # -- el bucle de pasadas -------------------------------------------------

    def pasada_vacia(self) -> bool:
        """Si en esta banda y con estos umbrales no puede aparecer nada.

        Cuando el umbral se ha partido tantas veces que ya no cabe, la pasada no
        lleva ni un bit y hay que saltarla **sin leer nada**: leer un bit «por
        si acaso» desincroniza el descodificador.
        """
        if self.banda:
            umbral = self.umbral_alto[self.banda]
            return not (0 < umbral < 0x8000)
        vacia = True
        for i in range(16):
            umbral = self.umbral_bajo[i]
            if 0 < umbral < 0x8000:
                self.estado[i] = _DESCONOCIDO
                vacia = False
            else:
                self.estado[i] = _CERO
        return vacia

    def una_pasada(self, zp: CodificadorZP) -> bool:
        """Lee una pasada entera. Devuelve si queda algo por leer."""
        if self.pasada < 0:
            return False
        if not self.pasada_vacia():
            primero, cuantos = _BANDAS[self.banda]
            for bloque in self.mapa.bloques:
                self._cubos(zp, bloque, primero, cuantos)
        return self._siguiente()

    def _siguiente(self) -> bool:
        """Parte los umbrales por la mitad y pasa a la banda siguiente."""
        self.umbral_alto[self.banda] >>= 1
        if self.banda == 0:
            for i in range(16):
                self.umbral_bajo[i] >>= 1
        self.banda += 1
        if self.banda >= len(_BANDAS):
            self.banda = 0
            self.pasada += 1
            if self.umbral_alto[len(_BANDAS) - 1] == 0:
                # Todos los umbrales a cero: no queda precisión que añadir.
                self.pasada = -1
                return False
        return True

    # -- un grupo de cubos ---------------------------------------------------

    def _preparar(self, bloque, primero: int, cuantos: int) -> int:
        """Qué se sabe ya de cada coeficiente antes de preguntar nada.

        Un cubo que **no existe** no vale cero: vale «desconocido», porque
        cualquiera de sus dieciséis puede aparecer en esta pasada. Uno que
        existe se mira coeficiente a coeficiente. De esa diferencia salen los
        contextos, así que confundirlas rompe el flujo entero.
        """
        estado = self.estado
        general = 0
        if primero:
            for cual in range(cuantos):
                base = cual * 16
                cubo = bloque[primero + cual]
                if cubo is None:
                    del_cubo = _DESCONOCIDO
                else:
                    del_cubo = 0
                    for i in range(16):
                        uno = _ACTIVO if cubo[i] else _DESCONOCIDO
                        estado[base + i] = uno
                        del_cubo |= uno
                self.estado_cubo[cual] = del_cubo
                general |= del_cubo
        else:
            cubo = bloque[0]
            if cubo is None:
                general = _DESCONOCIDO
            else:
                for i in range(16):
                    uno = estado[i]
                    if uno != _CERO:
                        uno = _ACTIVO if cubo[i] else _DESCONOCIDO
                    estado[i] = uno
                    general |= uno
            self.estado_cubo[0] = general
        return general

    def _cubos(self, zp, bloque, primero: int, cuantos: int) -> None:
        """El corazón: lee un grupo de cubos de un bloque."""
        estado = self.estado
        estado_cubo = self.estado_cubo
        general = self._preparar(bloque, primero, cuantos)

        # ¿Hay algo nuevo en todo el grupo? Con pocos cubos no se pregunta: sale
        # más caro el bit que lo que ahorraría.
        if cuantos < 16 or (general & _ACTIVO):
            general |= _NUEVO
        elif general & _DESCONOCIDO:
            if zp.decodificar(self.ctx_raiz, 0):
                general |= _NUEVO

        banda = self.banda
        if general & _NUEVO:
            for cual in range(cuantos):
                if not (estado_cubo[cual] & _DESCONOCIDO):
                    continue
                # El contexto sale de mirar el cubo de la escala de arriba: si
                # allí había detalle, es probable que aquí también.
                ctx = 0
                if banda > 0:
                    k = (primero + cual) << 2
                    arriba = bloque[k >> 4]
                    if arriba is not None:
                        k &= 0xf
                        if arriba[k]:
                            ctx += 1
                        if arriba[k + 1]:
                            ctx += 1
                        if arriba[k + 2]:
                            ctx += 1
                        if ctx < 3 and arriba[k + 3]:
                            ctx += 1
                if general & _ACTIVO:
                    ctx |= 4
                if zp.decodificar(self.ctx_cubo, banda * 8 + ctx):
                    estado_cubo[cual] |= _NUEVO

        # -- los coeficientes que aparecen ahora, con su signo ---------------
        if general & _NUEVO:
            umbral = self.umbral_alto[banda]
            for cual in range(cuantos):
                if not (estado_cubo[cual] & _NUEVO):
                    continue
                base = cual * 16
                cubo = bloque[primero + cual]
                if cubo is None:
                    cubo = bloque[primero + cual] = [0] * 16
                    if primero == 0:
                        for i in range(16):
                            if estado[i] != _CERO:
                                estado[i] = _DESCONOCIDO
                    else:
                        for i in range(base, base + 16):
                            estado[i] = _DESCONOCIDO
                # Cuántos quedan por decidir: cuantos menos, más probable es que
                # el siguiente sí sea, y eso es lo que dice el contexto.
                quedan = 0
                for i in range(base, base + 16):
                    if estado[i] & _DESCONOCIDO:
                        quedan += 1
                for i in range(16):
                    if not (estado[base + i] & _DESCONOCIDO):
                        continue
                    if banda == 0:
                        umbral = self.umbral_bajo[i]
                    ctx = 7 if quedan >= 7 else quedan
                    if estado_cubo[cual] & _ACTIVO:
                        ctx |= 8
                    if zp.decodificar(self.ctx_inicio, ctx):
                        estado[base + i] |= _NUEVO
                        medio = umbral >> 1
                        valor = umbral + medio - (medio >> 2)
                        cubo[i] = -valor if zp.decodificar_iw() else valor
                        quedan = 0
                    elif quedan > 0:
                        quedan -= 1

        # -- los que ya estaban, que se afinan -------------------------------
        if general & _ACTIVO:
            umbral = self.umbral_alto[banda]
            for cual in range(cuantos):
                if not (estado_cubo[cual] & _ACTIVO):
                    continue
                base = cual * 16
                cubo = bloque[primero + cual]
                for i in range(16):
                    if not (estado[base + i] & _ACTIVO):
                        continue
                    valor = cubo[i]
                    magnitud = -valor if valor < 0 else valor
                    if banda == 0:
                        umbral = self.umbral_bajo[i]
                    if magnitud <= 3 * umbral:
                        magnitud += umbral >> 2
                        if zp.decodificar(self.ctx_mantisa, 0):
                            magnitud += umbral >> 1
                        else:
                            magnitud += (umbral >> 1) - umbral
                    elif zp.decodificar_iw():
                        magnitud += umbral >> 1
                    else:
                        magnitud += (umbral >> 1) - umbral
                    cubo[i] = magnitud if valor > 0 else -magnitud


# ---------------------------------------------------------------------------
# La transformada inversa
# ---------------------------------------------------------------------------


def _vertical(rejilla, ancho: int, alto: int, salto: int) -> None:
    """Deshace la ondícula por columnas, a la escala ``salto``.

    Son dos medias vueltas: primero se le quita a cada fila impar lo que se le
    había predicho de sus vecinas, y después se le suma a cada fila par la
    interpolación de las impares ya corregidas. En ese orden y no al revés: es
    lo que hace que la operación sea exactamente reversible.
    """
    filas_utiles = ((alto - 1) // salto) + 1
    y = 0
    while y - 3 < filas_utiles:
        # 1 - Quitar la predicción de las filas impares.
        if y < filas_utiles:
            fila = rejilla[y * salto]
            menos1 = rejilla[(y - 1) * salto] if y >= 1 else None
            mas1 = rejilla[(y + 1) * salto] if y + 1 < filas_utiles else None
            menos3 = rejilla[(y - 3) * salto] if y >= 3 else None
            mas3 = rejilla[(y + 3) * salto] if y + 3 < filas_utiles else None
            for x in range(0, ancho, salto):
                a = (menos1[x] if menos1 is not None else 0) + \
                    (mas1[x] if mas1 is not None else 0)
                b = (menos3[x] if menos3 is not None else 0) + \
                    (mas3[x] if mas3 is not None else 0)
                fila[x] -= ((a << 3) + a - b + 16) >> 5
        # 2 - Sumar la interpolación a las filas pares, tres filas más atrás.
        destino = y - 3
        if destino >= 0:
            fila = rejilla[destino * salto]
            if y >= 6 and y < filas_utiles:
                a1 = rejilla[(destino - 1) * salto]
                a2 = rejilla[(destino + 1) * salto]
                b1 = rejilla[(destino - 3) * salto]
                b2 = rejilla[(destino + 3) * salto]
                for x in range(0, ancho, salto):
                    a = a1[x] + a2[x]
                    b = b1[x] + b2[x]
                    fila[x] += ((a << 3) + a - b + 8) >> 4
            else:
                anterior = rejilla[(destino - 1) * salto]
                otra = rejilla[((destino + 1) if destino + 1 < filas_utiles
                                else (destino - 1)) * salto]
                for x in range(0, ancho, salto):
                    fila[x] += (anterior[x] + otra[x] + 1) >> 1
        y += 2


def _horizontal(rejilla, ancho: int, alto: int, salto: int) -> None:
    """Lo mismo por filas.

    Va escrito de otra manera —arrastrando cuatro valores en vez de mirar atrás
    en la lista— porque dentro de una fila los vecinos están seguidos, y así se
    recorre una sola vez lo que si no habría que recorrer cuatro.
    """
    s2 = salto + salto
    s3 = salto * 3
    for y in range(0, alto, salto):
        fila = rejilla[y]
        a0 = a1 = a2 = a3 = 0
        b0 = b1 = b2 = b3 = 0
        x = 0
        if x < ancho:
            a2 = fila[x + salto] if x + salto < ancho else 0
            a3 = fila[x + s3] if x + s3 < ancho else 0
            b2 = b3 = fila[x] - ((((a1 + a2) << 3) + (a1 + a2) - a0 - a3 + 16) >> 5)
            fila[x] = b3
            x += s2
        if x < ancho:
            a0, a1, a2 = a1, a2, a3
            a3 = fila[x + s3] if x + s3 < ancho else 0
            b3 = fila[x] - ((((a1 + a2) << 3) + (a1 + a2) - a0 - a3 + 16) >> 5)
            fila[x] = b3
            x += s2
        if x < ancho:
            b1, b2 = b2, b3
            a0, a1, a2 = a1, a2, a3
            a3 = fila[x + s3] if x + s3 < ancho else 0
            b3 = fila[x] - ((((a1 + a2) << 3) + (a1 + a2) - a0 - a3 + 16) >> 5)
            fila[x] = b3
            fila[x - s3] += (b1 + b2 + 1) >> 1
            x += s2
        while x + s3 < ancho:
            a0, a1, a2, a3 = a1, a2, a3, fila[x + s3]
            b0, b1, b2 = b1, b2, b3
            b3 = fila[x] - ((((a1 + a2) << 3) + (a1 + a2) - a0 - a3 + 16) >> 5)
            fila[x] = b3
            fila[x - s3] += (((b1 + b2) << 3) + (b1 + b2) - b0 - b3 + 8) >> 4
            x += s2
        while x < ancho:
            a0, a1, a2, a3 = a1, a2, a3, 0
            b0, b1, b2 = b1, b2, b3
            b3 = fila[x] - ((((a1 + a2) << 3) + (a1 + a2) - a0 - a3 + 16) >> 5)
            fila[x] = b3
            fila[x - s3] += (((b1 + b2) << 3) + (b1 + b2) - b0 - b3 + 8) >> 4
            x += s2
        while x - s3 < ancho:
            b0, b1, b2 = b1, b2, b3
            if x - s3 >= 0:
                fila[x - s3] += (b1 + b2 + 1) >> 1
            x += s2


def reconstruir(mapa: Mapa) -> list:
    """De coeficientes a píxeles: una fila de enteros de -128 a 127 por línea.

    Se va de la escala más gruesa a la más fina, y en cada una primero por
    columnas y luego por filas. Cada vuelta duplica el tamaño de lo que ya está
    reconstruido, así que la imagen aparece entera desde la primera y solo gana
    definición.
    """
    rejilla = mapa.coeficientes()
    anchura = mapa.ancho_bloques
    altura = mapa.alto_bloques
    salto = 16
    while salto >= 1:
        _vertical(rejilla, anchura, altura, salto)
        _horizontal(rejilla, anchura, altura, salto)
        salto >>= 1
    salida = []
    for y in range(mapa.alto):
        fila = rejilla[y]
        linea = []
        for x in range(mapa.ancho):
            valor = (fila[x] + _REDONDEO) >> _ESCALA
            linea.append(-128 if valor < -128 else (127 if valor > 127 else valor))
        salida.append(linea)
    return salida


# ---------------------------------------------------------------------------
# Los trozos del archivo
# ---------------------------------------------------------------------------


class Capa:
    """Una capa de color, tal como se va leyendo de sus trozos.

    Guarda los descodificadores entre trozos porque cada uno **continúa** el
    anterior: se abre con el primero, se le van dando los demás, y cuando ya no
    hay más se pide la imagen.
    """

    __slots__ = ("ancho", "alto", "gris", "retardo", "y", "cb", "cr",
                 "_y", "_cb", "_cr", "_pasadas", "_serie")

    def __init__(self) -> None:
        self.ancho = 0
        self.alto = 0
        self.gris = True
        self.retardo = 0
        self.y = self.cb = self.cr = None
        self._y = self._cb = self._cr = None
        self._pasadas = 0
        self._serie = 0

    def trozo(self, datos: bytes, inicio: int, fin: int) -> None:
        """Añade un trozo ``BG44`` o ``FG44``, en el orden en que vienen."""
        posicion = inicio
        if fin - posicion < 2:
            raise Corrupto("trozo de imagen truncado")
        serie, pasadas = datos[posicion], datos[posicion + 1]
        posicion += 2
        if serie != self._serie:
            raise Corrupto("los trozos de la imagen vienen desordenados")
        if self._serie == 0:
            if fin - posicion < 6:
                raise Corrupto("cabecera de imagen truncada")
            mayor, menor = datos[posicion], datos[posicion + 1]
            posicion += 2
            if (mayor & 0x7f) != 1:
                raise Corrupto("versión de imagen incompatible: %d" % (mayor & 0x7f))
            ancho, alto = struct.unpack(">HH", datos[posicion:posicion + 4])
            posicion += 4
            retardo = 0
            if menor >= 2:
                if fin - posicion < 1:
                    raise Corrupto("cabecera de imagen truncada")
                retardo = datos[posicion] & 0x7f
                posicion += 1
            if mayor & 0x80:
                # El bit alto dice que la imagen es en blanco y negro: no trae
                # las dos capas de color y no hay que reservarlas.
                retardo = -1
            self.ancho, self.alto = ancho, alto
            self.retardo = retardo
            self.gris = retardo < 0
            self.y = Mapa(ancho, alto)
            self._y = _Descodificador(self.y)
            if not self.gris:
                self.cb = Mapa(ancho, alto)
                self.cr = Mapa(ancho, alto)
                self._cb = _Descodificador(self.cb)
                self._cr = _Descodificador(self.cr)
        if self._y is None:
            raise Corrupto("la imagen no empieza por su cabecera")

        zp = CodificadorZP(datos, posicion, fin)
        tope = self._pasadas + pasadas
        sigue = True
        while sigue and self._pasadas < tope:
            sigue = self._y.una_pasada(zp)
            if self._cb is not None and self.retardo <= self._pasadas:
                sigue = self._cb.una_pasada(zp) or sigue
                sigue = self._cr.una_pasada(zp) or sigue
            self._pasadas += 1
        self._serie += 1

    def imagen(self) -> tuple:
        """La capa ya reconstruida: ``(ancho, alto, filas en RGB)``.

        Cada fila son ``ancho * 3`` bytes, que es justo lo que quiere el
        codificador de PNG.
        """
        if self.y is None:
            raise Corrupto("la imagen no trae ningún trozo")
        luz = reconstruir(self.y)
        ancho, alto = self.ancho, self.alto
        if self.gris or self.cb is None:
            # En blanco y negro el valor va **invertido**: el formato guarda
            # cuánta tinta hay, no cuánta luz, así que el cero es el papel.
            # Sumarle 128 en vez de restárselo a 127 da la imagen en negativo,
            # que se nota enseguida en una foto y no se nota nada en una página
            # de texto casi vacía.
            filas = []
            for y in range(alto):
                linea = bytearray(ancho * 3)
                origen = luz[y]
                for x in range(ancho):
                    gris = 127 - origen[x]
                    linea[x * 3] = linea[x * 3 + 1] = linea[x * 3 + 2] = gris
                filas.append(bytes(linea))
            return ancho, alto, filas
        azul = reconstruir(self.cb)
        rojo = reconstruir(self.cr)
        filas = []
        for y in range(alto):
            linea = bytearray(ancho * 3)
            fy, fb, fr = luz[y], azul[y], rojo[y]
            for x in range(ancho):
                # La transformada de Pigeon, que no es la del JPEG: se parecen
                # lo justo para que una foto salga reconocible y con los colores
                # cambiados.
                b, r = fb[x], fr[x]
                t2 = r + (r >> 1)
                t3 = fy[x] + 128 - (b >> 2)
                rr = fy[x] + 128 + t2
                gg = t3 - (t2 >> 1)
                bb = t3 + (b << 1)
                linea[x * 3] = 0 if rr < 0 else (255 if rr > 255 else rr)
                linea[x * 3 + 1] = 0 if gg < 0 else (255 if gg > 255 else gg)
                linea[x * 3 + 2] = 0 if bb < 0 else (255 if bb > 255 else bb)
            filas.append(bytes(linea))
        return ancho, alto, filas


def a_png(capa: Capa) -> bytes:
    """La capa como PNG en color."""
    from . import png

    ancho, alto, filas = capa.imagen()
    return png.codificar(ancho, alto, filas)
