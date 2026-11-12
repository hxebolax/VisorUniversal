# -*- coding: utf-8 -*-
"""Lectura de los libros MOBI y AZW3 de Kindle, los formatos anteriores al KFX.

Los dos van dentro de una **base de datos Palm**, que es un formato de los años
noventa: una cabecera, una lista de registros y los registros detrás.  Lo que
cambia es lo que se guarda dentro:

* **MOBI** (``.mobi``, ``.prc``, ``.azw``) guarda **un solo HTML enorme** con
  el libro entero, comprimido y partido en registros de 4 KB.  Las anclas no
  son nombres: son **posiciones de byte** dentro de ese HTML, y los enlaces
  apuntan a ellas con ``filepos``.
* **AZW3**, también llamado **KF8** (``.azw3``, ``.azw``), guarda XHTML de
  verdad, el mismo que llevaba el EPUB del que salió, pero **partido en dos
  mitades**: los «esqueletos» —la cabecera de cada archivo— y los
  «fragmentos» —su contenido—, que hay que volver a coser en el orden que dice
  su índice.

Los dos acaban en secciones XHTML, así que a partir de ahí el libro se recorre
igual que un EPUB.

La compresión
-------------

Hay tres:

* **Ninguna**, en libros pequeños.
* **PalmDOC**, un LZ77 sencillo con un truco propio para los espacios.
* **HUFF/CDIC**, un Huffman con diccionario que Amazon usa en los libros
  grandes.  Es la más enrevesada y está implementada entera, porque sin ella
  buena parte de los MOBI no se abren.

Sobre el DRM
------------

No se descifra nada.  Un libro cifrado se reconoce por su cabecera y se
rechaza diciéndolo.
"""

from __future__ import annotations

import re
import struct
from pathlib import Path

from nucleo.documento import ElementoIndice
from nucleo.idioma import _
from nucleo.registro import obtener_registro

log = obtener_registro(__name__)

#: Dónde dice la cabecera Palm cuántos registros trae el archivo.
CUENTA_DE_REGISTROS = 76

#: Dónde empieza la lista de registros, justo detrás de esa cuenta.  Cada
#: entrada ocupa ocho bytes: cuatro dicen dónde empieza el registro y los otros
#: cuatro son atributos y un identificador que aquí no hacen falta.
LISTA_DE_REGISTROS = 78

#: Tipos de compresión del texto.
SIN_COMPRIMIR = 1
PALMDOC = 2
HUFFMAN = 17480

#: Valores del campo de cifrado.  Cualquiera que no sea cero quiere decir que
#: el libro está protegido y no se puede leer.
SIN_CIFRAR = 0

#: Códigos de idioma de MOBI, que son los de Windows.  Solo se traducen los
#: que aparecen: para el resto vale el número, que no se enseña a nadie.
IDIOMAS = {
    9: "en", 4: "zh", 7: "de", 10: "es", 12: "fr", 16: "it", 22: "pt",
    25: "ru", 17: "ja", 19: "nl", 29: "sv", 8: "el", 21: "pl", 5: "cs",
    30: "tr", 1: "ar", 13: "he", 14: "hu", 20: "no", 6: "da", 11: "fi",
}

#: Dónde está cada dato dentro de la cabecera MOBI, contando desde el principio
#: del primer registro.  Se escriben con nombre porque un número suelto en
#: medio de un «unpack_from» no dice nada y equivocarse en uno se paga con el
#: libro entero leído del revés.
LARGO_CABECERA = 20
CODIFICACION = 28
VERSION_MOBI = 0x68
PRIMERA_IMAGEN = 0x6C
BANDERAS_COLA = 0xF2

#: Dónde dice la cabecera en qué registro empieza el índice del libro.
INDICE_NCX = 0xF4

#: Qué significa cada etiqueta de una entrada del índice.  Son las tres que
#: hacen falta: dónde empieza el capítulo, cómo se llama y de qué nivel es.
ETIQUETA_POSICION = 1
ETIQUETA_ROTULO = 3
ETIQUETA_NIVEL = 4

#: Qué metadato es cada número de registro EXTH.
EXTH = {
    100: "author",
    101: "publisher",
    103: "description",
    104: "isbn",
    106: "issue_date",
    108: "contributor",
    503: "title",
}


class ErrorMobi(ValueError):
    """El archivo no es un MOBI legible."""


# ---------------------------------------------------------------------------
# La base de datos Palm
# ---------------------------------------------------------------------------

def _registros(datos: bytes) -> list[bytes]:
    """Parte el archivo en los registros de la base de datos Palm.

    La lista de registros solo trae dónde empieza cada uno, así que el final
    de uno es el principio del siguiente y el del último es el final del
    archivo.
    """
    if len(datos) < LISTA_DE_REGISTROS:
        raise ErrorMobi(_("El archivo está incompleto."))
    cuantos = struct.unpack_from(">H", datos, CUENTA_DE_REGISTROS)[0]
    inicios = []
    for numero in range(cuantos):
        posicion = LISTA_DE_REGISTROS + numero * 8
        if posicion + 4 > len(datos):
            break
        inicios.append(struct.unpack_from(">L", datos, posicion)[0])
    if not inicios:
        raise ErrorMobi(_("El archivo no contiene ningún registro."))
    inicios.append(len(datos))
    salida = []
    for numero in range(len(inicios) - 1):
        principio = min(inicios[numero], len(datos))
        final = min(inicios[numero + 1], len(datos))
        salida.append(datos[principio:final] if final > principio else b"")
    return salida


# ---------------------------------------------------------------------------
# Las tres compresiones
# ---------------------------------------------------------------------------

def _descomprimir_palmdoc(datos: bytes) -> bytes:
    """Deshace la compresión PalmDOC, que es un LZ77 con un añadido.

    Cada byte se lee como una orden:

    * ``0x00``, y de ``0x09`` a ``0x7f``: el carácter tal cual.
    * De ``0x01`` a ``0x08``: copiar tantos bytes literales.
    * De ``0x80`` a ``0xbf``: dos bytes que dicen «vuelve tanto y copia tanto».
    * De ``0xc0`` a ``0xff``: un espacio y una letra, que es el añadido de
      PalmDOC sobre el LZ77 de siempre.
    """
    salida = bytearray()
    posicion = 0
    total = len(datos)
    while posicion < total:
        orden = datos[posicion]
        posicion += 1
        if orden == 0 or 9 <= orden <= 0x7F:
            salida.append(orden)
        elif orden <= 8:
            salida.extend(datos[posicion:posicion + orden])
            posicion += orden
        elif orden <= 0xBF:
            if posicion >= total:
                break
            pareja = (orden << 8) | datos[posicion]
            posicion += 1
            distancia = (pareja >> 3) & 0x07FF
            cuantos = (pareja & 7) + 3
            if not 0 < distancia <= len(salida):
                continue
            desde = len(salida) - distancia
            for indice in range(cuantos):
                salida.append(salida[desde + indice])
        else:
            salida.append(0x20)
            salida.append(orden ^ 0x80)
    return bytes(salida)


class _Huffman:
    """Descompresor HUFF/CDIC, la compresión de los MOBI grandes.

    Son dos piezas.  El registro ``HUFF`` trae **dos tablas de códigos**: una
    con los 256 comienzos posibles, para resolver de un vistazo los códigos
    cortos, y otra con el código menor y el mayor de cada longitud, para los
    largos.  Los registros ``CDIC`` traen el **diccionario**: los trozos de
    texto a los que llevan esos códigos.

    Se decodifica bit a bit sobre una ventana de 32 bits, que es lo que ocupa
    el código más largo.  Un trozo del diccionario puede estar a su vez
    comprimido, y entonces se entra en él y se sigue; cuando eso pasa, el
    resultado se guarda ya descomprimido en el diccionario, porque un trozo
    así se repite muchas veces y descomprimirlo cada vez es lo que separa
    abrir un libro en un segundo de tardar un minuto.
    """

    def __init__(self, huff: bytes, cdics: list[bytes]) -> None:
        if huff[0:4] != b"HUFF" or len(huff) < 24:
            raise ErrorMobi(_("La tabla de compresión del libro está dañada."))
        desplazamiento_1, desplazamiento_2 = struct.unpack_from(">LL", huff, 8)
        self._directa = tuple(
            self._entrada_directa(valor)
            for valor in struct.unpack_from(">256L", huff, desplazamiento_1))
        segunda = struct.unpack_from(">64L", huff, desplazamiento_2)
        self._minimo = tuple(
            codigo << (32 - largo)
            for largo, codigo in enumerate((0,) + segunda[0::2]))
        self._maximo = tuple(
            ((codigo + 1) << (32 - largo)) - 1
            for largo, codigo in enumerate((0,) + segunda[1::2]))
        self._diccionario: list = []
        for cdic in cdics:
            self._cargar_diccionario(cdic)
        if not self._diccionario:
            raise ErrorMobi(_("El diccionario de compresión del libro está vacío."))

    @staticmethod
    def _entrada_directa(valor: int) -> tuple[int, bool, int]:
        """Traduce una entrada de la tabla rápida: longitud, si acaba y tope."""
        largo = valor & 0x1F
        acaba = bool(valor & 0x80)
        mayor = valor >> 8
        if largo:
            mayor = ((mayor + 1) << (32 - largo)) - 1
        return largo, acaba, mayor

    def _cargar_diccionario(self, cdic: bytes) -> None:
        """Añade al diccionario los trozos de texto de un registro CDIC."""
        if cdic[0:4] != b"CDIC" or len(cdic) < 16:
            return
        frases, bits = struct.unpack_from(">LL", cdic, 8)
        cuantos = min(1 << bits, frases - len(self._diccionario))
        if cuantos <= 0:
            return
        try:
            posiciones = struct.unpack_from(">%dH" % cuantos, cdic, 16)
        except struct.error:
            return
        for posicion in posiciones:
            if 16 + posicion + 2 > len(cdic):
                continue
            marca = struct.unpack_from(">H", cdic, 16 + posicion)[0]
            largo = marca & 0x7FFF
            trozo = cdic[18 + posicion:18 + posicion + largo]
            # El bit alto dice que el trozo ya está en claro.
            self._diccionario.append((trozo, bool(marca & 0x8000)))

    def descomprimir(self, datos: bytes, profundidad: int = 0) -> bytes:
        """Devuelve el texto de un registro comprimido."""
        if profundidad > 16:
            return b""
        quedan = len(datos) * 8
        relleno = datos + b"\0" * 8
        posicion = 0
        ventana = struct.unpack_from(">Q", relleno, posicion)[0]
        bits = 32
        piezas: list[bytes] = []
        while True:
            if bits <= 0:
                posicion += 4
                if posicion + 8 > len(relleno):
                    break
                ventana = struct.unpack_from(">Q", relleno, posicion)[0]
                bits += 32
            codigo = (ventana >> bits) & 0xFFFFFFFF
            largo, acaba, mayor = self._directa[codigo >> 24]
            if not largo:
                break
            if not acaba:
                # Código largo: se busca su longitud en la segunda tabla.
                while largo < len(self._minimo) and codigo < self._minimo[largo]:
                    largo += 1
                if largo >= len(self._maximo):
                    break
                mayor = self._maximo[largo]
            bits -= largo
            quedan -= largo
            if quedan < 0:
                break
            entrada = (mayor - codigo) >> (32 - largo)
            if not 0 <= entrada < len(self._diccionario):
                break
            guardado = self._diccionario[entrada]
            if guardado is None:
                break                    # trozo que se llama a sí mismo
            trozo, en_claro = guardado
            if not en_claro:
                self._diccionario[entrada] = None
                trozo = self.descomprimir(trozo, profundidad + 1)
                self._diccionario[entrada] = (trozo, True)
            piezas.append(trozo)
        return b"".join(piezas)


# ---------------------------------------------------------------------------
# El libro
# ---------------------------------------------------------------------------

class LibroMobi:
    """Un MOBI o un AZW3 ya abierto, listo para dar sus secciones en XHTML."""

    def __init__(self, ruta) -> None:
        self.ruta = Path(ruta)
        self.metadatos: dict[str, object] = {}
        #: «MOBI» o «AZW3», para el registro.
        self.formato = "MOBI"
        self._registros = _registros(self.ruta.read_bytes())
        self._texto = b""
        self._primera_imagen = 0
        self._registro_ncx = 0
        self._indice: list | None = None
        self._leer()

    # -- cabeceras ------------------------------------------------------------

    def _leer(self) -> None:
        """Lee la cabecera del libro y descomprime su texto."""
        cabecera = self._registros[0]
        if len(cabecera) < 16:
            raise ErrorMobi(_("El libro no trae cabecera."))
        compresion, _relleno, largo_texto, cuantos, tamano, cifrado = \
            struct.unpack_from(">HHLHHH", cabecera, 0)
        if cifrado != SIN_CIFRAR:
            raise ErrorMobi(_("Este libro de Kindle está protegido con DRM y no se "
                              "puede leer."))
        version = 6
        codificacion = "cp1252"
        self._cola = 0
        if cabecera[16:20] == b"MOBI" and len(cabecera) >= 0x70:
            largo_cabecera = struct.unpack_from(">L", cabecera, LARGO_CABECERA)[0]
            if struct.unpack_from(">L", cabecera, CODIFICACION)[0] == 65001:
                codificacion = "utf-8"
            version = struct.unpack_from(">L", cabecera, VERSION_MOBI)[0]
            self._primera_imagen = struct.unpack_from(">L", cabecera, PRIMERA_IMAGEN)[0]
            if 0xE4 <= largo_cabecera <= 500 and len(cabecera) >= BANDERAS_COLA + 2:
                self._cola = struct.unpack_from(">H", cabecera, BANDERAS_COLA)[0]
            if len(cabecera) >= INDICE_NCX + 4:
                indice = struct.unpack_from(">L", cabecera, INDICE_NCX)[0]
                # 0xFFFFFFFF quiere decir «no hay».
                self._registro_ncx = indice if indice < 0xFFFFFFFF else 0
            self._leer_titulo(cabecera, codificacion)
            self._leer_exth(cabecera, 16 + largo_cabecera, codificacion)
            self._leer_idioma(cabecera)
        self.formato = "AZW3" if version >= 8 else "MOBI"
        self._codificacion = codificacion
        self._texto = self._descomprimir(compresion, cuantos, largo_texto)

    def _leer_titulo(self, cabecera: bytes, codificacion: str) -> None:
        """Saca el título completo, que va al final de la cabecera."""
        try:
            desde, largo = struct.unpack_from(">LL", cabecera, 84)
        except struct.error:
            return
        crudo = cabecera[desde:desde + largo]
        if crudo:
            self.metadatos["title"] = crudo.decode(codificacion, "replace").strip()

    def _leer_idioma(self, cabecera: bytes) -> None:
        """Traduce el código de idioma de Windows al de dos letras."""
        try:
            codigo = struct.unpack_from(">L", cabecera, 92)[0]
        except struct.error:
            return
        idioma = IDIOMAS.get(codigo & 0xFF)
        if idioma:
            self.metadatos["language"] = idioma

    def _leer_exth(self, cabecera: bytes, desde: int, codificacion: str) -> None:
        """Lee los metadatos del bloque EXTH, si lo hay.

        Un libro puede traer varios autores, cada uno en su registro, así que
        se van juntando en vez de quedarse con el último.
        """
        if cabecera[desde:desde + 4] != b"EXTH":
            return
        try:
            _largo, cuantos = struct.unpack_from(">LL", cabecera, desde + 4)
        except struct.error:
            return
        posicion = desde + 12
        autores: list[str] = []
        for _numero in range(min(cuantos, 512)):
            try:
                clase, largo = struct.unpack_from(">LL", cabecera, posicion)
            except struct.error:
                break
            if largo < 8:
                break
            crudo = cabecera[posicion + 8:posicion + largo]
            posicion += largo
            nombre = EXTH.get(clase)
            if not nombre:
                continue
            valor = crudo.decode(codificacion, "replace").strip()
            if not valor:
                continue
            if nombre == "author":
                autores.append(valor)
            else:
                self.metadatos.setdefault(nombre, valor)
        if autores:
            self.metadatos["authors"] = autores

    # -- texto ----------------------------------------------------------------

    def _descomprimir(self, compresion: int, cuantos: int, largo: int) -> bytes:
        """Junta y descomprime los registros de texto del libro."""
        registros = self._registros[1:1 + max(0, cuantos)]
        limpios = [_sin_cola(registro, self._cola) for registro in registros]
        if compresion == HUFFMAN:
            descompresor = self._huffman()
            piezas = [descompresor.descomprimir(r) for r in limpios]
        elif compresion == PALMDOC:
            piezas = [_descomprimir_palmdoc(r) for r in limpios]
        else:
            piezas = limpios
        texto = b"".join(piezas)
        return texto[:largo] if 0 < largo <= len(texto) else texto

    def _huffman(self) -> "_Huffman":
        """Monta el descompresor con los registros HUFF y CDIC del libro."""
        for registro in self._registros:
            if registro[:4] == b"HUFF":
                cdics = [r for r in self._registros if r[:4] == b"CDIC"]
                return _Huffman(registro, cdics)
        raise ErrorMobi(_("El libro dice estar comprimido de una forma cuya tabla "
                          "no trae."))

    # -- secciones ------------------------------------------------------------

    def secciones(self) -> list[tuple[str, bytes]]:
        """Devuelve el libro partido en secciones XHTML.

        En un AZW3 el texto es la sucesión de los archivos XHTML que tenía el
        libro original, uno detrás de otro, así que se parte por donde empieza
        cada uno.  En un MOBI es **un solo archivo**, y lo que hace las veces
        de capítulo son las marcas de salto de página que dejó el generador.
        """
        texto = self._marcar_indice(self._texto)
        if not texto.strip():
            return []
        if self.formato == "AZW3":
            trozos = _partir_por_html(texto)
        else:
            trozos = _partir_por_saltos(texto)
        salida = []
        for numero, trozo in enumerate(trozos, start=1):
            if not trozo.strip():
                continue
            if self.formato == "AZW3":
                trozo = _coser_fragmentos(trozo)
            salida.append(("parte-%d" % numero, _preparar(trozo, self._codificacion)))
        return salida

    def _marcar_indice(self, texto: bytes) -> bytes:
        """Deja un ancla en el texto por cada entrada del índice.

        El índice del libro apunta a **posiciones de byte**, y el programa
        trabaja con posiciones de carácter del texto ya convertido, que no son
        las mismas.  El puente es poner un ancla de verdad en cada sitio antes
        de convertir: al convertir, el ancla se apunta con su posición, y así
        la entrada del índice sabe a dónde lleva.

        Se insertan de atrás hacia delante para que cada inserción no corra las
        posiciones de las que faltan.
        """
        entradas = self.indice()
        if not entradas:
            return texto
        piezas = []
        anterior = len(texto)
        for _rotulo, posicion, _nivel in sorted(entradas, key=lambda e: -e[1]):
            if not 0 <= posicion <= anterior:
                continue
            piezas.append(texto[posicion:anterior])
            piezas.append(('<a id="%s"></a>' % ancla_de(posicion)).encode("ascii"))
            anterior = posicion
        piezas.append(texto[:anterior])
        return b"".join(reversed(piezas))

    # -- índice e imágenes ----------------------------------------------------

    def indice(self) -> list[tuple[str, int, int]]:
        """El índice del libro: ``(rótulo, posición de byte, nivel)``.

        Hace falta porque **un MOBI no marca sus títulos**.  Lo que en el EPUB
        era un ``<h1>`` sale del generador de Amazon como un párrafo con letra
        más grande, así que en el texto no hay nada que distinguir.  Los
        capítulos están, pero en otro sitio: en un índice propio, guardado en
        registros aparte con su propio formato.  Sin leerlo, un MOBI se abre
        sin un solo encabezado y no se puede recorrer.
        """
        if self._indice is not None:
            return self._indice
        self._indice = []
        try:
            self._indice = _leer_indice(self._registros, self._registro_ncx,
                                        self._codificacion)
        except Exception as error:
            log.debug("No se ha podido leer el índice del MOBI: %s", error)
        return self._indice

    def recurso(self, referencia: str) -> bytes | None:
        """Devuelve una imagen del libro por su número de registro."""
        numero = _numero_de_imagen(referencia)
        if numero is None or not self._primera_imagen:
            return None
        indice = self._primera_imagen + numero - 1
        if not 0 <= indice < len(self._registros):
            return None
        datos = self._registros[indice]
        return datos if datos[:2] in (b"\xff\xd8", b"\x89P", b"GI", b"BM") else None


# ---------------------------------------------------------------------------
# El índice interno
# ---------------------------------------------------------------------------

def _leer_indice(registros: list, primero: int, codificacion: str) -> list:
    """Lee el índice del libro y devuelve ``(rótulo, posición, nivel)``.

    El índice ocupa varios registros seguidos.  El primero es la cabecera:
    dice cuántos registros de entradas vienen detrás, cuántos registros de
    rótulos y dónde está la tabla ``TAGX``, que es la que explica **cómo está
    escrita cada entrada**.  Los rótulos van aparte, en los registros del
    final, y cada entrada apunta al suyo por su posición.
    """
    if not 0 < primero < len(registros):
        return []
    cabecera = registros[primero]
    if cabecera[:4] != b"INDX":
        return []
    cuantos = struct.unpack_from(">L", cabecera, 24)[0]
    rotulos_cuantos = struct.unpack_from(">L", cabecera, 52)[0]
    inicio_tagx = struct.unpack_from(">L", cabecera, 164)[0]
    if cabecera[inicio_tagx:inicio_tagx + 4] != b"TAGX":
        encontrado = cabecera.find(b"TAGX", 56)
        if encontrado < 0:
            return []
        inicio_tagx = encontrado
    mandos, etiquetas = _leer_tagx(cabecera[inicio_tagx:])
    rotulos = {}
    if rotulos_cuantos > 0:
        desde = primero + cuantos + 1
        rotulos = _leer_rotulos(registros[desde:desde + rotulos_cuantos], codificacion)
    entradas = []
    for numero in range(primero + 1, primero + 1 + cuantos):
        if numero >= len(registros):
            break
        entradas.extend(_leer_registro_indice(registros[numero], mandos, etiquetas,
                                              rotulos, codificacion))
    entradas.sort(key=lambda entrada: entrada[1])
    return entradas


def _leer_tagx(datos: bytes) -> tuple[int, list]:
    """Lee la tabla que explica cómo está escrita cada entrada del índice."""
    primera, mandos = struct.unpack_from(">LL", datos, 4)
    etiquetas = []
    for posicion in range(12, min(primera, len(datos)), 4):
        trozo = datos[posicion:posicion + 4]
        if len(trozo) < 4:
            break
        etiquetas.append((trozo[0], trozo[1], trozo[2], trozo[3]))
    return mandos, etiquetas


def _leer_rotulos(registros: list, codificacion: str) -> dict:
    """Lee los rótulos del índice, que van en sus propios registros.

    Cada rótulo se guarda como «cuánto mide y qué dice», uno detrás de otro, y
    las entradas lo citan por la posición donde empieza.  Los registros se
    numeran de 64 KB en 64 KB, que es lo que da la posición global.
    """
    salida = {}
    desplazamiento = 0
    for registro in registros:
        posicion = 0
        while posicion < len(registro):
            largo, consumidos = _numero_variable(registro, posicion)
            if largo <= 0:
                posicion += max(consumidos, 1)
                continue
            crudo = registro[posicion + consumidos:posicion + consumidos + largo]
            salida[posicion + desplazamiento] = crudo.decode(codificacion, "replace")
            posicion += consumidos + largo
        desplazamiento += 0x10000
    return salida


def _leer_registro_indice(datos: bytes, mandos: int, etiquetas: list,
                          rotulos: dict, codificacion: str) -> list:
    """Saca las entradas de un registro del índice."""
    if datos[:4] != b"INDX":
        return []
    inicio_tabla = struct.unpack_from(">L", datos, 20)[0]
    cuantas = struct.unpack_from(">L", datos, 24)[0]
    if datos[inicio_tabla:inicio_tabla + 4] != b"IDXT":
        return []
    posiciones = []
    for numero in range(cuantas):
        sitio = inicio_tabla + 4 + numero * 2
        if sitio + 2 > len(datos):
            break
        posiciones.append(struct.unpack_from(">H", datos, sitio)[0])
    posiciones.append(inicio_tabla)
    salida = []
    for numero in range(len(posiciones) - 1):
        trozo = datos[posiciones[numero]:posiciones[numero + 1]]
        if not trozo:
            continue
        largo_nombre = trozo[0]
        cuerpo = trozo[1 + largo_nombre:]
        valores = _valores_de_entrada(cuerpo, mandos, etiquetas)
        posicion = valores.get(ETIQUETA_POSICION)
        rotulo = valores.get(ETIQUETA_ROTULO)
        if not posicion or rotulo is None:
            continue
        texto = rotulos.get(rotulo[0], "") if rotulo else ""
        nivel = (valores.get(ETIQUETA_NIVEL) or [0])[0] + 1
        if texto.strip():
            salida.append((texto.strip(), posicion[0], min(nivel, 6)))
    del codificacion
    return salida


def _valores_de_entrada(datos: bytes, mandos: int, etiquetas: list) -> dict:
    """Descifra una entrada del índice según la tabla de etiquetas.

    Cada entrada empieza por unos «bytes de mando» que dicen qué etiquetas
    trae; detrás van los valores, todos como números de longitud variable.  Es
    un formato apretado y sin margen: leer un valor de más descoloca todos los
    siguientes, así que se sigue la tabla al pie de la letra.
    """
    presentes = []
    banderas = list(datos[:mandos])
    cuerpo = datos[mandos:]
    for etiqueta, cuantos_por_valor, mascara, fin in etiquetas:
        if fin == 0x01:
            banderas = banderas[1:]
            continue
        if not banderas:
            break
        valor = banderas[0] & mascara
        if not valor:
            continue
        if valor == mascara:
            if bin(mascara).count("1") > 1:
                # Con la máscara entera puesta, lo que sigue es cuántos bytes
                # ocupan los valores, no cuántos valores hay.
                bytes_de_valores, consumidos = _numero_variable(cuerpo, 0)
                cuerpo = cuerpo[consumidos:]
                presentes.append((etiqueta, None, bytes_de_valores, cuantos_por_valor))
                continue
            presentes.append((etiqueta, 1, None, cuantos_por_valor))
            continue
        mascara_movil = mascara
        while mascara_movil & 1 == 0:
            mascara_movil >>= 1
            valor >>= 1
        presentes.append((etiqueta, valor, None, cuantos_por_valor))
    salida = {}
    for etiqueta, cuantos, bytes_de_valores, por_valor in presentes:
        valores = []
        if cuantos is not None:
            for _vez in range(cuantos * max(1, por_valor)):
                numero, consumidos = _numero_variable(cuerpo, 0)
                cuerpo = cuerpo[consumidos:]
                valores.append(numero)
        else:
            gastados = 0
            while gastados < (bytes_de_valores or 0) and cuerpo:
                numero, consumidos = _numero_variable(cuerpo, 0)
                cuerpo = cuerpo[consumidos:]
                gastados += consumidos
                valores.append(numero)
        salida[etiqueta] = valores
    return salida


def _numero_variable(datos: bytes, pos: int) -> tuple[int, int]:
    """Número de longitud variable: siete bits por byte, el último marcado."""
    numero = 0
    consumidos = 0
    limite = min(len(datos), pos + 8)
    while pos + consumidos < limite:
        byte = datos[pos + consumidos]
        consumidos += 1
        numero = (numero << 7) | (byte & 0x7F)
        if byte & 0x80:
            break
    return numero, max(consumidos, 1)


def ancla_de(posicion: int) -> str:
    """Nombre del ancla que corresponde a una posición de byte del libro.

    Es el mismo nombre que se le pone a los destinos de los enlaces
    ``filepos``, así que un enlace del texto y una entrada del índice que
    apunten al mismo sitio acaban en el mismo ancla.
    """
    return "filepos%d" % posicion


def resolver_ruta(seccion: str, referencia: str) -> str:
    """Deja las referencias del libro tal como están.

    Un MOBI no tiene rutas: sus imágenes van por número de registro y sus
    enlaces por posición de byte, así que no hay nada que resolver.
    """
    del seccion
    return referencia


# ---------------------------------------------------------------------------
# Auxiliares
# ---------------------------------------------------------------------------

def _sin_cola(registro: bytes, banderas: int) -> bytes:
    """Quita del registro los datos de cola, que no son texto.

    Detrás del texto de cada registro, MOBI guarda cosas suyas: las posiciones
    de las imágenes que caen dentro, el índice de búsqueda, los saltos de
    línea que se pueden partir.  **Cuántas de esas cosas hay lo dicen las
    banderas de la cabecera**, un bit por cada una, y cada una guarda su propio
    tamaño al final, escrito al revés: siete bits por byte, del último byte
    hacia atrás, hasta encontrar uno con el bit alto puesto.

    Sin quitarlas, esos bytes se leen como si fueran texto y el libro sale con
    basura entre párrafo y párrafo; quitando de más, se pierde texto.
    """
    if not registro:
        return registro
    for bit in range(15, 0, -1):
        if banderas & (1 << bit):
            registro = registro[:len(registro) - _tamano_de_cola(registro)]
            if not registro:
                return registro
    if banderas & 1:
        # El último bit es el de los caracteres partidos entre dos registros:
        # su cuenta va en los dos bits bajos del último byte.
        sobran = (registro[-1] & 0x3) + 1
        registro = registro[:-sobran] if sobran <= len(registro) else b""
    return registro


def _tamano_de_cola(registro: bytes) -> int:
    """Lee, del final hacia atrás, cuánto ocupa el último dato de cola."""
    tamano = 0
    desplazamiento = 0
    posicion = len(registro)
    while posicion > 0 and desplazamiento < 28:
        byte = registro[posicion - 1]
        tamano |= (byte & 0x7F) << desplazamiento
        desplazamiento += 7
        posicion -= 1
        if byte & 0x80:
            break
    return min(tamano, len(registro))


def _partir_por_html(texto: bytes) -> list[bytes]:
    """Parte el texto de un AZW3 por donde empieza cada archivo XHTML."""
    cortes = [coincidencia.start()
              for coincidencia in re.finditer(rb"<html[ >]", texto, re.IGNORECASE)]
    if not cortes:
        return [texto]
    if cortes[0] > 0:
        cortes.insert(0, 0)
    cortes.append(len(texto))
    return [texto[cortes[n]:cortes[n + 1]] for n in range(len(cortes) - 1)]


def _partir_por_saltos(texto: bytes) -> list[bytes]:
    """Parte el texto de un MOBI por sus marcas de salto de página."""
    trozos = re.split(rb"<mbp:pagebreak[^>]*>", texto, flags=re.IGNORECASE)
    return trozos if len(trozos) > 1 else [texto]


def _coser_fragmentos(trozo: bytes) -> bytes:
    """Mete dentro del cuerpo los fragmentos que van detrás de su esqueleto.

    Un AZW3 no guarda cada archivo entero: guarda por un lado el **esqueleto**
    —``<html><head>...</head><body class="..."></body></html>``, con el cuerpo
    vacío— y por otro los **fragmentos** con su contenido, que van justo
    detrás.  Tal cual se leen, el cuerpo está vacío y los párrafos quedan
    fuera del ``</html>``, así que el archivo entero se lee como si no tuviera
    texto.

    Se vuelven a coser por donde estaban: todo lo que venga después del cierre
    del cuerpo se mete dentro de él, que es el sitio del que salió.
    """
    minuscula = trozo.lower()
    cierre = minuscula.rfind(b"</body>")
    if cierre < 0:
        return trozo
    cola = trozo[cierre + len(b"</body>"):]
    # Lo que queda detrás son los fragmentos y el cierre del documento.
    fragmentos = re.sub(rb"</\s*html\s*>", b"", cola, flags=re.IGNORECASE).strip()
    if not fragmentos or not fragmentos.startswith(b"<"):
        return trozo
    # Detrás del último archivo van los «flujos» del libro: la hoja de estilo,
    # los dibujos vectoriales.  No son marcado y van pegados a los fragmentos,
    # así que se corta por donde acaba la última etiqueta; sin eso, la hoja de
    # estilo entera se leía como un párrafo al final del libro.
    ultima = fragmentos.rfind(b">")
    if ultima >= 0:
        fragmentos = fragmentos[:ultima + 1]
    return trozo[:cierre] + fragmentos + b"</body></html>"


def _preparar(trozo: bytes, codificacion: str) -> bytes:
    """Deja un trozo listo para el conversor: XHTML bien formado y en UTF-8.

    Se traducen las tres cosas propias de MOBI que el conversor no conoce: el
    salto de página, el ancla por posición de byte y el enlace a esa posición.
    Traducirlas aquí y no en el conversor es lo que mantiene el conversor
    limpio de formatos concretos.
    """
    texto = trozo.decode(codificacion, "replace")
    texto = re.sub(r"<mbp:pagebreak[^>]*>", "<hr/>", texto, flags=re.IGNORECASE)
    texto = re.sub(r"<\s*/?\s*mbp:[a-z]+[^>]*>", "", texto, flags=re.IGNORECASE)
    # «filepos» es el ancla de MOBI: una posición de byte dentro del libro.
    texto = re.sub(r'<a([^>]*?)filepos=["\']?0*(\d+)["\']?',
                   r'<a\1href="#filepos\2"', texto, flags=re.IGNORECASE)
    texto = re.sub(r'(<[a-z]+[^>]*?)\bid=["\']?filepos0*(\d+)["\']?',
                   r'\1id="filepos\2"', texto, flags=re.IGNORECASE)
    if "<body" not in texto.lower():
        texto = "<body>%s</body>" % texto
    if "<html" not in texto.lower():
        texto = "<html>%s</html>" % texto
    # El trozo puede traer ya su propia declaración XML —los archivos de un
    # AZW3 la llevan—, y dos declaraciones seguidas no son XML válido: el
    # analizador rechaza el archivo entero y el libro sale vacío.
    texto = re.sub(r"^\s*<\?xml[^>]*\?>\s*", "", texto)
    return ('<?xml version="1.0" encoding="utf-8"?>\n' + texto).encode("utf-8")


def _numero_de_imagen(referencia: str) -> int | None:
    """Saca de una referencia el número de registro de la imagen.

    En un MOBI las imágenes se citan como ``recindex="00042"``, que es el
    número de la imagen contando desde la primera.
    """
    hallado = re.search(r"(\d+)", referencia or "")
    if not hallado:
        return None
    try:
        return int(hallado.group(1))
    except ValueError:
        return None
