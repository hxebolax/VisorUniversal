# -*- coding: utf-8 -*-
"""Archivos de ayuda de Windows (CHM).

La documentación técnica de los años noventa y dos mil se publicó en ``.chm``, y
buena parte de ella sigue siendo la única que hay: manuales de ingeniería, de
programas de cálculo, de máquinas industriales, referencias de lenguajes.  En
una carrera técnica todavía aparecen, y hasta ahora eran un archivo que no se
podía abrir de ninguna manera.

Por dentro un CHM es sencillo de contar y engorroso de leer: es **un ZIP hecho a
la manera de Microsoft**, con un índice propio y con el contenido comprimido en
LZX en vez de en *deflate*.  Los archivos que lleva dentro son **HTML**, así que
en cuanto se sacan, el trabajo lo hace el conversor de siempre.

Las tres capas
--------------

1. **ITSF**, la cabecera del archivo, que dice dónde están las otras dos cosas.
2. **ITSP**, el listado: una serie de trozos ``PMGL`` con el nombre, el sitio y
   el tamaño de cada archivo interno.  Los nombres van con una codificación de
   enteros de longitud variable que hay que descifrar byte a byte.
3. El **contenido**, en dos secciones: la 0 sin comprimir —donde viven las
   tablas de control— y la 1 comprimida con LZX (:mod:`formatos.lzx`), donde
   está todo lo demás.

Qué se lee y en qué orden
-------------------------

El orden importa mucho: un manual son doscientas páginas HTML sueltas, y leerlas
por orden alfabético de nombre de archivo daría un libro sin pies ni cabeza.  El
CHM trae su propio índice —un archivo ``.hhc``, que es HTML con listas
anidadas— y **de ahí sale el orden y el índice del documento**.  Lo que no esté
en el índice se añade detrás, porque perder una página es peor que ponerla al
final.

Lo que no se abre
-----------------

Los CHM cifrados y los partidos en varios archivos (``.chi``) no se abren, y se
dice.  Son rarísimos.
"""

from __future__ import annotations

import re
import struct
from pathlib import Path

from nucleo.documento import Metadatos
from nucleo.idioma import _
from nucleo.registro import obtener_registro

from .base import Analizador, ErrorFormato, OpcionesAnalisis, registrar
from .ensamblador import montar
from .lzx import Descompresor, ErrorLZX

log = obtener_registro(__name__)

#: Marcas de las tres estructuras.
ITSF = b"ITSF"
ITSP = b"ITSP"
PMGL = b"PMGL"

#: Nombres internos de las tablas que gobiernan la descompresión.
CONTENIDO = "::DataSpace/Storage/MSCompressed/Content"
CONTROL = "::DataSpace/Storage/MSCompressed/ControlData"
REINICIOS = ("::DataSpace/Storage/MSCompressed/Transform/"
             "{7FC28940-9D31-11D0-9B27-00A0C91E9C7C}/InstanceData/ResetTable")

#: Extensiones de los archivos internos que son contenido de verdad.  Lo demás
#: —los índices binarios, las tablas de búsqueda— es maquinaria del formato.
PAGINAS = (".htm", ".html", ".xhtml", ".txt")

#: Cuántas páginas se leen como mucho.  Un manual grande tiene unas mil; con
#: cinco mil, montar el documento cuesta más de lo que vale.
PAGINAS_MAXIMAS = 5000


class ErrorCHM(ErrorFormato):
    """El archivo de ayuda no se puede leer."""


# ---------------------------------------------------------------------------
# El índice interno
# ---------------------------------------------------------------------------

def _entero_variable(datos: bytes, posicion: int) -> tuple[int, int]:
    """Lee un entero de longitud variable.  Devuelve ``(valor, posición nueva)``.

    Cada byte aporta siete bits, y el bit de más peso dice si sigue otro.  Los
    bytes vienen de más significativo a menos, al revés que en casi todo lo
    demás del formato.
    """
    valor = 0
    while posicion < len(datos):
        byte = datos[posicion]
        posicion += 1
        valor = (valor << 7) | (byte & 0x7F)
        if not (byte & 0x80):
            return valor, posicion
    raise ErrorCHM(_("El índice del archivo de ayuda está cortado."))


class Entrada:
    """Un archivo dentro del CHM: dónde está y cuánto ocupa."""

    __slots__ = ("nombre", "seccion", "desplazamiento", "largo")

    def __init__(self, nombre: str, seccion: int, desplazamiento: int,
                 largo: int) -> None:
        self.nombre = nombre
        self.seccion = seccion
        self.desplazamiento = desplazamiento
        self.largo = largo


class ArchivoCHM:
    """Un CHM abierto, con su índice leído y su contenido a mano.

    La sección comprimida se descomprime **entera y una sola vez**, la primera
    vez que se pide algo de ella.  Descomprimir por trozos usando la tabla de
    reinicios sería más fino, pero un manual entero son unos pocos megabytes y
    el documento se monta leyéndolo todo de todas formas: así se descomprime una
    vez en lugar de doscientas.
    """

    def __init__(self, ruta) -> None:
        self.ruta = Path(ruta)
        try:
            self.datos = self.ruta.read_bytes()
        except OSError as error:
            raise ErrorCHM(_("No se ha podido leer el archivo: %s") % error) from error
        self.entradas: dict[str, Entrada] = {}
        self._contenido_seccion0 = 0
        self._descomprimido: bytes | None = None
        self._leer()

    # -- el envoltorio -------------------------------------------------------

    def _leer(self) -> None:
        """Lee la cabecera y el listado de archivos."""
        datos = self.datos
        if len(datos) < 0x60 or datos[:4] != ITSF:
            raise ErrorCHM(_("El archivo no es un archivo de ayuda de Windows."))
        version = struct.unpack_from("<L", datos, 4)[0]
        if version < 2:
            raise ErrorCHM(
                _("El archivo de ayuda es de una versión demasiado antigua."))
        seccion1 = struct.unpack_from("<Q", datos, 0x48)[0]
        if version >= 3:
            self._contenido_seccion0 = struct.unpack_from("<Q", datos, 0x58)[0]
        else:
            # En la versión 2 el contenido empieza justo después de la cabecera.
            self._contenido_seccion0 = struct.unpack_from("<L", datos, 8)[0]
        self._leer_listado(seccion1)

    def _leer_listado(self, inicio: int) -> None:
        """Recorre los trozos ``PMGL`` apuntando dónde está cada archivo."""
        datos = self.datos
        if datos[inicio:inicio + 4] != ITSP:
            raise ErrorCHM(_("El archivo de ayuda no trae su índice interno."))
        largo_cabecera = struct.unpack_from("<L", datos, inicio + 0x08)[0]
        tamano_trozo = struct.unpack_from("<L", datos, inicio + 0x10)[0]
        primero = struct.unpack_from("<l", datos, inicio + 0x20)[0]
        ultimo = struct.unpack_from("<l", datos, inicio + 0x24)[0]
        cuantos = struct.unpack_from("<L", datos, inicio + 0x2C)[0]
        base = inicio + largo_cabecera

        if tamano_trozo <= 0 or cuantos <= 0:
            raise ErrorCHM(_("El índice del archivo de ayuda no es válido."))
        for numero in range(cuantos):
            if not (primero <= numero <= ultimo):
                continue
            donde = base + numero * tamano_trozo
            trozo = datos[donde:donde + tamano_trozo]
            if len(trozo) < 20 or trozo[:4] != PMGL:
                continue
            self._leer_trozo(trozo)
        log.info("CHM %s: %d archivos internos", self.ruta.name, len(self.entradas))

    def _leer_trozo(self, trozo: bytes) -> None:
        """Lee las entradas de un trozo del listado."""
        libre = struct.unpack_from("<L", trozo, 4)[0]
        fin = max(20, len(trozo) - libre)
        posicion = 20
        while posicion < fin:
            try:
                largo_nombre, posicion = _entero_variable(trozo, posicion)
                nombre = trozo[posicion:posicion + largo_nombre].decode(
                    "utf-8", "replace")
                posicion += largo_nombre
                seccion, posicion = _entero_variable(trozo, posicion)
                desplazamiento, posicion = _entero_variable(trozo, posicion)
                largo, posicion = _entero_variable(trozo, posicion)
            except ErrorCHM:
                return
            if nombre:
                self.entradas[nombre] = Entrada(nombre, seccion, desplazamiento,
                                                largo)

    # -- el contenido --------------------------------------------------------

    def leer(self, nombre: str) -> bytes | None:
        """Devuelve el contenido de un archivo interno, o ``None``."""
        entrada = self.entradas.get(nombre)
        if entrada is None:
            return None
        if entrada.largo == 0:
            return b""
        if entrada.seccion == 0:
            inicio = self._contenido_seccion0 + entrada.desplazamiento
            return self.datos[inicio:inicio + entrada.largo]
        datos = self._seccion_comprimida()
        return datos[entrada.desplazamiento:entrada.desplazamiento + entrada.largo]

    def _seccion_comprimida(self) -> bytes:
        """Descomprime la sección 1 entera, una sola vez."""
        if self._descomprimido is not None:
            return self._descomprimido
        contenido = self._crudo(CONTENIDO)
        control = self._crudo(CONTROL)
        tabla = self._crudo(REINICIOS)
        if contenido is None or control is None or tabla is None:
            raise ErrorCHM(
                _("El archivo de ayuda no trae las tablas que hacen falta para "
                  "descomprimirlo."))

        if len(control) < 28 or control[4:8] != b"LZXC":
            raise ErrorCHM(_("El archivo de ayuda usa una compresión desconocida."))
        # El orden de los campos importa mucho y es fácil equivocarse: el
        # intervalo de reinicio va en 0x0C y el tamaño de ventana en 0x10.  Los
        # dos vienen contados en bloques de 32 KB, no en bytes, y la ventana
        # decide **cuántos símbolos tiene el árbol principal**: leerla mal da un
        # árbol incompleto y no se descomprime ni el primer bloque.
        intervalo = struct.unpack_from("<L", control, 0x0C)[0]
        ventana = struct.unpack_from("<L", control, 0x10)[0]
        bits_ventana = max(15, min(21, (max(ventana, 1) * 0x8000).bit_length() - 1))

        if len(tabla) < 0x28:
            raise ErrorCHM(_("El archivo de ayuda tiene la tabla de bloques dañada."))
        bloques = struct.unpack_from("<L", tabla, 4)[0]
        sin_comprimir = struct.unpack_from("<Q", tabla, 0x10)[0]
        comprimido = struct.unpack_from("<Q", tabla, 0x18)[0]
        por_bloque = struct.unpack_from("<Q", tabla, 0x20)[0] or 0x8000
        puntos = [struct.unpack_from("<Q", tabla, 0x28 + numero * 8)[0]
                  for numero in range(bloques)]
        if not puntos:
            raise ErrorCHM(_("El archivo de ayuda no tiene ningún bloque de datos."))

        salida = bytearray()
        motor = Descompresor(bits_ventana)
        # El intervalo dice cada cuántos bloques se pone a cero el estado de la
        # compresión.  Descomprimir sin respetarlo da basura a partir del
        # segundo tramo, y es el fallo más difícil de ver: los primeros treinta
        # y dos kilobytes salen perfectos.
        cada = intervalo if intervalo > 0 else 1
        for numero in range(bloques):
            if numero % cada == 0:
                motor.reiniciar()
                grupo_final = min(numero + cada, bloques)
                inicio = puntos[numero]
                fin = (puntos[grupo_final] if grupo_final < bloques else comprimido)
                trozo = contenido[inicio:fin]
                esperado = min(por_bloque * (grupo_final - numero),
                               sin_comprimir - len(salida))
                try:
                    salida += motor.descomprimir(trozo, esperado)
                except ErrorLZX as error:
                    log.warning("El archivo de ayuda %s está dañado a partir del "
                                "bloque %d: %s", self.ruta.name, numero, error)
                    break
        self._descomprimido = bytes(salida)
        log.info("CHM %s: %d KB descomprimidos", self.ruta.name,
                 len(self._descomprimido) // 1024)
        return self._descomprimido

    def _crudo(self, nombre: str) -> bytes | None:
        """Lee un archivo de la sección sin comprimir."""
        entrada = self.entradas.get(nombre)
        if entrada is None or entrada.seccion != 0:
            return None
        inicio = self._contenido_seccion0 + entrada.desplazamiento
        return self.datos[inicio:inicio + entrada.largo]


# ---------------------------------------------------------------------------
# El orden de lectura
# ---------------------------------------------------------------------------

#: Un enlace del índice del CHM, que va en un ``<param>`` de un ``<object>``.
_PARAMETRO = re.compile(
    rb'(?i)<param\s+name="(Local|Name)"\s+value="([^"]*)"')


def _paginas_del_indice(datos: bytes) -> list[str]:
    """Saca del ``.hhc`` los archivos en el orden en que hay que leerlos.

    El ``.hhc`` es HTML: listas anidadas de ``<object>`` con un parámetro
    ``Local`` que dice a qué archivo apunta cada entrada.  Ese es el orden del
    manual, y es el único sitio donde está.
    """
    orden: list[str] = []
    vistos = set()
    for encaje in _PARAMETRO.finditer(datos or b""):
        if encaje.group(1).lower() != b"local":
            continue
        destino = encaje.group(2).decode("utf-8", "replace")
        destino = destino.split("#", 1)[0].split("::")[-1].strip()
        if not destino:
            continue
        clave = destino.lower().lstrip("/")
        if clave in vistos:
            continue
        vistos.add(clave)
        orden.append(destino)
    return orden


def _titulos_del_indice(datos: bytes) -> dict[str, str]:
    """Empareja cada archivo con el título que le da el índice.

    Es lo que permite que el documento tenga encabezados con los nombres del
    manual y no con el del archivo (``HELPArcComment.htm``).
    """
    titulos: dict[str, str] = {}
    nombre = ""
    for encaje in _PARAMETRO.finditer(datos or b""):
        clase = encaje.group(1).lower()
        valor = encaje.group(2).decode("utf-8", "replace").strip()
        if clase == b"name":
            nombre = valor
        elif clase == b"local" and nombre:
            destino = valor.split("#", 1)[0].split("::")[-1].strip().lstrip("/")
            titulos.setdefault(destino.lower(), nombre)
            nombre = ""
    return titulos


def _es_pagina(nombre: str) -> bool:
    """Indica si un archivo interno es contenido y no maquinaria del formato."""
    if nombre.startswith(("/#", "/$", "::", "#", "$")):
        return False
    if nombre.endswith("/"):
        return False
    return nombre.lower().endswith(PAGINAS)


class AnalizadorCHM(Analizador):
    """Archivos de ayuda de Windows."""

    extensiones = (".chm",)
    descripcion = _("Ayuda de Windows (CHM)")

    def analizar(self, ruta, opciones: OpcionesAnalisis):
        """Convierte el archivo de ayuda en un documento con sus capítulos."""
        archivo = ArchivoCHM(ruta)
        orden = self._orden(archivo)
        if not orden:
            raise ErrorCHM(
                _("El archivo de ayuda no contiene ninguna página que se pueda leer."))

        titulos = {}
        for nombre in archivo.entradas:
            if nombre.lower().endswith(".hhc"):
                titulos = _titulos_del_indice(archivo.leer(nombre) or b"")
                break

        secciones = []
        progreso = opciones.progreso
        for numero, nombre in enumerate(orden):
            if progreso is not None:
                progreso.paso(numero, len(orden),
                              _("Leyendo la página %d de %d") % (numero + 1, len(orden)))
            datos = archivo.leer(nombre)
            if not datos:
                continue
            titulo = titulos.get(nombre.lower().lstrip("/"),
                                 Path(nombre).stem)
            secciones.append((titulo, datos))

        if not secciones:
            raise ErrorCHM(
                _("El archivo de ayuda no contiene ninguna página que se pueda leer."))
        metadatos = Metadatos(titulo=self._titulo(archivo) or Path(ruta).stem)
        documento = montar(secciones, metadatos, Path(ruta), opciones)
        log.info("Archivo de ayuda analizado: %s | %d páginas",
                 Path(ruta).name, len(secciones))
        return documento

    @staticmethod
    def _orden(archivo: ArchivoCHM) -> list[str]:
        """El orden de lectura: el del índice, y detrás lo que no esté en él."""
        paginas = [nombre for nombre in archivo.entradas if _es_pagina(nombre)]
        disponibles = {nombre.lower().lstrip("/"): nombre for nombre in paginas}

        orden: list[str] = []
        for nombre in archivo.entradas:
            if not nombre.lower().endswith(".hhc"):
                continue
            for destino in _paginas_del_indice(archivo.leer(nombre) or b""):
                real = disponibles.pop(destino.lower().lstrip("/"), None)
                if real is not None:
                    orden.append(real)
            break
        # Lo que el índice no menciona se añade detrás, ordenado por su nombre:
        # perder una página es peor que ponerla al final.
        orden += sorted(disponibles.values(), key=str.lower)
        return orden[:PAGINAS_MAXIMAS]

    @staticmethod
    def _titulo(archivo: ArchivoCHM) -> str:
        """El título del manual, que va en el archivo interno ``#SYSTEM``."""
        datos = archivo.leer("/#SYSTEM") or archivo.leer("#SYSTEM")
        if not datos or len(datos) < 4:
            return ""
        posicion = 4
        while posicion + 4 <= len(datos):
            codigo, largo = struct.unpack_from("<HH", datos, posicion)
            posicion += 4
            valor = datos[posicion:posicion + largo]
            posicion += largo
            if codigo == 3:                          # título del archivo de ayuda
                return valor.split(b"\0", 1)[0].decode("utf-8", "replace").strip()
        return ""

    def extraer_recurso(self, ruta, interna: str) -> bytes | None:
        """Devuelve una imagen del archivo de ayuda."""
        try:
            archivo = ArchivoCHM(ruta)
        except ErrorFormato:
            return None
        for candidato in (interna, "/" + interna.lstrip("/")):
            datos = archivo.leer(candidato)
            if datos:
                return datos
        return None


registrar(AnalizadorCHM())
