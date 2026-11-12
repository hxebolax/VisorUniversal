# -*- coding: utf-8 -*-
"""Archivos de ayuda de Windows 3.x y 95: los `.hlp`, anteriores al CHM.

Son los manuales de todo un decenio de programas, y hoy no hay nada que los
abra: Windows dejó de traer el visor en Vista, después dejó de ofrecerlo, y a
partir de Windows 10 el parche oficial ni siquiera se instala.  Quien tiene un
manual en `.hlp` tiene un archivo que ya no puede leer nadie.

El programa ya sabe leer su sucesor, el CHM, y lo hace descomprimiendo LZX por
su cuenta.  Este es el mismo problema una generación antes, y por dentro es un
sistema de archivos —igual que el `.doc`, pero otro— con:

* un **directorio en árbol B+** que asocia nombres internos con posiciones;
* un archivo `|SYSTEM` que dice de qué versión es y cómo está comprimido;
* un archivo `|TOPIC` con el contenido, partido en bloques que pueden ir
  comprimidos con LZ77;
* y, encima de eso, una **segunda compresión por frases**: las palabras que más
  se repiten en el manual están en una tabla aparte y en el texto solo va su
  número.  Hay dos maneras de guardar esa tabla, y un archivo puede usar
  cualquiera de las dos.

**Lo que se saca es el texto de cada tema, con su título**, que es un manual
que se puede leer, buscar y marcar.  No se sacan los saltos de hipertexto ni
las imágenes: el formato las guarda como mapas de bits de 1990 con su propia
compresión, y no es lo que hace falta para poder leer el manual.

La descripción del formato que se sigue está en
``adjuntos/Estudio/helpdeco/helpfile.txt``, que es el trabajo de Manfred
Winterhoff volcando quinientos archivos de ayuda para averiguar qué significaba
cada byte, porque Microsoft nunca lo publicó.
"""

from __future__ import annotations

import struct
from pathlib import Path

from nucleo.documento import Metadatos
from nucleo.idioma import _
from nucleo.idioma import _n
from nucleo.registro import obtener_registro

from .base import Analizador, ErrorFormato, OpcionesAnalisis, registrar
from .ensamblador import escapar, montar

log = obtener_registro(__name__)

#: Los cuatro bytes con los que empieza un archivo de ayuda.
MAGIA = 0x00035F3F

#: Tope de lo que se descomprime, para que un archivo mal formado no vacíe la
#: memoria diciendo que un bloque ocupa cuatro gigabytes.
MAXIMO = 64 * 1024 * 1024

#: Cuántos temas se leen como mucho.  Un manual de verdad no pasa de unos pocos
#: miles; más que eso es que se ha interpretado mal algo.
MAXIMOS_TEMAS = 20000


class ErrorHLP(Exception):
    """El archivo no es un `.hlp` o está roto más allá de lo recuperable."""


# ---------------------------------------------------------------------------
# LZ77, el de los archivos de ayuda
# ---------------------------------------------------------------------------

def descomprimir_lz77(datos: bytes, tope: int = MAXIMO) -> bytes:
    """Deshace la compresión LZ77 de un archivo de ayuda.

    Es la variante más sencilla que existe y cabe en veinte líneas: un byte de
    banderas manda sobre los ocho trozos siguientes, y cada bit dice si lo que
    viene es un byte tal cual o una pareja «vuelve tantos y copia tantos».  Los
    doce bits de la distancia dan una ventana de cuatro kilobytes, que es lo que
    se llevaba en 1990.
    """
    salida = bytearray()
    posicion = 0
    largo = len(datos)
    while posicion < largo and len(salida) < tope:
        banderas = datos[posicion]
        posicion += 1
        for bit in range(8):
            if posicion >= largo or len(salida) >= tope:
                break
            if not (banderas & (1 << bit)):
                salida.append(datos[posicion])
                posicion += 1
                continue
            if posicion + 1 >= largo:
                return bytes(salida)
            (pareja,) = struct.unpack_from("<H", datos, posicion)
            posicion += 2
            distancia = (pareja & 0x0FFF) + 1
            cuantos = (pareja >> 12) + 3
            if distancia > len(salida):
                # Referencia a antes del principio: el archivo está roto. Se
                # devuelve lo que se lleve, que es lo útil.
                return bytes(salida)
            inicio = len(salida) - distancia
            for numero in range(cuantos):
                salida.append(salida[inicio + numero])
    return bytes(salida)


# ---------------------------------------------------------------------------
# El sistema de archivos interno
# ---------------------------------------------------------------------------

def _corto(datos: bytes, sitio: int):
    """Un entero corto «comprimido»: uno o dos bytes según el primero.

    Es la codificación de longitud variable del formato: si el byte es par vale
    la mitad; si es impar, la mitad más ciento veintiocho veces el siguiente.
    Los valores pequeños —que son casi todos— ocupan un byte.
    """
    if sitio >= len(datos):
        raise ErrorHLP("número comprimido fuera del archivo")
    crudo = datos[sitio]
    if crudo & 1:
        if sitio + 1 >= len(datos):
            raise ErrorHLP("número comprimido truncado")
        return (crudo >> 1) + 128 * datos[sitio + 1], sitio + 2
    return crudo >> 1, sitio + 1


def _largo(datos: bytes, sitio: int):
    """Lo mismo con dos o cuatro bytes."""
    if sitio + 2 > len(datos):
        raise ErrorHLP("número comprimido fuera del archivo")
    crudo = struct.unpack_from("<H", datos, sitio)[0]
    if crudo & 1:
        if sitio + 4 > len(datos):
            raise ErrorHLP("número comprimido truncado")
        return (crudo >> 1) + 32768 * struct.unpack_from("<H", datos, sitio + 2)[0], sitio + 4
    return crudo >> 1, sitio + 2


def descomprimir_runlen(datos: bytes, tope: int) -> bytes:
    """La otra compresión del formato, la de las imágenes.

    Es la más simple que existe: un byte manda, y o dice «copia estos tantos
    tal cual» o «repite el siguiente tantas veces».  En un icono de dieciséis
    colores, donde hay zonas planas grandes, deja el archivo en la mitad.
    """
    salida = bytearray()
    sitio = 0
    while sitio < len(datos) and len(salida) < tope:
        mandato = datos[sitio]
        sitio += 1
        if mandato & 0x80:
            cuantos = mandato & 0x7F
            salida += datos[sitio:sitio + cuantos]
            sitio += cuantos
        else:
            if sitio >= len(datos):
                break
            salida += bytes((datos[sitio],)) * mandato
            sitio += 1
    return bytes(salida)


class Ayuda:
    """Un archivo de ayuda abierto, con sus archivos internos por nombre."""

    def __init__(self, datos: bytes) -> None:
        self.datos = datos
        if len(datos) < 16:
            raise ErrorHLP("el archivo se corta antes de la cabecera")
        (magia, self.inicio_directorio, _libres,
         self.tamano) = struct.unpack_from("<iiii", datos, 0)
        if magia != MAGIA:
            raise ErrorHLP("no empieza por la marca de un archivo de ayuda")
        self.archivos = self._leer_directorio()

    # -- el directorio -------------------------------------------------------

    def _interno(self, posicion: int) -> bytes:
        """El contenido de un archivo interno que empieza en esa posición.

        Delante de cada uno hay nueve bytes que dicen cuánto ocupa reservado y
        cuánto ocupa de verdad; lo que interesa es lo segundo.
        """
        if posicion < 0 or posicion + 9 > len(self.datos):
            return b""
        _reservado, usado = struct.unpack_from("<ii", self.datos, posicion)
        if usado < 0 or usado > MAXIMO:
            return b""
        return self.datos[posicion + 9:posicion + 9 + usado]

    def _leer_directorio(self) -> dict[str, int]:
        """Los nombres internos y dónde está cada uno.

        El directorio es un árbol B+, pero para lo que hace falta aquí —tenerlos
        todos— no hay que bajar por el árbol: las hojas están encadenadas entre
        sí, así que basta con recorrer todas las páginas y quedarse con las que
        son hojas.  Es más simple y además aguanta mejor un archivo con el árbol
        estropeado, que es la mitad de los que quedan.
        """
        crudo = self._interno(self.inicio_directorio)
        if len(crudo) < 38:
            raise ErrorHLP("el directorio interno está vacío o incompleto")
        (magia, _banderas, tamano_pagina) = struct.unpack_from("<HHH", crudo, 0)
        if magia != 0x293B:
            raise ErrorHLP("el directorio no tiene la marca que le corresponde")
        (_ceros, _divisiones, _raiz, _menos_uno, paginas,
         niveles) = struct.unpack_from("<hhhhhh", crudo, 22)
        salida: dict[str, int] = {}
        base = 38
        for numero in range(max(paginas, 0)):
            inicio = base + numero * tamano_pagina
            pagina = crudo[inicio:inicio + tamano_pagina]
            if len(pagina) < 8:
                break
            self._leer_hoja(pagina, niveles, salida)
        if not salida:
            raise ErrorHLP("el directorio no lista ningún archivo interno")
        return salida

    @staticmethod
    def _leer_hoja(pagina: bytes, niveles: int, salida: dict) -> None:
        """Saca los nombres de una página del árbol, si es una hoja.

        Una hoja y una página índice se distinguen por su tamaño de cabecera:
        ocho bytes la hoja —que además apunta a la anterior y a la siguiente— y
        seis la índice.  Con un solo nivel, todas son hojas.
        """
        (_sin_usar, cuantas, _antes, _despues) = struct.unpack_from("<Hhhh",
                                                                    pagina, 0)
        if cuantas <= 0 or cuantas > 4096:
            return
        posicion = 8
        for _numero in range(cuantas):
            fin = pagina.find(b"\x00", posicion)
            if fin < 0 or fin + 5 > len(pagina):
                return
            nombre = pagina[posicion:fin].decode("cp1252", "replace")
            (donde,) = struct.unpack_from("<i", pagina, fin + 1)
            posicion = fin + 5
            if nombre and nombre not in salida:
                salida[nombre] = donde

    # -- lo que se usa desde fuera -------------------------------------------

    def nombres(self) -> list[str]:
        return sorted(self.archivos)

    def archivo(self, nombre: str) -> bytes:
        """El contenido de un archivo interno, o vacío si no está."""
        if nombre in self.archivos:
            return self._interno(self.archivos[nombre])
        plano = nombre.lower()
        for otro, donde in self.archivos.items():
            if otro.lower() == plano:
                return self._interno(donde)
        return b""


# ---------------------------------------------------------------------------
# |SYSTEM: de qué versión es y cómo está comprimido
# ---------------------------------------------------------------------------

class Sistema:
    """Lo que el archivo dice de sí mismo."""

    __slots__ = ("menor", "mayor", "banderas", "titulo", "copyright")

    def __init__(self, crudo: bytes) -> None:
        self.menor = self.mayor = 0
        self.banderas = 0
        self.titulo = self.copyright = ""
        if len(crudo) < 12:
            return
        (magia, self.menor, self.mayor, _fecha,
         self.banderas) = struct.unpack_from("<HHHiH", crudo, 0)
        if magia != 0x036C:
            return
        if self.menor <= 16:
            fin = crudo.find(b"\x00", 12)
            self.titulo = crudo[12:fin if fin > 0 else len(crudo)].decode(
                "cp1252", "replace")
            return
        self._leer_registros(crudo)

    def _leer_registros(self, crudo: bytes) -> None:
        """Los datos sueltos que trae la versión moderna del formato."""
        posicion = 12
        while posicion + 4 <= len(crudo):
            tipo, largo = struct.unpack_from("<HH", crudo, posicion)
            cuerpo = crudo[posicion + 4:posicion + 4 + largo]
            if tipo == 1:
                self.titulo = cuerpo.split(b"\x00")[0].decode("cp1252", "replace")
            elif tipo == 2:
                self.copyright = cuerpo.split(b"\x00")[0].decode("cp1252",
                                                                 "replace")
            posicion += 4 + largo

    @property
    def comprimido(self) -> bool:
        """Si los bloques de contenido van comprimidos con LZ77."""
        return self.menor > 16 and self.banderas in (4, 8)

    @property
    def tamano_bloque(self) -> int:
        """Cuánto ocupa cada bloque de contenido en el archivo."""
        if self.menor <= 16:
            return 2048
        return 2048 if self.banderas == 8 else 4096

    @property
    def tamano_descomprimido(self) -> int:
        """A cuánto se descomprime cada bloque."""
        return 16384 if self.comprimido else self.tamano_bloque - 12


# ---------------------------------------------------------------------------
# Las frases: la segunda compresión
# ---------------------------------------------------------------------------

def frases_clasicas(crudo: bytes) -> list[bytes]:
    """La tabla de frases al estilo de Windows 3.

    Las frases no acaban en cero: se sabe dónde acaba cada una porque la
    siguiente dice dónde empieza, y por eso hay una posición de más al final.
    """
    if len(crudo) < 6:
        return []
    (cuantas, cien) = struct.unpack_from("<HH", crudo, 0)
    if cien != 0x0100 or cuantas > 65000:
        return []
    # Windows 3.1 en adelante comprime además el montón de letras.
    comprimido = len(crudo) >= 10 + 2 * (cuantas + 1)
    base = 4
    tamano_final = 0
    if comprimido:
        (tamano_final,) = struct.unpack_from("<i", crudo, 4)
        base = 8
    if base + 2 * (cuantas + 1) > len(crudo):
        return []
    posiciones = list(struct.unpack_from("<%dH" % (cuantas + 1), crudo, base))
    letras = crudo[base + 2 * (cuantas + 1):]
    if comprimido and 0 < tamano_final <= MAXIMO:
        letras = descomprimir_lz77(letras, tamano_final)
    primera = posiciones[0]
    salida = []
    for numero in range(cuantas):
        desde = posiciones[numero] - primera
        hasta = posiciones[numero + 1] - primera
        if 0 <= desde <= hasta <= len(letras):
            salida.append(letras[desde:hasta])
        else:
            salida.append(b"")
    return salida


def frases_hall(indice: bytes, imagen: bytes) -> list[bytes]:
    """La tabla de frases al estilo de Windows 95.

    Aquí las longitudes no se guardan como números: se guardan **bit a bit**,
    porque casi todas son pequeñas y así ocupan una fracción.  Se leen con un
    lector de bits que va de cuatro en cuatro bytes, que es como lo escribió
    quien hizo el compilador.
    """
    if len(indice) < 28:
        return []
    (magia, cuantas, _comprimido, tamano_imagen,
     tamano_comprimido, _cero) = struct.unpack_from("<iiiiii", indice, 0)
    if magia != 1 or cuantas <= 0 or cuantas > 65000:
        return []
    (mezcla,) = struct.unpack_from("<H", indice, 24)
    bits_extra = mezcla & 0x000F
    letras = imagen
    if tamano_comprimido != tamano_imagen and 0 < tamano_imagen <= MAXIMO:
        letras = descomprimir_lz77(imagen, tamano_imagen)

    lector = _Bits(indice, 28)
    posiciones = [0]
    for _numero in range(cuantas):
        largo = 1
        while lector.bit():
            largo += 1 << bits_extra
            if largo > 1 << 20:
                return []
        for desplazamiento in range(min(bits_extra + 1, 5)):
            if lector.bit():
                largo += 1 << desplazamiento
        posiciones.append(posiciones[-1] + largo)
    return [letras[posiciones[numero]:posiciones[numero + 1]]
            for numero in range(cuantas)
            if posiciones[numero + 1] <= len(letras)]


class _Bits:
    """Lee bits de cuatro en cuatro bytes, como los escribió el compilador."""

    __slots__ = ("datos", "posicion", "mascara", "actual")

    def __init__(self, datos: bytes, desde: int) -> None:
        self.datos = datos
        self.posicion = desde
        self.mascara = 0
        self.actual = 0

    def bit(self) -> int:
        if self.mascara == 0:
            if self.posicion + 4 > len(self.datos):
                return 0
            (self.actual,) = struct.unpack_from("<I", self.datos, self.posicion)
            self.posicion += 4
            self.mascara = 1
        valor = 1 if self.actual & self.mascara else 0
        self.mascara = (self.mascara << 1) & 0xFFFFFFFF
        return valor


def descomprimir_frases(datos: bytes, frases: list[bytes], hall: bool) -> bytes:
    """Devuelve el texto con sus frases puestas en su sitio.

    Son dos códigos distintos según cómo se guardara la tabla, y los dos hacen
    lo mismo: donde el texto trae un número, se pone la frase que le
    corresponde.  Es lo que reduce a la mitad un manual lleno de «haga clic en
    el botón».
    """
    salida = bytearray()
    posicion = 0
    while posicion < len(datos) and len(salida) < MAXIMO:
        letra = datos[posicion]
        posicion += 1
        if hall:
            if letra % 2 == 0:
                _poner(salida, frases, letra // 2)
            elif letra & 0x03 == 0x01:
                if posicion >= len(datos):
                    break
                numero = (letra // 4) * 256 + datos[posicion] + 64
                posicion += 1
                _poner(salida, frases, numero)
            elif letra & 0x07 == 0x03:
                cuantas = letra // 8 + 1
                salida.extend(datos[posicion:posicion + cuantas])
                posicion += cuantas
            elif letra & 0x0F == 0x07:
                salida.extend(b" " * (letra // 16 + 1))
            else:
                salida.extend(b"\x00" * (letra // 16 + 1))
            continue
        if letra == 0 or letra > 15:
            salida.append(letra)
            continue
        if posicion >= len(datos):
            break
        numero = letra * 256 - 256 + datos[posicion]
        posicion += 1
        _poner(salida, frases, numero // 2)
        if numero % 2:
            salida.append(0x20)
    return bytes(salida)


def _poner(salida: bytearray, frases: list[bytes], numero: int) -> None:
    if 0 <= numero < len(frases):
        salida.extend(frases[numero])


# ---------------------------------------------------------------------------
# |TOPIC: el contenido
# ---------------------------------------------------------------------------

#: Tope de píxeles de una imagen suelta.  Las de un archivo de ayuda son iconos
#: y capturas de pantalla de 1993: ninguna real se acerca.
MAXIMO_IMAGEN = 16 * 1024 * 1024


def imagen_a_png(datos: bytes, sitio: int) -> bytes | None:
    """Convierte a PNG el mapa de bits que empieza en ``sitio``.

    Los archivos de ayuda guardan sus imágenes en el formato de SHED y MRBC, que
    es un mapa de bits de Windows con la cabecera escrita a mano y con dos
    compresiones a elegir.  Se admiten las de 1, 4, 8 y 24 bits, que son todas
    las que produjo aquella herramienta; un metarchivo —dibujo vectorial— no se
    convierte y se dice, porque redibujarlo es otro programa entero.
    """
    if sitio + 2 > len(datos):
        return None
    tipo, empaquetado = datos[sitio], datos[sitio + 1]
    if tipo not in (5, 6):
        # Tipo 8 es un metarchivo: instrucciones de dibujo, no píxeles.
        return None
    p = sitio + 2
    _xdpi, p = _largo(datos, p)
    _ydpi, p = _largo(datos, p)
    _planos, p = _corto(datos, p)
    bits, p = _corto(datos, p)
    ancho, p = _largo(datos, p)
    alto, p = _largo(datos, p)
    colores, p = _largo(datos, p)
    _importantes, p = _largo(datos, p)
    comprimido, p = _largo(datos, p)
    _puntos, p = _largo(datos, p)
    if p + 8 > len(datos):
        return None
    desplazamiento = struct.unpack_from("<I", datos, p)[0]
    p += 8
    if bits not in (1, 4, 8, 24) or not ancho or not alto:
        return None
    if ancho * alto > MAXIMO_IMAGEN:
        raise ErrorHLP("imagen imposible: %dx%d" % (ancho, alto))

    paleta = []
    if tipo == 6 and bits != 24:
        cuantos = colores or (1 << bits)
        if p + cuantos * 4 > len(datos):
            return None
        for i in range(cuantos):
            azul, verde, rojo = datos[p + i * 4:p + i * 4 + 3]
            paleta.append(bytes((rojo, verde, azul)))
    if not paleta and bits != 24:
        # Un mapa dependiente del dispositivo no trae paleta propia: se pinta en
        # grises, que es preferible a inventar colores.
        cuantos = 1 << bits
        paleta = [bytes((i * 255 // max(1, cuantos - 1),) * 3) for i in range(cuantos)]

    # Cada fila de un mapa de bits de Windows se rellena hasta un múltiplo de
    # cuatro bytes.  Olvidarlo inclina la imagen un poco más en cada fila, que
    # es el error clásico y se ve enseguida.
    paso = ((ancho * bits + 31) // 32) * 4
    esperado = paso * alto
    crudo = datos[sitio + desplazamiento:sitio + desplazamiento + comprimido]
    if empaquetado == 1:
        crudo = descomprimir_runlen(crudo, esperado)
    elif empaquetado == 2:
        crudo = descomprimir_lz77(crudo, esperado)
    elif empaquetado == 3:
        crudo = descomprimir_runlen(descomprimir_lz77(crudo, esperado * 2), esperado)
    elif empaquetado:
        return None
    crudo = crudo.ljust(esperado, b"\x00")

    filas = []
    # Un mapa de bits va de abajo arriba y un PNG de arriba abajo.
    for y in range(alto - 1, -1, -1):
        linea = crudo[y * paso:(y + 1) * paso]
        salida = bytearray(ancho * 3)
        for x in range(ancho):
            if bits == 24:
                salida[x * 3] = linea[x * 3 + 2]
                salida[x * 3 + 1] = linea[x * 3 + 1]
                salida[x * 3 + 2] = linea[x * 3]
                continue
            if bits == 8:
                indice = linea[x]
            elif bits == 4:
                pareja = linea[x >> 1]
                indice = (pareja >> 4) if not (x & 1) else (pareja & 15)
            else:
                indice = (linea[x >> 3] >> (7 - (x & 7))) & 1
            salida[x * 3:x * 3 + 3] = paleta[indice] if indice < len(paleta) \
                else b"\x00\x00\x00"
        filas.append(bytes(salida))

    from . import png

    return png.codificar(ancho, alto, filas)


def imagenes_de(ayuda: "Ayuda") -> dict:
    """Todas las imágenes del archivo, por su número: ``{0: png, 1: png}``.

    Van en archivos internos llamados ``|bm0``, ``|bm1``…, y cada uno puede
    traer **varias resoluciones de la misma imagen**.  Se coge la primera: las
    demás son la misma cosa para otra pantalla.
    """
    salida = {}
    for nombre in ayuda.archivos:
        corto = nombre.lstrip("|")
        if not corto.startswith("bm") or not corto[2:].isdigit():
            continue
        try:
            datos = ayuda.archivo(nombre)
            if datos is None or len(datos) < 8:
                continue
            _magia, cuantas = struct.unpack_from("<HH", datos, 0)
            if not 1 <= cuantas <= 64 or 4 + 4 * cuantas > len(datos):
                continue
            sitio = struct.unpack_from("<I", datos, 4)[0]
            imagen = imagen_a_png(datos, sitio)
        except Exception as error:
            log.debug("Imagen %s ilegible (%s)", nombre, error)
            continue
        if imagen:
            salida[int(corto[2:])] = imagen
    return salida


#: Los mandatos de formato que llevan datos detrás y cuántos bytes ocupan esos
#: datos.  Hay que saltárselos aunque no se usen: van seguidos, y equivocarse en
#: uno descoloca todos los de después.
_MANDATOS_FIJOS = {0x20: 4, 0x21: 2, 0x80: 2, 0xE0: 4, 0xE1: 4,
                   0xE2: 4, 0xE3: 4, 0xE6: 4, 0xE7: 4}

#: Los que traen una imagen.  Son el mismo mandato con tres alineaciones: en
#: medio, a la izquierda y a la derecha.
_MANDATOS_IMAGEN = (0x86, 0x87, 0x88)


def _saltar_parrafo(datos: bytes, tipo: int) -> int:
    """Dónde acaban los ajustes del párrafo y empiezan los de las letras.

    Es la parte que la documentación del formato llama «difícil de describir»:
    la mitad de los campos solo están si un bit de más arriba lo dice.  Se lee
    campo a campo comprobando su condición, que es la única manera.
    """
    _tamano, sitio = _largo(datos, 0)
    if tipo not in (1, 0x20, 0x23):
        raise ErrorHLP("registro de tipo %d" % tipo)
    if tipo == 1:
        return sitio
    _largo_tema, sitio = _corto(datos, sitio)
    if tipo == 0x23:
        columnas = datos[sitio]
        clase = datos[sitio + 1]
        sitio += 2
        if clase in (0, 2):
            sitio += 2
        sitio += 4 * columnas
        sitio += 5
    # Dos bytes sueltos que nadie ha sabido nunca para qué son, el
    # identificador y las banderas de lo que viene detrás.
    sitio += 4
    banderas = struct.unpack_from("<H", datos, sitio)[0]
    sitio += 2
    if banderas & 0x0001:
        _valor, sitio = _largo(datos, sitio)
    for bit in (0x0002, 0x0004, 0x0008, 0x0010, 0x0020, 0x0040):
        if banderas & bit:
            _valor, sitio = _corto(datos, sitio)
    if banderas & 0x0100:
        sitio += 3
    if banderas & 0x0200:
        cuantas, sitio = _corto(datos, sitio)
        for _i in range(cuantas):
            parada, sitio = _corto(datos, sitio)
            if parada & 0x4000:
                _clase, sitio = _corto(datos, sitio)
    return sitio


def imagenes_del_parrafo(datos: bytes, tipo: int) -> list:
    """Qué imágenes lleva este párrafo y detrás de qué trozo de texto.

    Devuelve pares ``(cuántos trozos van antes, número de imagen)``.  El formato
    alterna: un trozo de texto, un mandato de formato, otro trozo, otro mandato.
    Contando los mandatos se sabe en qué punto del párrafo estaba la imagen, que
    es la diferencia entre leer «pulse el botón [imagen] para seguir» y leer el
    párrafo con la imagen suelta al final.
    """
    salida = []
    sitio = _saltar_parrafo(datos, tipo)
    trozos_antes = 0
    while sitio < len(datos):
        mandato = datos[sitio]
        sitio += 1
        if mandato == 0xFF:
            break
        trozos_antes += 1
        if mandato in _MANDATOS_FIJOS:
            sitio += _MANDATOS_FIJOS[mandato]
        elif mandato in (0x81, 0x82, 0x83, 0x89, 0x8B, 0x8C):
            continue
        elif mandato in (0xC8, 0xCC):
            largo = struct.unpack_from("<H", datos, sitio)[0]
            sitio += max(2, largo - 1)
        elif mandato in (0xEA, 0xEB, 0xEE, 0xEF):
            largo = struct.unpack_from("<H", datos, sitio)[0]
            sitio += max(2, largo)
        elif mandato in _MANDATOS_IMAGEN:
            clase = datos[sitio]
            sitio += 1
            tamano, sitio = _largo(datos, sitio)
            if clase == 0x22:
                _puntos, sitio = _corto(datos, sitio)
            if clase in (3, 0x22) and tamano >= 4:
                incrustada = struct.unpack_from("<h", datos, sitio)[0]
                if incrustada == 0:
                    cual = struct.unpack_from("<h", datos, sitio + 2)[0]
                    if cual >= 0:
                        salida.append((trozos_antes, cual))
            sitio += tamano
        else:
            # Un mandato que no se conoce deja de ser seguro seguir leyendo:
            # a partir de aquí las posiciones ya no son fiables y lo honrado es
            # quedarse con lo que se sabe.
            break
    return salida


class Tema:
    """Un tema del manual: su título, su texto y sus imágenes.

    Las piezas van en el orden en que aparecen —un texto, una imagen, más
    texto—, porque en un manual de 1993 la frase y la captura de pantalla que la
    acompaña se leen juntas o no se entienden.
    """

    __slots__ = ("titulo", "piezas")

    def __init__(self, titulo: str = "") -> None:
        self.titulo = titulo
        self.piezas: list[tuple[str, object]] = []

    @property
    def parrafos(self) -> list:
        """Solo el texto, para quien no necesite las imágenes."""
        return [pieza for clase, pieza in self.piezas if clase == "texto"]

    def __bool__(self) -> bool:
        return bool(self.titulo or self.piezas)


def temas_de(crudo: bytes, sistema: Sistema, frases: list[bytes],
             hall: bool) -> list[Tema]:
    """Lee el contenido y lo devuelve como temas con su texto.

    El contenido va partido en bloques del tamaño que diga el archivo, cada uno
    con doce bytes de cabecera y el resto comprimido o no.  Se descomprimen
    todos, se **rellenan hasta su tamaño completo** y se pegan: el formato
    cuenta las posiciones como si cada bloque ocupara siempre lo mismo, y sin
    ese relleno las cuentas se desplazan y a partir del tercer bloque se lee
    basura.

    Sobre el resultado se van leyendo los enlaces: uno de ellos abre un tema
    nuevo y los demás traen texto.  **Un enlace no empieza a caballo de dos
    bloques**: cuando en la cola de uno no cabe una cabecera entera, el
    compilador la deja sin usar y sigue en el siguiente. Es justo lo que hacía
    parar la lectura a la tercera pantalla, y es lo que aquí se salta.
    """
    tamano = max(sistema.tamano_bloque, 32)
    hueco = sistema.tamano_descomprimido
    bloques = []
    posicion = 0
    while posicion + 12 <= len(crudo):
        cuerpo = crudo[posicion + 12:posicion + tamano]
        if sistema.comprimido:
            cuerpo = descomprimir_lz77(cuerpo, hueco)
        bloques.append(cuerpo.ljust(hueco, b"\x00")[:hueco])
        posicion += tamano
    entero = b"".join(bloques)

    temas: list[Tema] = []
    actual = Tema()
    lugar = 0
    while lugar + 21 <= len(entero) and len(temas) < MAXIMOS_TEMAS:
        (tamano_enlace, largo2, _antes, _despues,
         largo1) = struct.unpack_from("<iiiii", entero, lugar)
        tipo = entero[lugar + 20]
        if not 21 < tamano_enlace <= len(entero) - lugar or largo1 < 21:
            siguiente = (lugar // hueco + 1) * hueco
            if siguiente <= lugar or siguiente >= len(entero):
                break
            lugar = siguiente
            continue
        datos2 = entero[lugar + largo1:lugar + tamano_enlace]
        if largo2 > len(datos2) and frases:
            datos2 = descomprimir_frases(datos2, frases, hall)
        if tipo == 2:
            if actual:
                temas.append(actual)
            actual = Tema(_primera_cadena(datos2))
        elif tipo in (1, 0x20, 0x23):
            datos1 = entero[lugar + 21:lugar + largo1]
            try:
                donde = imagenes_del_parrafo(datos1, tipo)
            except Exception:
                # Un párrafo cuyos ajustes no se dejan leer sigue teniendo su
                # texto: se pierde la colocación de sus imágenes y nada más.
                donde = []
            for pieza in _piezas_de(datos2, donde):
                actual.piezas.append(pieza)
        lugar += tamano_enlace
    if actual:
        temas.append(actual)
    return temas


def _piezas_de(datos: bytes, imagenes: list) -> list:
    """Parte el texto en piezas y mete las imágenes en su sitio."""
    trozos_texto = datos.split(b"\x00")
    por_sitio: dict = {}
    for cuantos, cual in imagenes:
        por_sitio.setdefault(cuantos, []).append(cual)
    piezas = []
    acumulado = []
    for numero, trozo in enumerate(trozos_texto):
        limpio = _limpiar_trozo(trozo)
        if limpio:
            acumulado.append(limpio)
        if numero + 1 in por_sitio:
            if acumulado:
                piezas.append(("texto", "\n".join(acumulado)))
                acumulado = []
            for cual in por_sitio[numero + 1]:
                piezas.append(("imagen", cual))
    if acumulado:
        piezas.append(("texto", "\n".join(acumulado)))
    # Una imagen que decía ir más allá del último trozo va al final: vale más
    # tenerla mal colocada que perderla.
    ultimo = len(trozos_texto)
    for cuantos, cual in imagenes:
        if cuantos > ultimo:
            piezas.append(("imagen", cual))
    return piezas


def _limpiar_trozo(trozo: bytes) -> str:
    """Un trozo de texto del archivo, ya legible."""
    texto = trozo.decode("cp1252", "replace")
    texto = texto.replace("\r\n", "\n").replace("\r", "\n")
    # Los archivos de ayuda usan estos dos para las tabulaciones internas.
    texto = texto.replace("\x0b", " ").replace("\x0c", "\n")
    return " ".join(texto.split())


def _primera_cadena(datos: bytes) -> str:
    """El primer texto de un bloque: en un encabezado, el título del tema."""
    return datos.split(b"\x00")[0].decode("cp1252", "replace").strip()


def _texto_de(datos: bytes) -> str:
    """El texto de un bloque, con sus párrafos separados.

    El contenido son cadenas terminadas en cero, una por trozo con el mismo
    formato.  Se pegan con un espacio cuando lo que se cortó fue una línea y se
    separan con un salto cuando era un párrafo, que es lo que se nota al leer.
    """
    partes = [limpio for limpio in (_limpiar_trozo(trozo)
                                    for trozo in datos.split(b"\x00")) if limpio]
    return "\n".join(partes)


# ---------------------------------------------------------------------------
# El analizador
# ---------------------------------------------------------------------------

#: Con qué nombre se piden las imágenes desde el documento.
NOMBRE_IMAGEN = "imagen%d.png"


def leer(ruta) -> tuple[Sistema, list[Tema]]:
    """Abre un archivo de ayuda y devuelve lo que dice de sí mismo y sus temas."""
    try:
        datos = Path(ruta).read_bytes()
    except OSError as error:
        raise ErrorHLP("no se ha podido leer: %s" % error) from error
    ayuda = Ayuda(datos)
    sistema = Sistema(ayuda.archivo("|SYSTEM"))
    frases = frases_clasicas(ayuda.archivo("|Phrases"))
    hall = False
    if not frases:
        indice = ayuda.archivo("|PhrIndex")
        imagen = ayuda.archivo("|PhrImage")
        if indice and imagen:
            frases = frases_hall(indice, imagen)
            hall = bool(frases)
    contenido = ayuda.archivo("|TOPIC")
    if not contenido:
        raise ErrorHLP("el archivo no tiene contenido que leer")
    return sistema, temas_de(contenido, sistema, frases, hall)


class AnalizadorHLP(Analizador):
    """Archivos de ayuda de Windows 3.x y 95."""

    extensiones = (".hlp",)
    descripcion = _("Archivos de ayuda de Windows (anteriores al CHM)")

    def analizar(self, ruta, opciones: OpcionesAnalisis):
        camino = Path(ruta)
        try:
            sistema, temas = leer(camino)
        except ErrorHLP as error:
            raise ErrorFormato(_(
                "Este archivo de ayuda no se ha podido leer: %s") % error) from error
        con_texto = [tema for tema in temas if tema.piezas or tema.titulo]
        if not con_texto:
            raise ErrorFormato(_(
                "Este archivo de ayuda no tiene texto que leer."))
        secciones = []
        for numero, tema in enumerate(con_texto, start=1):
            titulo = tema.titulo or _("Tema %d") % numero
            partes = ["<h1>%s</h1>" % escapar(titulo)]
            for clase, pieza in tema.piezas:
                if clase == "imagen":
                    # Sin texto alternativo a propósito: el formato no lo tiene,
                    # así que la imagen queda **marcada como pendiente de
                    # describir** y se puede mandar a la IA, en vez de aparecer
                    # con una descripción inventada.
                    partes.append("<img src=\"%s\"/>" % (NOMBRE_IMAGEN % pieza))
                    continue
                for renglon in pieza.split("\n"):
                    if renglon.strip():
                        partes.append("<p>%s</p>" % escapar(renglon.strip()))
            secciones.append(("tema%d.xhtml" % numero, _envolver("".join(partes))))
        metadatos = Metadatos(titulo=sistema.titulo or camino.stem,
                              autor=sistema.copyright)
        log.info("Archivo de ayuda con %s leído",
                 _n("%d tema", "%d temas", len(secciones)) % len(secciones))
        return montar(secciones, metadatos, camino, opciones)


    def extraer_recurso(self, ruta, interna: str) -> bytes | None:
        """Devuelve una imagen del archivo de ayuda, para verla o describirla.

        Se vuelve a abrir el archivo en vez de guardarlas al analizar: son
        iconos de treinta píxeles y capturas de pantalla, no llegan a nada, y
        guardarlas todas por si acaso es memoria gastada en lo que casi nadie
        va a mirar.
        """
        if not interna.startswith("imagen") or not interna.endswith(".png"):
            return None
        try:
            numero = int(interna[len("imagen"):-4])
        except ValueError:
            return None
        try:
            return imagenes_de(Ayuda(Path(ruta).read_bytes())).get(numero)
        except Exception as error:
            log.debug("No se ha podido sacar %s del archivo de ayuda: %s",
                      interna, error)
            return None


def _envolver(cuerpo: str) -> bytes:
    return ("<?xml version=\"1.0\" encoding=\"utf-8\"?>"
            "<html xmlns=\"http://www.w3.org/1999/xhtml\"><head>"
            "<meta charset=\"utf-8\"/></head><body>%s</body></html>"
            % cuerpo).encode("utf-8")


registrar(AnalizadorHLP())
