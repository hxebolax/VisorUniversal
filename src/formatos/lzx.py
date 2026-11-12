# -*- coding: utf-8 -*-
"""LZX: el algoritmo con el que están comprimidos los archivos de ayuda.

Un ``.chm`` guarda su contenido comprimido con LZX, que es un algoritmo de
Microsoft de los años noventa —el mismo de los ``.cab`` y de las imágenes de
instalación de Windows— y del que Python no trae nada.  Sin esto, un archivo de
ayuda no se puede abrir: no es que se lea mal, es que no hay forma de sacar un
solo byte.

Se escribe aquí, entero y en Python, porque las alternativas eran peores:
depender de que el usuario tenga instalado 7-Zip, o traerse una biblioteca en C
que habría que compilar para cada versión de Python.  Son cuatrocientas líneas
que no cambian nunca —el formato está cerrado desde 1997— y a cambio los
archivos de ayuda se abren en cualquier equipo.

Cómo funciona LZX, en corto
---------------------------

Es un LZ77 con codificación Huffman por encima, como *deflate*, pero con tres
cosas propias que hay que respetar o no sale nada:

**Los árboles se transmiten como diferencias.**  No se manda la tabla de
longitudes de cada árbol, se manda **cuánto cambia respecto al bloque
anterior**, y esas diferencias van a su vez comprimidas con otro árbol Huffman
—el *pretree*— que sí viene entero.  Por eso hay que conservar las longitudes de
un bloque al siguiente.

**Las distancias recientes se recuerdan.**  Hay tres huecos (R0, R1, R2) con las
últimas distancias usadas; los tres primeros valores de posición no son
distancias, son «repite la de antes».  Es lo que hace a LZX bueno con texto
repetitivo, y es la parte donde un fallo no se nota hasta mil bytes después.

**Las llamadas a función se traducen.**  Como LZX se inventó para comprimir
programas, convierte las direcciones de las llamadas (el byte ``E8`` del
procesador) en direcciones absolutas antes de comprimir, y hay que deshacerlo
al descomprimir.  En un archivo de ayuda, que es HTML, eso casi nunca se activa;
pero cuando el HTML lleva por casualidad un byte ``E8``, no deshacerlo cambia
cuatro bytes del texto.

Los bits se leen de una forma poco corriente: **palabras de 16 bits en orden de
Intel, y dentro de cada palabra los bits de más peso primero**.  Escrito de otra
manera, no sale nada.
"""

from __future__ import annotations

from nucleo.idioma import _
from nucleo.registro import obtener_registro

log = obtener_registro(__name__)

#: Longitudes mínimas de coincidencia y número de símbolos de cada árbol.
COINCIDENCIA_MINIMA = 2
NUM_CARACTERES = 256
NUM_SECUNDARIAS = 249
NUM_ALINEADOS = 8
NUM_PREARBOL = 20

#: Cuántos bits ocupa como mucho un código de cada árbol.  Es lo que fija el
#: tamaño de las tablas de descodificación.
BITS_MAXIMOS = 16

#: Cuántas posiciones «recientes» se recuerdan.
HUECOS = 3

#: Tamaño del trozo en que LZX reparte su salida: 32 KB.  Es la unidad de los
#: puntos de reinicio y la de la traducción de las llamadas.
TROZO = 0x8000

#: Ranuras de posición según el tamaño de la ventana.  La tabla está en la
#: especificación de LZX y no se deduce de nada: hay que llevarla escrita.
_RANURAS = {
    15: 30, 16: 32, 17: 34, 18: 36, 19: 38, 20: 42, 21: 50,
}

#: Desplazamiento base de cada ranura de posición.
_BASES: list[int] = []
#: Bits extra que lleva cada ranura.
_EXTRAS: list[int] = []


def _preparar_tablas() -> None:
    """Calcula las bases y los bits extra de cada ranura de posición."""
    global _BASES, _EXTRAS
    extras = [0, 0, 0, 0]
    for numero in range(4, 50):
        extras.append(min(17, (numero // 2) - 1))
    _EXTRAS = extras
    bases = [0]
    for numero in range(1, 51):
        bases.append(bases[numero - 1] + (1 << extras[numero - 1]))
    _BASES = bases


_preparar_tablas()

#: Longitudes de las coincidencias: los primeros siete símbolos secundarios no
#: llevan bits extra.
_LONGITUD_BASE = COINCIDENCIA_MINIMA


class ErrorLZX(Exception):
    """El flujo comprimido no se puede descomprimir.

    Casi siempre significa que el archivo está dañado o cortado.  Se distingue
    de un fallo del programa a propósito: quien lo reciba tiene que decírselo al
    usuario como un problema del archivo.
    """


class _Bits:
    """Lee bits de un flujo LZX: palabras de 16 bits, bits altos primero."""

    __slots__ = ("datos", "posicion", "deposito", "cuantos")

    def __init__(self, datos: bytes) -> None:
        self.datos = datos
        self.posicion = 0
        self.deposito = 0
        self.cuantos = 0

    def _rellenar(self, cuantos: int) -> None:
        """Se asegura de tener al menos ``cuantos`` bits en el depósito."""
        while self.cuantos < cuantos:
            if self.posicion + 1 < len(self.datos):
                palabra = (self.datos[self.posicion]
                           | (self.datos[self.posicion + 1] << 8))
                self.posicion += 2
            elif self.posicion < len(self.datos):
                palabra = self.datos[self.posicion]
                self.posicion += 1
            else:
                # Se acabó el flujo: se rellena con ceros.  Un bloque puede
                # pedir unos bits de más al final y no es un error.
                palabra = 0
            self.deposito = ((self.deposito << 16) | palabra) & 0xFFFFFFFFFFFF
            self.cuantos += 16

    def leer(self, cuantos: int) -> int:
        """Lee un número de esa cantidad de bits."""
        if cuantos == 0:
            return 0
        self._rellenar(cuantos)
        self.cuantos -= cuantos
        valor = (self.deposito >> self.cuantos) & ((1 << cuantos) - 1)
        return valor

    def mirar(self, cuantos: int) -> int:
        """Mira los siguientes bits sin consumirlos."""
        self._rellenar(cuantos)
        return (self.deposito >> (self.cuantos - cuantos)) & ((1 << cuantos) - 1)

    def saltar(self, cuantos: int) -> None:
        """Consume bits ya mirados."""
        self.cuantos -= cuantos

    def alinear_palabra(self) -> None:
        """Tira los bits sueltos hasta la siguiente palabra de 16 bits.

        Es lo que hay que hacer al final de cada trozo de 32 KB: LZX empieza
        cada trozo en una palabra nueva.  **Los bits ya leídos que forman
        palabras enteras se conservan**; tirar el depósito entero perdería
        dieciséis bits y a partir de ahí no se descodifica nada.
        """
        sobran = self.cuantos % 16
        if sobran:
            self.leer(sobran)

    def alinear_bytes(self) -> None:
        """Se coloca en un byte entero, para leer datos en crudo.

        Lo usan los bloques sin comprimir.  Si en el depósito quedaba más de
        una palabra, hay que devolverla al flujo: si no, los bytes en crudo se
        leerían dos palabras más allá de donde están.
        """
        self._rellenar(16)
        if self.cuantos > 16:
            self.posicion -= 2
        self.cuantos = 0
        self.deposito = 0

    def bytes_de(self, cuantos: int) -> bytes:
        """Lee bytes en crudo, con el flujo ya alineado."""
        trozo = self.datos[self.posicion:self.posicion + cuantos]
        self.posicion += cuantos
        return trozo


class _Arbol:
    """Un árbol Huffman canónico, con su tabla de búsqueda rápida.

    La tabla convierte los ``BITS_MAXIMOS`` bits siguientes en el símbolo
    directamente, sin recorrer ningún árbol.  Es lo que hace que esto se pueda
    escribir en Python sin que tarde un minuto por megabyte: sin la tabla habría
    que decidir bit a bit, y son millones de bits.
    """

    __slots__ = ("longitudes", "tabla", "bits")

    def __init__(self, cuantos: int) -> None:
        self.longitudes = [0] * cuantos
        self.tabla: dict = {}
        self.bits = 0

    def construir(self) -> None:
        """Rehace la tabla de búsqueda a partir de las longitudes.

        Se sigue el reparto canónico: los códigos se asignan por longitud
        creciente y, dentro de cada longitud, por orden de símbolo.
        """
        self.bits = max(self.longitudes) if self.longitudes else 0
        if not self.bits:
            self.tabla = {}
            return
        self.bits = min(self.bits, BITS_MAXIMOS)
        tabla = [0] * (1 << self.bits)
        codigo = 0
        posicion = 0
        for largo in range(1, self.bits + 1):
            for simbolo, suyo in enumerate(self.longitudes):
                if suyo != largo:
                    continue
                # Cada código ocupa en la tabla tantas entradas como
                # combinaciones queden libres en los bits que no usa.
                cuantas = 1 << (self.bits - largo)
                inicio = codigo << (self.bits - largo)
                if inicio + cuantas > len(tabla):
                    raise ErrorLZX(_("El árbol de compresión del archivo no es válido."))
                for hueco in range(inicio, inicio + cuantas):
                    tabla[hueco] = (simbolo << 5) | largo
                codigo += 1
            codigo <<= 1
            posicion += 1
        self.tabla = tabla

    def leer(self, bits: _Bits) -> int:
        """Descodifica el siguiente símbolo."""
        if not self.bits:
            raise ErrorLZX(_("El archivo usa un árbol de compresión vacío."))
        vistos = bits.mirar(self.bits)
        entrada = self.tabla[vistos]
        largo = entrada & 0x1F
        if not largo:
            raise ErrorLZX(_("El archivo comprimido tiene un código que no existe."))
        bits.saltar(largo)
        return entrada >> 5


def _leer_longitudes(bits: _Bits, arbol: _Arbol, desde: int, hasta: int) -> None:
    """Lee las longitudes de un árbol, que van como diferencias comprimidas.

    Primero viene el *pretree* —veinte símbolos de cuatro bits cada uno— y
    después, con él, las diferencias respecto a las longitudes que tenía el
    árbol en el bloque anterior.
    """
    prearbol = _Arbol(NUM_PREARBOL)
    for numero in range(NUM_PREARBOL):
        prearbol.longitudes[numero] = bits.leer(4)
    prearbol.construir()

    posicion = desde
    while posicion < hasta:
        simbolo = prearbol.leer(bits)
        if simbolo == 17:
            # Tantos ceros seguidos.
            cuantos = bits.leer(4) + 4
            for _repetido in range(cuantos):
                if posicion >= hasta:
                    break
                arbol.longitudes[posicion] = 0
                posicion += 1
        elif simbolo == 18:
            cuantos = bits.leer(5) + 20
            for _repetido in range(cuantos):
                if posicion >= hasta:
                    break
                arbol.longitudes[posicion] = 0
                posicion += 1
        elif simbolo == 19:
            # Tantas veces la misma longitud, que viene detrás.
            cuantos = bits.leer(1) + 4
            siguiente = prearbol.leer(bits)
            valor = (arbol.longitudes[posicion] - siguiente) % 17
            for _repetido in range(cuantos):
                if posicion >= hasta:
                    break
                arbol.longitudes[posicion] = valor
                posicion += 1
        else:
            arbol.longitudes[posicion] = (arbol.longitudes[posicion] - simbolo) % 17
            posicion += 1


class Descompresor:
    """Descomprime un flujo LZX conservando el estado entre bloques.

    El estado —las longitudes de los árboles, las tres distancias recientes y la
    ventana de salida— se arrastra de un bloque al siguiente, y solo se pone a
    cero en los puntos de reinicio que marque quien llama.  Por eso esto es un
    objeto y no una función.

    :param bits_ventana: Logaritmo del tamaño de la ventana.  En los archivos de
                         ayuda suele ser 16, o sea 64 KB.
    """

    def __init__(self, bits_ventana: int = 16) -> None:
        if bits_ventana not in _RANURAS:
            raise ErrorLZX(
                _("El archivo usa una ventana de compresión que no se admite."))
        self.bits_ventana = bits_ventana
        self.ranuras = _RANURAS[bits_ventana]
        self.principal = _Arbol(NUM_CARACTERES + self.ranuras * 8)
        self.secundario = _Arbol(NUM_SECUNDARIAS)
        self.alineado = _Arbol(NUM_ALINEADOS)
        #: Todo lo descomprimido hasta ahora.  Es a la vez la salida y la
        #: **ventana**: las coincidencias apuntan hacia atrás dentro de ella.
        self.historia = bytearray()
        #: Cuántos trozos de 32 KB se han sacado, que es lo que decide hasta
        #: cuándo se deshace la traducción de las llamadas.
        self.trozos = 0
        self.reiniciar()

    def reiniciar(self) -> None:
        """Reinicia el estado de la compresión **sin tirar la ventana**.

        Es la diferencia que hace que un archivo de ayuda se descomprima entero
        y no solo sus primeros sesenta y cuatro kilobytes.  En un punto de
        reinicio se ponen a cero las distancias recientes y los árboles —el
        compresor hizo lo mismo al escribirlo— pero **lo ya descomprimido sigue
        estando**, porque las coincidencias del tramo siguiente pueden apuntar
        hacia atrás, a lo que se leyó antes del reinicio.
        """
        self.recientes = [1, 1, 1]
        self.pendiente = 0
        self.tipo_bloque = 0
        self.traduccion = False
        self.tamano_traduccion = 0
        self.primer_bloque = True
        for arbol in (self.principal, self.secundario, self.alineado):
            arbol.longitudes = [0] * len(arbol.longitudes)

    # -- descompresión -------------------------------------------------------

    def descomprimir(self, datos: bytes, cuantos: int) -> bytes:
        """Descomprime hasta obtener ``cuantos`` bytes.

        :param datos: El trozo comprimido.
        :param cuantos: Cuántos bytes de salida se esperan.
        """
        bits = _Bits(datos)
        principio = len(self.historia)
        objetivo = principio + cuantos

        if self.primer_bloque:
            # El primer bloque dice si hay que deshacer la traducción de las
            # llamadas a función, y con qué tamaño de archivo.
            self.traduccion = bool(bits.leer(1))
            if self.traduccion:
                alto = bits.leer(16)
                bajo = bits.leer(16)
                self.tamano_traduccion = (alto << 16) | bajo
            self.primer_bloque = False

        # LZX reparte su salida en trozos de 32 KB y **empieza cada trozo en
        # una palabra de 16 bits nueva**.  Descomprimir de corrido, sin
        # realinear al pasar de un trozo al siguiente, da los primeros treinta
        # y dos kilobytes perfectos y basura a partir de ahí; es el fallo más
        # difícil de ver de todo el formato, porque parece que funciona.
        hecho = 0
        while hecho < cuantos:
            este = min(TROZO, cuantos - hecho)
            fin = principio + hecho + este
            while len(self.historia) < fin:
                if self.pendiente <= 0:
                    self._empezar_bloque(bits)
                trozo = min(self.pendiente, fin - len(self.historia))
                antes = len(self.historia)
                if self.tipo_bloque == 3:
                    self._bloque_sin_comprimir(bits, trozo)
                else:
                    self._bloque_comprimido(bits, trozo)
                producido = len(self.historia) - antes
                if producido == 0:
                    raise ErrorLZX(_("El archivo comprimido está cortado."))
                self.pendiente -= producido
            # Una coincidencia no puede rebasar el final de su trozo; si lo
            # hace, el archivo está mal y lo que sobra se tira antes de que
            # corra la ventana.
            del self.historia[fin:]
            hecho += este
            bits.alinear_palabra()

        salida = bytes(self.historia[principio:objetivo])
        if self.traduccion and self.tamano_traduccion:
            salida = self._deshacer_traduccion(salida, principio)
        self.trozos += max(1, (cuantos + TROZO - 1) // TROZO)
        return salida

    def _empezar_bloque(self, bits: _Bits) -> None:
        """Lee la cabecera del bloque siguiente y sus árboles."""
        self.tipo_bloque = bits.leer(3)
        alto = bits.leer(8)
        medio = bits.leer(8)
        bajo = bits.leer(8)
        self.pendiente = (alto << 16) | (medio << 8) | bajo

        if self.tipo_bloque == 1:                    # verbatim
            _leer_longitudes(bits, self.principal, 0, NUM_CARACTERES)
            _leer_longitudes(bits, self.principal, NUM_CARACTERES,
                             len(self.principal.longitudes))
            self.principal.construir()
            _leer_longitudes(bits, self.secundario, 0, NUM_SECUNDARIAS)
            self.secundario.construir()
        elif self.tipo_bloque == 2:                  # aligned offset
            for numero in range(NUM_ALINEADOS):
                self.alineado.longitudes[numero] = bits.leer(3)
            self.alineado.construir()
            _leer_longitudes(bits, self.principal, 0, NUM_CARACTERES)
            _leer_longitudes(bits, self.principal, NUM_CARACTERES,
                             len(self.principal.longitudes))
            self.principal.construir()
            _leer_longitudes(bits, self.secundario, 0, NUM_SECUNDARIAS)
            self.secundario.construir()
        elif self.tipo_bloque == 3:                  # sin comprimir
            bits.alinear_bytes()
            self.recientes = [
                int.from_bytes(bits.bytes_de(4), "little") for _hueco in range(HUECOS)]
        else:
            raise ErrorLZX(_("El archivo usa un tipo de bloque desconocido."))

    def _bloque_sin_comprimir(self, bits: _Bits, cuantos: int) -> None:
        """Copia tal cual los bytes de un bloque sin comprimir."""
        self.historia += bits.bytes_de(cuantos)

    def _bloque_comprimido(self, bits: _Bits, cuantos: int) -> None:
        """Descodifica símbolos hasta llenar el trozo pedido."""
        alineado = self.tipo_bloque == 2
        objetivo = len(self.historia) + cuantos
        while len(self.historia) < objetivo:
            simbolo = self.principal.leer(bits)
            if simbolo < NUM_CARACTERES:
                self.historia.append(simbolo)
                continue

            simbolo -= NUM_CARACTERES
            ranura = simbolo >> 3
            largo = simbolo & 7
            if largo == 7:
                largo += self.secundario.leer(bits)
            largo += _LONGITUD_BASE

            distancia = self._distancia(bits, ranura, alineado)
            self._copiar(distancia, largo)

    def _distancia(self, bits: _Bits, ranura: int, alineado: bool) -> int:
        """Calcula la distancia a la que hay que copiar.

        Las tres primeras ranuras no son distancias: son «la misma de antes»,
        que es lo que hace de LZX un buen compresor de texto repetido.
        """
        if ranura < HUECOS:
            distancia = self.recientes[ranura]
            if ranura:
                self.recientes[ranura] = self.recientes[0]
                self.recientes[0] = distancia
            return distancia

        extras = _EXTRAS[ranura]
        if alineado and extras >= 3:
            # Con ranura alineada, los tres bits de menos peso vienen por su
            # propio árbol y el resto en crudo.
            resto = bits.leer(extras - 3) << 3
            resto += self.alineado.leer(bits)
        elif extras:
            resto = bits.leer(extras)
        else:
            resto = 0
        distancia = _BASES[ranura] + resto - (HUECOS - 1)
        self.recientes[2] = self.recientes[1]
        self.recientes[1] = self.recientes[0]
        self.recientes[0] = distancia
        return distancia

    def _copiar(self, distancia: int, largo: int) -> None:
        """Copia una coincidencia de lo ya escrito.

        Se copia byte a byte y no de una vez a propósito: en LZX la distancia
        puede ser menor que la longitud —así se codifica una secuencia que se
        repite— y entonces lo que se copia incluye lo que se acaba de escribir.
        """
        salida = self.historia
        inicio = len(salida) - distancia
        if inicio < 0:
            raise ErrorLZX(_("El archivo comprimido apunta fuera de la ventana."))
        for posicion in range(inicio, inicio + largo):
            salida.append(salida[posicion])

    #: Instrucción de llamada del procesador, que es lo que LZX traduce.
    _LLAMADA = 0xE8

    def _deshacer_traduccion(self, datos: bytes, desde: int) -> bytes:
        """Devuelve las direcciones de las llamadas a como estaban.

        LZX se inventó para comprimir programas, y antes de comprimir convierte
        el destino relativo de cada llamada en una dirección absoluta, que se
        repite más y comprime mejor.  Aquí se deshace.  En un archivo de ayuda
        casi nunca hay nada que deshacer, pero cuando lo hay y no se deshace,
        cambian cuatro bytes del texto sin que se note hasta leerlo.
        """
        if len(datos) <= 10 or self.trozos >= 32768:
            return datos
        salida = bytearray(datos)
        tamano = self.tamano_traduccion
        posicion = 0
        limite = len(salida) - 10
        while posicion < limite:
            if salida[posicion] != self._LLAMADA:
                posicion += 1
                continue
            # La posición que cuenta es la **absoluta** dentro del archivo
            # descomprimido, no la del trozo: usar la del trozo deja mal todas
            # las llamadas a partir del segundo.
            actual = desde + posicion
            absoluta = int.from_bytes(salida[posicion + 1:posicion + 5], "little",
                                      signed=True)
            if -actual <= absoluta < tamano:
                if absoluta >= 0:
                    relativa = absoluta - actual
                else:
                    relativa = absoluta + tamano
                salida[posicion + 1:posicion + 5] = (
                    relativa & 0xFFFFFFFF).to_bytes(4, "little")
            posicion += 5
        return bytes(salida)


def descomprimir(datos: bytes, cuantos: int, bits_ventana: int = 16) -> bytes:
    """Descomprime un flujo LZX de una sola pieza."""
    return Descompresor(bits_ventana).descomprimir(datos, cuantos)
