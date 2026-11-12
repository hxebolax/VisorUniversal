# -*- coding: utf-8 -*-
"""Lectura de libros DAISY de cualquier versión y de cualquier tipo.

DAISY es **el** formato de las bibliotecas para personas ciegas: la ONCE,
Bookshare, la National Library Service de la Biblioteca del Congreso y las
bibliotecas equivalentes de medio mundo prestan en DAISY.  Y la mayor parte de
lo que prestan no es texto: es **una grabación humana**, que para muchos
lectores es justo lo que quieren —una voz de verdad leyendo el libro— y no un
sucedáneo de la síntesis.

Un libro DAISY no es un archivo, es una **carpeta** (o un ZIP con esa carpeta
dentro).  Hay dos generaciones y seis tipos, y este módulo entiende todos.

Las dos generaciones
--------------------

**DAISY 2.02** se navega con ``ncc.html`` (*Navigation Control Centre*): un
XHTML cuyo cuerpo son solo encabezados ``<h1>``…``<h6>`` y ``<span>`` de número
de página, cada uno enlazando a un punto de un archivo SMIL.  Los SMIL son
SMIL 1.0 y escriben los recortes de audio como ``clip-begin="npt=1.709s"``.

**DAISY 3** (ANSI/NISO Z39.86) se navega con un ``.ncx`` (``navMap`` de
``navPoint``, más un ``pageList``), tiene un ``.opf`` con el orden de lectura, y
sus SMIL son SMIL 2.0, donde los recortes se escriben ``clipBegin="0:00:01.709"``.
El texto, cuando lo hay, va en un XML propio, DTBook.

Los seis tipos
--------------

La norma los llama por su ``multimediaType``, y la diferencia importa mucho:

===============  ===========================================================
``audioOnly``    Solo la grabación, sin apenas estructura.
``audioNcc``     Grabación con navegación: el índice y los números de página
                 existen, el texto del libro no.
``audioPartText``Grabación con parte del texto.
``audioFullText``Grabación **y** texto completo, sincronizados frase a frase.
``textPartAudio``Texto con algo de audio.
``textNcc``      Solo texto, sin grabación.
===============  ===========================================================

El analizador de texto que había solo servía para los dos últimos, y ante los
otros cuatro decía «este libro no trae texto» y se rendía.  Es justo al revés
de lo que hace falta: los de audio son la mayoría de lo que prestan las
bibliotecas.

Qué se saca de aquí
-------------------

Un :class:`LibroDaisy` con dos cosas atadas entre sí:

* las **frases** (:class:`Frase`), que son los ``<par>`` del SMIL en orden de
  lectura: un trozo de audio y, si el libro lo trae, el texto que le
  corresponde;
* la **navegación** (:class:`Punto`), es decir el índice y las páginas, cada
  uno apuntando a la frase donde empieza.

Con eso, el resto del programa puede hacer las dos cosas a la vez: enseñar el
libro como texto —aunque sea solo el índice— y reproducir la grabación
siguiendo el cursor.

Este módulo no toca ni la interfaz ni el audio: solo lee.
"""

from __future__ import annotations

import posixpath
import re
import zipfile
from pathlib import Path
from typing import NamedTuple

from nucleo.idioma import _
from nucleo.registro import obtener_registro, registrar_excepcion

log = obtener_registro(__name__)

#: Nombre del archivo de navegación de DAISY 2.02.  La norma lo fija en
#: minúsculas, pero hay libros por ahí con «NCC.HTML»: se compara en minúsculas.
NCC = "ncc.html"

#: Extensiones de audio que se admiten.  BASS abre todas estas y más; la lista
#: sirve para reconocer los archivos, no para limitar lo que suena.
AUDIO = (".mp3", ".mp2", ".wav", ".ogg", ".m4a", ".mp4", ".aac", ".wma",
         ".flac", ".opus", ".amr", ".3gp")

#: Los seis tipos de la norma, con lo que significan para el lector.
TIPOS = ("audioOnly", "audioNcc", "audioPartText", "audioFullText",
         "textPartAudio", "textNcc")

#: Clases de encabezado del NCC que no son estructura del libro sino aviso de
#: producción.  Se leen igual, pero conviene saber cuáles son.
_CLASES_PAGINA = ("page-normal", "page-front", "page-special")

#: Declaración de codificación en el prólogo XML o en una etiqueta ``meta``.
_CHARSET = re.compile(
    rb"""(?:encoding|charset)\s*=\s*["']?\s*([A-Za-z0-9_.:+-]+)""", re.IGNORECASE)

#: Un número con decimales opcionales y, quizá, una unidad detrás.
_MEDIDA = re.compile(r"^(\d+(?:\.\d+)?)\s*(ms|s|min|h)?$", re.IGNORECASE)

#: Cuántos segundos vale cada unidad de las que admite SMIL.
_UNIDADES = {"ms": 0.001, "s": 1.0, "min": 60.0, "h": 3600.0}


def tiempo(valor: str | None) -> float | None:
    """Convierte un valor de reloj de SMIL a segundos.

    Hay que aceptar todas estas formas, porque todas aparecen en libros reales:
    ``npt=1.709s`` (DAISY 2.02), ``0:00:01.709`` y ``00:01.709`` (DAISY 3),
    ``1.709``, ``250ms``, ``3min``, ``1h``.

    La separación por dos puntos se cuenta **de derecha a izquierda**, que es lo
    que dice la norma y lo que hace que ``01:30`` sea minuto y medio y no una
    hora y media.  Escrito con grupos opcionales de una expresión regular sale
    justo al revés, porque el primer grupo se queda con lo que encuentra.

    :return: Los segundos, o ``None`` si no hay valor o no se entiende.
    """
    if not valor:
        return None
    limpio = valor.strip()
    if limpio[:4].lower() == "npt=":
        limpio = limpio[4:].strip()
    if not limpio:
        return None

    if ":" in limpio:
        partes = limpio.split(":")
        if len(partes) > 3:
            return None
        total = 0.0
        for escala, parte in zip((1.0, 60.0, 3600.0), reversed(partes)):
            encaje = _MEDIDA.match(parte.strip())
            if encaje is None or encaje.group(2):
                return None      # dentro de un reloj no caben unidades
            total += float(encaje.group(1)) * escala
        return total

    encaje = _MEDIDA.match(limpio)
    if encaje is None:
        return None
    return float(encaje.group(1)) * _UNIDADES[(encaje.group(2) or "s").lower()]


def descodificar(datos: bytes) -> str:
    """Convierte el documento a texto, respetando la codificación que declara.

    Hay dos motivos para no dejarle esto a lxml, y los dos se ven en el mismo
    libro.

    El primero es la **codificación**.  Los libros DAISY llevan veinte años
    circulando y casi todos vienen en ``windows-1252`` o ``iso-8859-1``,
    declarado en el prólogo XML.  Si se le pasan los bytes tal cual, lxml los
    reinterpreta a su manera: ante un 0xC9 —una «É»— lo toma por el arranque de
    una secuencia UTF-8 y lo «repara» en dos caracteres, con lo que el autor de
    *El principito* pasa a llamarse «SAINT-EXUPÃ‰RY».

    El segundo es más serio: sobre estos NCC —XHTML con espacio de nombres y
    DOCTYPE externo— el analizador de HTML de lxml **se atasca a los pocos
    elementos** cuando se le dan bytes, y devuelve dos encabezados de los
    treinta y uno que hay.  Con una cadena ya descodificada los lee todos.
    """
    if datos.startswith(b"\xef\xbb\xbf"):
        datos = datos[3:]
    elif datos.startswith((b"\xff\xfe", b"\xfe\xff")):
        return _sin_prologo(datos.decode("utf-16"))
    encaje = _CHARSET.search(datos[:2048])
    declarada = encaje.group(1).decode("ascii", "ignore").lower() if encaje else ""
    for codificacion in ([declarada] if declarada else []) + ["utf-8", "cp1252", "latin-1"]:
        try:
            return _sin_prologo(datos.decode(codificacion))
        except (UnicodeDecodeError, LookupError):
            continue
    return _sin_prologo(datos.decode("utf-8", "replace"))


def _sin_prologo(texto: str) -> str:
    """Quita la declaración ``<?xml ... encoding=...?>``.

    Hace falta porque lxml rechaza una cadena que declare su codificación: ya
    no queda nada que descodificar, y la declaración solo puede mentir.
    """
    return re.sub(r"^\s*<\?xml[^>]*\?>", "", texto, count=1).lstrip()


def _nombre(elemento) -> str:
    """Nombre de la etiqueta sin su espacio de nombres, en minúsculas."""
    etiqueta = elemento.tag
    if not isinstance(etiqueta, str):
        return ""
    return etiqueta.rsplit("}", 1)[-1].lower()


def _texto_de(elemento) -> str:
    """Todo el texto que hay dentro de un elemento, con los espacios apretados."""
    return " ".join("".join(elemento.itertext()).split())


class Recorte(NamedTuple):
    """Un trozo de un archivo de audio.

    :param archivo: Ruta del audio dentro del libro.
    :param inicio: Segundo en el que empieza.
    :param fin: Segundo en el que acaba, o ``None`` hasta el final del archivo.
    """

    archivo: str
    inicio: float
    fin: float | None

    @property
    def duracion(self) -> float:
        """Lo que dura el recorte, o 0 si no se sabe dónde acaba."""
        if self.fin is None:
            return 0.0
        return max(0.0, self.fin - self.inicio)


class Frase(NamedTuple):
    """Un ``<par>`` del SMIL: la unidad mínima de lectura de un libro DAISY.

    Es lo que se oye de una vez y lo que se resalta de una vez.  Un libro de
    solo audio tiene frases sin ``texto``; uno de solo texto, frases sin
    ``recortes``; el caso bueno —``audioFullText``— tiene las dos cosas y por
    eso se puede seguir la grabación palabra por palabra.

    :param recortes: Trozos de audio que suenan, en orden.
    :param texto: Referencia al texto, ``archivo.html#identificador``.
    :param smil: Archivo SMIL del que sale.
    :param identificador: ``id`` del ``<par>``, para los enlaces del índice.
    """

    recortes: tuple[Recorte, ...]
    texto: str
    smil: str
    identificador: str

    @property
    def duracion(self) -> float:
        """Lo que dura la frase entera."""
        return sum(recorte.duracion for recorte in self.recortes)


class Punto(NamedTuple):
    """Un sitio al que se puede saltar: un título del índice o una página.

    :param titulo: Lo que se lee en voz alta al llegar.
    :param nivel: Profundidad en el índice, de 1 a 6.  Las páginas llevan 0.
    :param frase: Índice de la frase donde empieza.
    :param clase: Qué es: ``titulo``, ``pagina``, ``nota``…
    """

    titulo: str
    nivel: int
    frase: int
    clase: str


class LibroDaisy:
    """Un libro DAISY ya leído: su navegación, sus frases y su grabación.

    :param ruta: Carpeta o ZIP del libro.
    :param version: ``2.02`` o ``3``.
    :param tipo: Uno de :data:`TIPOS`.
    """

    def __init__(self, ruta: Path, version: str, tipo: str) -> None:
        self.ruta = ruta
        self.version = version
        self.tipo = tipo
        self.titulo = ""
        self.autor = ""
        self.narrador = ""
        self.editorial = ""
        self.idioma = ""
        self.duracion_declarada = 0.0
        self.frases: list[Frase] = []
        self.puntos: list[Punto] = []
        self.paginas: list[Punto] = []
        #: Archivo de texto principal, si el libro trae texto aparte del NCC.
        self.contenido = ""

    # -- lo que se puede hacer con él ----------------------------------------

    @property
    def tiene_audio(self) -> bool:
        """Si hay grabación que reproducir."""
        return any(frase.recortes for frase in self.frases)

    @property
    def tiene_texto(self) -> bool:
        """Si hay texto del libro, más allá del índice."""
        return bool(self.contenido)

    @property
    def duracion(self) -> float:
        """Lo que dura la grabación entera, en segundos."""
        calculada = sum(frase.duracion for frase in self.frases)
        return calculada or self.duracion_declarada

    def descripcion_del_tipo(self) -> str:
        """Explica en una frase qué clase de libro DAISY es este."""
        if self.tipo in ("audioOnly",):
            return _("DAISY %s de solo audio, sin índice.") % self.version
        if self.tipo in ("audioNcc", "audioNCX"):
            return _("DAISY %s de audio con índice y páginas, sin el texto del libro.") % self.version
        if self.tipo in ("audioPartText",):
            return _("DAISY %s de audio con parte del texto.") % self.version
        if self.tipo in ("audioFullText",):
            return _("DAISY %s de audio con el texto completo sincronizado.") % self.version
        if self.tipo in ("textPartAudio",):
            return _("DAISY %s de texto con algo de audio.") % self.version
        if self.tipo in ("textNcc", "textNCX"):
            return _("DAISY %s de solo texto, sin grabación.") % self.version
        return _("Libro DAISY %s.") % self.version

    def audio_de(self, indice: int) -> Recorte | None:
        """Primer recorte de audio de una frase, si lo tiene."""
        if 0 <= indice < len(self.frases):
            recortes = self.frases[indice].recortes
            if recortes:
                return recortes[0]
        return None

    def punto_en(self, frase: int) -> Punto | None:
        """Último punto del índice que empieza en esa frase o antes."""
        elegido = None
        for punto in self.puntos:
            if punto.frase > frase:
                break
            elegido = punto
        return elegido

    def pagina_en(self, frase: int) -> Punto | None:
        """Última página que empieza en esa frase o antes."""
        elegida = None
        for pagina in self.paginas:
            if pagina.frase > frase:
                break
            elegida = pagina
        return elegida

    def __repr__(self) -> str:
        return "<LibroDaisy %s %s %d frases %d puntos>" % (
            self.version, self.tipo, len(self.frases), len(self.puntos))


class Origen:
    """Da acceso a los archivos del libro, esté en carpeta o dentro de un ZIP.

    Los libros DAISY llegan de las dos maneras —la biblioteca te da un ZIP, el
    lector de sobremesa te deja una carpeta—, y todo lo demás funciona igual.
    """

    def __init__(self, ruta: Path) -> None:
        self.ruta = ruta
        self.zip = None
        if ruta.is_file() and zipfile.is_zipfile(ruta):
            self.zip = zipfile.ZipFile(ruta)
            self.nombres = [n for n in self.zip.namelist() if not n.endswith("/")]
            self.base = ""
        else:
            self.base = str(ruta if ruta.is_dir() else ruta.parent)
            self.nombres = [
                str(hijo.relative_to(self.base)).replace("\\", "/")
                for hijo in Path(self.base).rglob("*") if hijo.is_file()
            ]
        #: Los nombres en minúsculas, para buscar sin importar mayúsculas: en
        #: Windows da igual, pero dentro de un ZIP no.
        self._bajos = {n.lower(): n for n in self.nombres}

    def existe(self, nombre: str) -> bool:
        """Si el libro tiene ese archivo."""
        return nombre.lower() in self._bajos

    def real(self, nombre: str) -> str:
        """Devuelve el nombre tal y como está escrito en el libro."""
        return self._bajos.get(nombre.lower(), nombre)

    def leer(self, nombre: str) -> bytes:
        """Lee un archivo del libro por su ruta relativa."""
        real = self.real(nombre)
        if self.zip is not None:
            return self.zip.read(real)
        return (Path(self.base) / real).read_bytes()

    def ruta_de(self, nombre: str) -> Path | None:
        """Ruta en el disco de un archivo, si el libro es una carpeta.

        El reproductor necesita una ruta de verdad para dársela a BASS.  En un
        libro comprimido no la hay, y quien llame tiene que extraerlo antes.
        """
        if self.zip is not None:
            return None
        destino = Path(self.base) / self.real(nombre)
        return destino if destino.exists() else None

    def buscar(self, *extensiones: str) -> list[str]:
        """Archivos del libro con alguna de esas extensiones, ordenados."""
        bajas = tuple(e.lower() for e in extensiones)
        return sorted(n for n in self.nombres if n.lower().endswith(bajas))

    def cerrar(self) -> None:
        """Suelta el ZIP, si lo había."""
        if self.zip is not None:
            self.zip.close()
            self.zip = None

    def __enter__(self) -> "Origen":
        return self

    def __exit__(self, *_excepcion) -> None:
        self.cerrar()


# ---------------------------------------------------------------------------
# Reconocer que algo es un libro DAISY
# ---------------------------------------------------------------------------

def reconocer(origen: Origen) -> str:
    """Dice qué versión de DAISY es el libro, o cadena vacía si no lo es.

    Se mira lo que de verdad identifica a cada generación: el ``ncc.html`` de
    la 2.02 y el ``.ncx`` de la 3.  No basta con la extensión del archivo que
    haya elegido el usuario, porque en 2.02 el punto de entrada es un ``.html``
    corriente y en un ZIP puede no haber ninguna pista en el nombre.
    """
    if any(n.lower().endswith(NCC) for n in origen.nombres):
        return "2.02"
    if origen.buscar(".ncx"):
        return "3"
    # Un OPF también basta si se declara como libro hablado digital, sea por
    # sus metadatos «dtb:» o porque su contenido es DTBook.  Los libros DAISY 3
    # de solo texto llegan así muchas veces: OPF y DTBook, sin NCX ni SMIL,
    # porque sin grabación no hay nada que sincronizar.
    for opf in origen.buscar(".opf"):
        try:
            cabeza = origen.leer(opf)[:20000]
        except Exception:
            continue
        if b"dtb:" in cabeza or b"dtbook" in cabeza.lower():
            return "3"
    for contenido in origen.buscar(".xml"):
        try:
            if b"<dtbook" in origen.leer(contenido)[:4000].lower():
                return "3"
        except Exception:
            continue
    return ""


#: Extensiones que pueden ser la puerta de entrada de un libro DAISY.  Sirven
#: para no ir a mirar el disco cada vez que se abre un EPUB o un PDF.
_PUERTAS = (".html", ".htm", ".xhtml", ".ncx", ".opf", ".daisy", ".zip", ".xml")


def es_libro_daisy(ruta) -> bool:
    """Comprueba si una ruta apunta a un libro DAISY, sin llegar a leerlo.

    Se hace **barato a propósito**: esto se pregunta al abrir cualquier archivo,
    así que mira solo los hermanos de la carpeta —sin bajar por el árbol— y ni
    siquiera eso si la extensión no puede ser la de un DAISY.  Un ``ncc.html``
    es un ``.html`` corriente, y ahí está la gracia: lo que delata al libro no
    es su nombre sino lo que tiene al lado.
    """
    try:
        destino = Path(ruta)
        if destino.is_file():
            if destino.suffix.lower() not in _PUERTAS:
                return False
            if zipfile.is_zipfile(destino):
                with zipfile.ZipFile(destino) as comprimido:
                    nombres = [n.lower() for n in comprimido.namelist()]
                return any(n.endswith(NCC) or n.endswith(".ncx") for n in nombres)
            carpeta = destino.parent
        elif destino.is_dir():
            carpeta = destino
        else:
            return False
        for hijo in carpeta.iterdir():
            bajo = hijo.name.lower()
            if bajo == NCC or bajo.endswith(".ncx"):
                return True
        return False
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Lectura
# ---------------------------------------------------------------------------

def abrir(ruta, progreso=None) -> LibroDaisy:
    """Lee un libro DAISY entero: navegación, frases y grabación.

    :param ruta: Carpeta, ZIP, o cualquier archivo de dentro del libro.
    :param progreso: Canal opcional con ``paso(hecho, total, mensaje)``.
    :raises ValueError: Si eso no es un libro DAISY.
    """
    destino = Path(ruta)
    origen = Origen(destino)
    try:
        version = reconocer(origen)
        if not version:
            raise ValueError(_("Esto no es un libro DAISY."))
        libro = LibroDaisy(destino, version, "")
        if version == "2.02":
            _leer_202(origen, libro, progreso)
        else:
            _leer_3(origen, libro, progreso)
        if not libro.titulo:
            libro.titulo = (destino if destino.is_dir() else destino.parent).name
        log.info("DAISY %s (%s): %d frases, %d puntos, %d páginas, %s",
                 libro.version, libro.tipo or "tipo desconocido", len(libro.frases),
                 len(libro.puntos), len(libro.paginas), _duracion_legible(libro.duracion))
        return libro
    finally:
        origen.cerrar()


def _duracion_legible(segundos: float) -> str:
    """Escribe una duración en horas, minutos y segundos."""
    total = int(segundos)
    return "%d:%02d:%02d" % (total // 3600, (total % 3600) // 60, total % 60)


def _analizar(origen: Origen, nombre: str, html: bool = False):
    """Lee un archivo del libro como árbol XML, o ``None`` si no se puede.

    Los NCC de los años dos mil traen de todo: entidades HTML sin declarar,
    codificaciones raras y etiquetas sin cerrar.  Se intenta primero como XML
    en modo tolerante y, si aun así no sale nada, con el analizador de HTML,
    que se lo traga casi todo.
    """
    from formatos.lectura_xml import crear_parser_html, crear_parser_xml
    from lxml import etree

    try:
        datos = descodificar(origen.leer(nombre))
    except Exception as error:
        registrar_excepcion(log, "No se ha podido leer %s" % nombre, error)
        return None
    if not html:
        try:
            arbol = etree.fromstring(datos, parser=crear_parser_xml())
            if arbol is not None and len(arbol):
                return arbol
        except Exception:
            pass
    try:
        arbol = etree.fromstring(datos, parser=crear_parser_html())
        return arbol
    except Exception as error:
        registrar_excepcion(log, "No se ha podido analizar %s" % nombre, error)
        return None


def _junto_a(base: str, referencia: str) -> str:
    """Resuelve una referencia relativa a otro archivo del libro."""
    referencia = (referencia or "").split("#", 1)[0]
    if not referencia:
        return ""
    carpeta = posixpath.dirname(base)
    return posixpath.normpath(posixpath.join(carpeta, referencia)) if carpeta else referencia


# -- SMIL --------------------------------------------------------------------

def _leer_smil(origen: Origen, nombre: str) -> list[Frase]:
    """Saca de un SMIL sus frases, en orden de reproducción.

    Vale igual para SMIL 1.0 (DAISY 2.02, ``clip-begin="npt=1.709s"``) y para
    SMIL 2.0 (DAISY 3, ``clipBegin="0:00:01.709"``): se aceptan los dos nombres
    de atributo y todas las formas de escribir el tiempo.
    """
    arbol = _analizar(origen, nombre)
    if arbol is None:
        return []
    frases: list[Frase] = []
    for elemento in arbol.iter():
        if _nombre(elemento) != "par":
            continue
        recortes: list[Recorte] = []
        referencia = ""
        for hijo in elemento.iter():
            etiqueta = _nombre(hijo)
            if etiqueta == "audio":
                archivo = _junto_a(nombre, hijo.get("src", ""))
                if not archivo:
                    continue
                inicio = tiempo(hijo.get("clip-begin") or hijo.get("clipBegin"))
                fin = tiempo(hijo.get("clip-end") or hijo.get("clipEnd"))
                recortes.append(Recorte(archivo, inicio or 0.0, fin))
            elif etiqueta == "text" and not referencia:
                origen_texto = hijo.get("src", "")
                if origen_texto:
                    archivo, _sep, ancla = origen_texto.partition("#")
                    referencia = _junto_a(nombre, archivo)
                    if ancla:
                        referencia += "#" + ancla
        if recortes or referencia:
            frases.append(Frase(tuple(recortes), referencia, nombre,
                                elemento.get("id", "")))
    return frases


def _cerrar_recortes(frases: list[Frase]) -> list[Frase]:
    """Rellena los finales de recorte que el libro no declara.

    Algunos productores dejan el último ``clip-end`` de un archivo sin poner, o
    no ponen ninguno cuando cada frase es un archivo entero.  Si la frase
    siguiente usa el mismo audio, su comienzo es el final de esta; si no, se
    deja en ``None`` y quien reproduzca lo llevará hasta el final del archivo.
    """
    arreglados: list[Frase] = []
    for numero, frase in enumerate(frases):
        if not frase.recortes:
            arreglados.append(frase)
            continue
        recortes = list(frase.recortes)
        for indice, recorte in enumerate(recortes):
            if recorte.fin is not None:
                continue
            siguiente = None
            if indice + 1 < len(recortes):
                siguiente = recortes[indice + 1]
            elif numero + 1 < len(frases) and frases[numero + 1].recortes:
                siguiente = frases[numero + 1].recortes[0]
            if siguiente is not None and siguiente.archivo == recorte.archivo:
                recortes[indice] = recorte._replace(fin=siguiente.inicio)
        arreglados.append(frase._replace(recortes=tuple(recortes)))
    return arreglados


# -- DAISY 2.02 --------------------------------------------------------------

def _leer_202(origen: Origen, libro: LibroDaisy, progreso=None) -> None:
    """Lee un libro DAISY 2.02 a partir de su ``ncc.html``."""
    ncc = next((n for n in origen.nombres if n.lower().endswith(NCC)), "")
    arbol = _analizar(origen, ncc, html=True)
    if arbol is None:
        raise ValueError(_("El archivo de navegación del libro DAISY no se puede leer."))

    _metadatos_202(arbol, libro)

    # El cuerpo del NCC es la navegación: encabezados y páginas, en el orden
    # del libro, cada uno enlazando a un punto de un SMIL.  De ese mismo
    # recorrido sale el orden en que hay que leer los SMIL.
    entradas: list[tuple[str, int, str, str]] = []   # (título, nivel, smil, ancla)
    orden_smil: list[str] = []
    for elemento in arbol.iter():
        etiqueta = _nombre(elemento)
        clase = (elemento.get("class") or "").lower()
        if etiqueta in ("h1", "h2", "h3", "h4", "h5", "h6"):
            nivel = int(etiqueta[1])
            clase_punto = "titulo"
        elif etiqueta == "span" and clase in _CLASES_PAGINA:
            nivel = 0
            clase_punto = "pagina"
        else:
            continue
        destino = ""
        for enlace in elemento.iter():
            if _nombre(enlace) == "a" and enlace.get("href"):
                destino = enlace.get("href")
                break
        if not destino:
            continue
        archivo, _sep, ancla = destino.partition("#")
        smil = _junto_a(ncc, archivo)
        if smil and smil not in orden_smil:
            orden_smil.append(smil)
        entradas.append((_texto_de(elemento) or _("(sin título)"), nivel, smil, ancla))
        if nivel:
            libro.puntos.append(Punto("", nivel, -1, clase_punto))   # se rellena luego

    libro.puntos.clear()
    _montar(origen, libro, ncc, orden_smil, entradas, progreso)

    if not libro.tipo:
        libro.tipo = "audioNcc" if libro.tiene_audio else "textNcc"
    # El archivo de texto de un 2.02 es aquel al que apuntan las frases y que
    # no es el propio NCC: si todas apuntan al NCC, el libro no trae texto.
    for frase in libro.frases:
        archivo = frase.texto.split("#", 1)[0]
        if archivo and not archivo.lower().endswith(NCC):
            libro.contenido = archivo
            break


def _metadatos_202(arbol, libro: LibroDaisy) -> None:
    """Saca del NCC el título, el autor, el narrador y el tipo de libro."""
    for elemento in arbol.iter():
        if _nombre(elemento) != "meta":
            continue
        clave = (elemento.get("name") or "").strip().lower()
        valor = (elemento.get("content") or "").strip()
        if not clave or not valor:
            continue
        if clave == "dc:title" and not libro.titulo:
            libro.titulo = valor
        elif clave == "dc:creator" and not libro.autor:
            libro.autor = valor
        elif clave == "dc:publisher":
            libro.editorial = valor
        elif clave == "dc:language":
            libro.idioma = valor
        elif clave == "ncc:narrator":
            libro.narrador = valor
        elif clave == "ncc:multimediatype":
            libro.tipo = valor
        elif clave == "ncc:totaltime":
            libro.duracion_declarada = tiempo(valor) or 0.0
    if not libro.titulo:
        for elemento in arbol.iter():
            if _nombre(elemento) == "title":
                libro.titulo = _texto_de(elemento)
                break


# -- DAISY 3 -----------------------------------------------------------------

def _leer_3(origen: Origen, libro: LibroDaisy, progreso=None) -> None:
    """Lee un libro DAISY 3 a partir de su OPF y su NCX."""
    opf = next(iter(origen.buscar(".opf")), "")
    if opf:
        _metadatos_3(origen, opf, libro)

    orden_smil = _orden_3(origen, opf)
    entradas = _navegacion_3(origen, libro)
    base = opf or next(iter(origen.buscar(".ncx")), "")
    _montar(origen, libro, base, orden_smil, entradas, progreso)

    if not libro.tipo:
        libro.tipo = "audioFullText" if libro.tiene_audio else "textNCX"
    for frase in libro.frases:
        archivo = frase.texto.split("#", 1)[0]
        if archivo and not archivo.lower().endswith(".smil"):
            libro.contenido = archivo
            break


def _metadatos_3(origen: Origen, opf: str, libro: LibroDaisy) -> None:
    """Lee del OPF los datos del libro, incluido su ``dtb:multimediaType``."""
    arbol = _analizar(origen, opf)
    if arbol is None:
        return
    for elemento in arbol.iter():
        etiqueta = _nombre(elemento)
        if etiqueta == "meta":
            clave = (elemento.get("name") or "").strip().lower()
            valor = (elemento.get("content") or "").strip()
            if not valor:
                continue
            if clave == "dtb:multimediatype":
                libro.tipo = valor
            elif clave == "dtb:totaltime":
                libro.duracion_declarada = tiempo(valor) or 0.0
            elif clave == "dtb:narrator":
                libro.narrador = valor
            elif clave.endswith("title") and not libro.titulo:
                libro.titulo = valor
            elif clave.endswith("creator") and not libro.autor:
                libro.autor = valor
            continue
        valor = (elemento.text or "").strip()
        if not valor:
            continue
        if etiqueta == "title" and not libro.titulo:
            libro.titulo = valor
        elif etiqueta == "creator" and not libro.autor:
            libro.autor = valor
        elif etiqueta == "language" and not libro.idioma:
            libro.idioma = valor
        elif etiqueta == "publisher" and not libro.editorial:
            libro.editorial = valor


def _orden_3(origen: Origen, opf: str) -> list[str]:
    """Orden de lectura de los SMIL: el ``spine`` del OPF, o por nombre."""
    if opf:
        arbol = _analizar(origen, opf)
        if arbol is not None:
            rutas = {}
            for elemento in arbol.iter():
                if _nombre(elemento) == "item":
                    rutas[elemento.get("id", "")] = elemento.get("href", "")
            orden = []
            for elemento in arbol.iter():
                if _nombre(elemento) != "itemref":
                    continue
                href = rutas.get(elemento.get("idref", ""), "")
                if href and href.lower().endswith(".smil"):
                    orden.append(_junto_a(opf, href))
            if orden:
                return orden
    return origen.buscar(".smil")


def _navegacion_3(origen: Origen, libro: LibroDaisy) -> list[tuple[str, int, str, str]]:
    """Lee el NCX: el índice del ``navMap`` y las páginas del ``pageList``."""
    ncx = next(iter(origen.buscar(".ncx")), "")
    if not ncx:
        return []
    arbol = _analizar(origen, ncx)
    if arbol is None:
        return []
    entradas: list[tuple[str, int, str, str]] = []

    def recorrer(elemento, nivel: int) -> None:
        """Baja por el árbol de puntos guardando su profundidad."""
        for hijo in elemento:
            etiqueta = _nombre(hijo)
            if etiqueta not in ("navpoint", "navtarget", "pagetarget"):
                recorrer(hijo, nivel)
                continue
            titulo = ""
            destino = ""
            for dentro in hijo.iter():
                nombre_dentro = _nombre(dentro)
                if nombre_dentro == "navlabel" and not titulo:
                    titulo = _texto_de(dentro)
                elif nombre_dentro == "content" and not destino:
                    destino = dentro.get("src", "")
            if destino:
                archivo, _sep, ancla = destino.partition("#")
                pagina = etiqueta == "pagetarget"
                entradas.append((titulo or _("(sin título)"),
                                 0 if pagina else min(nivel, 6),
                                 _junto_a(ncx, archivo), ancla))
            if etiqueta == "navpoint":
                recorrer(hijo, nivel + 1)

    for elemento in arbol.iter():
        if _nombre(elemento) in ("navmap", "pagelist", "navlist"):
            recorrer(elemento, 1)
    return entradas


# -- montaje común -----------------------------------------------------------

def _montar(origen: Origen, libro: LibroDaisy, base: str, orden_smil: list[str],
            entradas: list[tuple[str, int, str, str]], progreso=None) -> None:
    """Lee los SMIL en orden y ata la navegación a las frases resultantes.

    Es la parte común a las dos versiones: cambia de dónde sale el orden y de
    dónde salen los títulos, pero una vez se tienen las dos listas el trabajo
    es idéntico.
    """
    # Cualquier SMIL que no estuviera en el orden declarado se añade al final:
    # más vale leerlo fuera de sitio que perderlo.
    todos = list(orden_smil)
    for nombre in origen.buscar(".smil"):
        if nombre not in todos:
            todos.append(nombre)

    #: Dónde empieza cada SMIL dentro de la lista de frases, y dónde está cada
    #: ancla concreta.  Con eso se resuelven los enlaces de la navegación.
    inicio_de_smil: dict[str, int] = {}
    anclas: dict[str, int] = {}
    total = len(todos)
    for numero, nombre in enumerate(todos):
        if progreso is not None:
            progreso.paso(numero, total,
                          _("Leyendo la sincronización %d de %d") % (numero + 1, total))
        frases = _leer_smil(origen, nombre)
        if not frases:
            continue
        inicio_de_smil[nombre] = len(libro.frases)
        for frase in frases:
            posicion = len(libro.frases)
            if frase.identificador:
                anclas["%s#%s" % (nombre, frase.identificador)] = posicion
            if frase.texto:
                anclas[frase.texto] = posicion
                _archivo, _sep, ancla = frase.texto.partition("#")
                if ancla:
                    anclas.setdefault("%s#%s" % (nombre, ancla), posicion)
            libro.frases.append(frase)

    libro.frases = _cerrar_recortes(libro.frases)

    for titulo, nivel, smil, ancla in entradas:
        destino = -1
        if ancla:
            destino = anclas.get("%s#%s" % (smil, ancla), -1)
        if destino < 0:
            destino = inicio_de_smil.get(smil, -1)
        if destino < 0:
            continue
        punto = Punto(titulo, nivel, destino, "pagina" if nivel == 0 else "titulo")
        if nivel == 0:
            libro.paginas.append(punto)
        else:
            libro.puntos.append(punto)

    libro.puntos.sort(key=lambda punto: punto.frase)
    libro.paginas.sort(key=lambda punto: punto.frase)
