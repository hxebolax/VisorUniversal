# -*- coding: utf-8 -*-
"""Cómic y novela gráfica: CBZ, CBT y los CBR que por dentro son un ZIP.

Un cómic digital no es más que **una carpeta de imágenes numeradas** metida en
un archivo comprimido.  No hay texto: lo que hay son páginas dibujadas, y por
eso hasta ahora un cómic era, para quien no ve, un archivo que no se podía
abrir de ninguna manera.

Lo que cambia es que el programa ya sabe **describir imágenes con inteligencia
artificial**.  Abriendo el cómic aquí, cada página es una imagen del documento:
se recorren con ``G``, se ven con ``Control+I`` y se describen con
``Control+Alt+I`` una a una o con ``Control+Alt+D`` todas de golpe.  La
descripción se guarda y vuelve con el archivo, igual que en un EPUB, así que un
álbum descrito una vez queda descrito para siempre.

Sobre el CBR
------------

Un ``.cbr`` es en teoría un RAR, un formato cerrado que Python no lee.  Se
intentan tres cosas, en este orden:

1. **Mirar lo que hay dentro y no el nombre.**  Muchos ``.cbr`` vienen
   comprimidos como ZIP con la extensión cambiada, y esos se abren sin más.
2. **Usar el descompresor que Windows ya trae.**  Desde Windows 10, el sistema
   incluye ``tar.exe``, que es bsdtar y sabe leer RAR, RAR5 y 7z.  No hay que
   instalar nada (:mod:`nucleo.descomprimir`).
3. **Decir con claridad qué pasa** cuando el archivo es de los que ese
   descompresor no alcanza —los RAR sólidos y los partidos en volúmenes—, en
   vez de fallar sin explicación.

Lo descomprimido se guarda en una carpeta temporal y se reaprovecha: sin eso,
un álbum de cincuenta páginas descomprimiría el archivo entero cincuenta veces,
una por página, cada vez que se pidiera ver una.
"""

from __future__ import annotations

import posixpath
import re
import zipfile
from pathlib import Path

from nucleo import descomprimir
from nucleo.documento import Metadatos
from nucleo.idioma import _
from nucleo.registro import obtener_registro

from .base import Analizador, ErrorFormato, OpcionesAnalisis, registrar
from .ensamblador import envolver, escapar, montar

log = obtener_registro(__name__)

#: Extensiones de imagen que se toman por páginas del cómic.
IMAGENES = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".avif")

#: Marca con la que empieza un archivo RAR de verdad.
MARCA_RAR = b"Rar!\x1a\x07"

#: Marca con la que empieza un archivo 7z.
MARCA_7Z = b"7z\xbc\xaf\x27\x1c"

#: Tope de páginas.  Un álbum tiene cincuenta; con mil, algo va mal en el
#: archivo y montar el documento entero costaría más de lo que vale.
PAGINAS_MAXIMAS = 2000

#: Cómics ya descomprimidos en esta sesión: ``ruta -> (fecha, carpeta)``.  La
#: fecha del archivo forma parte de la clave para que, si el archivo cambia,
#: se vuelva a descomprimir en lugar de enseñar lo de antes.
_DESCOMPRIMIDOS: dict = {}


def _carpeta_de(destino: Path):
    """Descomprime el cómic —o devuelve lo ya descomprimido— y dice cómo ha ido.

    Devuelve la :class:`~nucleo.descomprimir.Extraccion` entera y no solo la
    carpeta, porque **de un cómic partido en volúmenes salen las páginas del
    primero y nada más**, y eso, sin avisar, se lee como un cómic que se acaba
    en la página cinco. Quien no ve la pantalla no tiene ninguna otra forma de
    sospecharlo.
    """
    try:
        fecha = destino.stat().st_mtime_ns
    except OSError:
        return None
    clave = str(destino.resolve()).lower()
    guardado = _DESCOMPRIMIDOS.get(clave)
    if guardado is not None and guardado[0] == fecha and Path(guardado[1]).is_dir():
        return descomprimir.Extraccion(Path(guardado[1]), guardado[2], guardado[3],
                                       guardado[4])
    extraccion = descomprimir.extraer_detallado(destino)
    if extraccion.carpeta is not None:
        _DESCOMPRIMIDOS[clave] = (fecha, str(extraccion.carpeta), extraccion.faltan,
                                  extraccion.programa, extraccion.por_volumenes)
    return extraccion


class AnalizadorComic(Analizador):
    """Cómic en archivo comprimido."""

    extensiones = (".cbz", ".cbr", ".cbt", ".cb7")
    descripcion = _("Cómic")

    def analizar(self, ruta, opciones: OpcionesAnalisis):
        """Convierte el cómic en un documento con una imagen por página."""
        destino = Path(ruta)
        paginas, aviso = self._paginas(destino)
        if not paginas:
            raise ErrorFormato(
                _("El cómic no contiene ninguna página que se pueda leer."))
        partes = []
        if aviso:
            # El aviso va **arriba del todo**, antes de la primera página, y no
            # al final: al final solo lo leería quien haya llegado hasta allí,
            # y justamente lo que se avisa es que no se puede llegar.
            partes.append("<p><strong>%s</strong></p>" % escapar(aviso))
        for numero, nombre in enumerate(paginas, start=1):
            # El texto alternativo dice de qué página se trata: sin él, un
            # álbum de cincuenta páginas sería cincuenta veces «[Imagen]» y no
            # habría forma de saber por dónde se va.
            partes.append('<p><img src="%s" alt="%s"/></p>'
                          % (escapar(nombre), escapar(_("Página %d") % numero)))
        cuerpo = "\n".join(partes)
        metadatos = Metadatos(titulo=destino.stem)
        documento = montar([(destino.name, envolver(cuerpo))], metadatos, destino, opciones)
        log.info("Cómic analizado: %s | %d páginas", destino.name, len(paginas))
        return documento

    def _paginas(self, destino: Path):
        """Las páginas en orden y, si falta alguna, con qué avisarlo."""
        aviso = ""
        if _es_zip(destino):
            try:
                with zipfile.ZipFile(str(destino)) as archivo:
                    nombres = [nombre for nombre in archivo.namelist()
                               if _es_pagina(nombre)]
            except Exception as error:
                raise ErrorFormato(
                    _("No se ha podido abrir el cómic: %s") % error) from error
        else:
            extraccion = _carpeta_de(destino)
            if extraccion.carpeta is None:
                raise ErrorFormato(descomprimir.motivo_de_fallo(destino.name))
            carpeta = extraccion.carpeta
            nombres = [hijo.relative_to(carpeta).as_posix()
                       for hijo in carpeta.rglob("*") if hijo.is_file()]
            nombres = [nombre for nombre in nombres if _es_pagina(nombre)]
            if not extraccion.completa:
                aviso = descomprimir.motivo_de_lo_que_falta(extraccion, destino.name)
                log.info("Cómic incompleto: %s (%s)", destino.name, aviso)
        return sorted(nombres, key=_orden_natural)[:PAGINAS_MAXIMAS], aviso

    def extraer_recurso(self, ruta, interna: str) -> bytes | None:
        """Devuelve una página del cómic, para verla o describirla."""
        destino = Path(ruta)
        try:
            if _es_zip(destino):
                with zipfile.ZipFile(str(destino)) as archivo:
                    return archivo.read(interna)
            carpeta = _carpeta_de(destino).carpeta
            if carpeta is None:
                return None
            pagina = carpeta / interna
            # Se comprueba que la página está de verdad dentro de la carpeta:
            # un nombre con «..» dentro del comprimido no debe poder leer
            # archivos de fuera.
            if carpeta.resolve() not in pagina.resolve().parents:
                return None
            return pagina.read_bytes()
        except Exception as error:
            log.debug("No se ha podido sacar %s del cómic: %s", interna, error)
            return None


def _es_zip(destino: Path) -> bool:
    """Indica si el archivo es un ZIP por dentro, mire lo que mire el nombre."""
    try:
        return zipfile.is_zipfile(str(destino))
    except OSError:
        return False


def _es_pagina(nombre: str) -> bool:
    """Indica si una entrada del archivo es una página del cómic."""
    if nombre.endswith("/"):
        return False
    base = posixpath.basename(nombre)
    if base.startswith(".") or base.startswith("__MACOSX"):
        return False
    return posixpath.splitext(base)[1].lower() in IMAGENES


def _orden_natural(nombre: str) -> tuple:
    """Ordena «pagina2» antes que «pagina10», que es lo que espera cualquiera.

    Ordenar por texto pondría la diez antes que la dos, y un cómic leído en ese
    orden no se entiende.  Se parte el nombre en trozos de letras y de números
    y los números se comparan como números.
    """
    trozos = re.split(r"(\d+)", nombre.lower())
    return tuple(int(trozo) if trozo.isdigit() else trozo for trozo in trozos)


registrar(AnalizadorComic())
