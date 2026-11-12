# -*- coding: utf-8 -*-
"""Descripciones de imágenes guardadas, una colección por libro.

Pedirle a la IA que describa una ilustración cuesta tiempo y, con Gemini,
cuota.  Volver a pedir lo mismo cada vez que se pasa por la misma imagen sería
absurdo, así que las descripciones se guardan en disco y **viajan con el
libro**: al abrirlo otra vez ya están ahí, y al llegar a la imagen se anuncia
la que se hizo en su día.  Quien quiera otra siempre puede pedirla de nuevo.

Cada libro tiene su propio archivo JSON en ``data/descripciones``, con el
nombre calculado a partir de la ruta del EPUB.  Guardarlo aparte, y no dentro
de ``documentos.json``, tiene dos motivos: las descripciones son largas y no
conviene releerlas todas al arrancar, y así se pueden borrar las de un libro
concreto sin tocar los marcadores ni las posiciones de lectura.

La clave de cada descripción es la **referencia** de la imagen: la ruta del
archivo dentro del EPUB (``OEBPS/images/lamina_03.jpg``).  Es estable entre
aperturas y única dentro del libro, aunque la misma imagen salga varias veces.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path

from . import rutas
from .configuracion import escribir_json, leer_json
from .registro import obtener_registro

log = obtener_registro(__name__)

#: Versión del formato del archivo.  Si algún día cambia la forma de guardar,
#: subirla hace que las colecciones viejas se descarten sin dar guerra.
VERSION = 1


def _archivo_de(ruta_libro: str) -> Path:
    """Devuelve el archivo de descripciones que corresponde a un libro."""
    huella = hashlib.sha1(str(ruta_libro).lower().encode("utf-8")).hexdigest()
    return rutas.subcarpeta("descripciones") / ("%s.json" % huella)


class Descripcion:
    """Una descripción hecha por la IA, con los datos de cómo se hizo.

    Se guarda el prompt y el modelo porque, al releerla meses después, saber
    con qué se generó explica por qué dice lo que dice, y permite decidir si
    conviene volver a pedirla con otro prompt.
    """

    __slots__ = ("texto", "prompt", "modelo", "fecha",
                 "datos", "datos_titulo", "datos_unidades", "datos_nota",
                 "datos_fiabilidad", "datos_por_que")

    def __init__(self, texto: str, prompt: str = "", modelo: str = "", fecha: str = "",
                 datos: str = "", datos_titulo: str = "", datos_unidades: str = "",
                 datos_nota: str = "", datos_fiabilidad: str = "",
                 datos_por_que: str = "") -> None:
        self.texto = texto
        self.prompt = prompt
        self.modelo = modelo
        self.fecha = fecha or time.strftime("%Y-%m-%d %H:%M")
        # Los datos del gráfico, cuando se han sacado.  Van junto a la
        # descripción y no en otro archivo porque son de la misma imagen y se
        # piden en el mismo sitio: separarlos obligaría a leer dos archivos
        # para enseñar una figura.  La rejilla se guarda con las filas
        # separadas por saltos de línea y las celdas por tabuladores, igual que
        # las tablas del libro.
        self.datos = datos
        self.datos_titulo = datos_titulo
        self.datos_unidades = datos_unidades
        self.datos_nota = datos_nota
        #: Hasta qué punto la IA se fía de lo que ha leído en el gráfico, y por
        #: qué. Va con los datos y no aparte porque **es parte del dato**: un
        #: número estimado y uno leído no valen lo mismo en un trabajo.
        self.datos_fiabilidad = datos_fiabilidad
        self.datos_por_que = datos_por_que

    @property
    def tiene_datos(self) -> bool:
        """Indica si de esta imagen se sacó una tabla de datos."""
        return bool((self.datos or "").strip())

    def esquema(self):
        """Devuelve el diagrama guardado, o ``None`` si lo que hay es una tabla.

        Los dos se guardan en el mismo campo porque para una imagen solo puede
        haber una de las dos cosas: o tiene valores que caben en una tabla o
        tiene estructura de cajas y flechas.  Lo guardado lleva su marca delante
        para saber cuál es.
        """
        from . import esquemas

        salida = esquemas.desde_guardado(self.datos)
        if salida is not None:
            salida.titulo = self.datos_titulo
            salida.tipo = salida.tipo or self.datos_unidades
            salida.nota = self.datos_nota
            salida.fiabilidad = self.datos_fiabilidad
            salida.por_que = self.datos_por_que
        return salida

    def grafico(self):
        """Devuelve los datos como :class:`~nucleo.graficos.Grafico`, o ``None``."""
        from . import esquemas, graficos

        if esquemas.es_esquema(self.datos):
            # Lo guardado es un diagrama, no una tabla: leerlo como rejilla
            # daría una tabla de tres columnas que no significa nada.
            return None
        salida = graficos.desde_guardado(self.datos)
        if salida is not None:
            salida.titulo = self.datos_titulo
            salida.unidades = self.datos_unidades
            salida.nota = self.datos_nota
            salida.fiabilidad = self.datos_fiabilidad
            salida.por_que = self.datos_por_que
        return salida

    def como_dict(self) -> dict:
        """Representación para guardar en JSON.

        Lo del gráfico solo se escribe cuando lo hay: así el archivo de quien
        nunca haya sacado datos sigue siendo exactamente el de antes.
        """
        contenido = {"texto": self.texto, "prompt": self.prompt,
                     "modelo": self.modelo, "fecha": self.fecha}
        if self.tiene_datos:
            contenido["datos"] = self.datos
            for clave, valor in (("datos_titulo", self.datos_titulo),
                                 ("datos_unidades", self.datos_unidades),
                                 ("datos_nota", self.datos_nota),
                                 ("datos_fiabilidad", self.datos_fiabilidad),
                                 ("datos_por_que", self.datos_por_que)):
                if valor:
                    contenido[clave] = valor
        return contenido

    @classmethod
    def desde_dict(cls, datos: dict) -> "Descripcion":
        """Reconstruye una descripción a partir del JSON."""
        return cls(str(datos.get("texto", "")), str(datos.get("prompt", "")),
                   str(datos.get("modelo", "")), str(datos.get("fecha", "")),
                   str(datos.get("datos", "")), str(datos.get("datos_titulo", "")),
                   str(datos.get("datos_unidades", "")),
                   str(datos.get("datos_nota", "")),
                   str(datos.get("datos_fiabilidad", "")),
                   str(datos.get("datos_por_que", "")))

    def resumen(self) -> str:
        """Frase con la procedencia, para enseñarla debajo del texto."""
        partes = [parte for parte in (self.modelo, self.prompt, self.fecha) if parte]
        return " · ".join(partes)


class Coleccion:
    """Las descripciones de un libro, cargadas en memoria.

    Se guarda en disco en cuanto cambia algo, y no al cerrar: describir una
    imagen es lento y caro, y perder el resultado porque el programa se cerrara
    de forma anómala sería un fastidio evitable.

    :param ruta_libro: Archivo EPUB al que pertenecen.  Con la cadena vacía se
                       obtiene una colección en memoria que no llega a
                       guardarse, cómoda cuando todavía no hay libro abierto.
    """

    def __init__(self, ruta_libro: str = "") -> None:
        self.ruta_libro = str(ruta_libro or "")
        self._descripciones: dict[str, Descripcion] = {}
        self._cerrojo = threading.Lock()
        if self.ruta_libro:
            self._cargar()

    # -- disco ---------------------------------------------------------------

    def _cargar(self) -> None:
        """Lee del disco las descripciones guardadas de este libro."""
        contenido = leer_json(_archivo_de(self.ruta_libro), {})
        if not isinstance(contenido, dict) or contenido.get("version") != VERSION:
            return
        for referencia, datos in (contenido.get("descripciones") or {}).items():
            if isinstance(datos, dict):
                self._descripciones[str(referencia)] = Descripcion.desde_dict(datos)
        if self._descripciones:
            log.info("Recuperadas %d descripciones de imágenes del libro",
                     len(self._descripciones))

    def _guardar(self) -> None:
        """Vuelca al disco lo que hay en memoria."""
        if not self.ruta_libro:
            return
        contenido = {
            "version": VERSION,
            "libro": self.ruta_libro,
            "descripciones": {referencia: descripcion.como_dict()
                              for referencia, descripcion in self._descripciones.items()},
        }
        try:
            escribir_json(_archivo_de(self.ruta_libro), contenido)
        except OSError as error:
            log.warning("No se han podido guardar las descripciones: %s", error)

    # -- consulta y cambio ---------------------------------------------------

    def obtener(self, referencia: str) -> Descripcion | None:
        """Devuelve la descripción guardada de una imagen, si la hay."""
        with self._cerrojo:
            return self._descripciones.get(str(referencia or ""))

    def guardar(self, referencia: str, descripcion: Descripcion) -> None:
        """Guarda (o reemplaza) la descripción de una imagen."""
        referencia = str(referencia or "")
        if not referencia:
            return
        with self._cerrojo:
            self._descripciones[referencia] = descripcion
            self._guardar()

    def olvidar(self, referencia: str) -> bool:
        """Borra la descripción de una imagen.  Devuelve si había alguna."""
        with self._cerrojo:
            existia = self._descripciones.pop(str(referencia or ""), None) is not None
            if existia:
                self._guardar()
        return existia

    def vaciar(self) -> int:
        """Borra todas las descripciones del libro.  Devuelve cuántas eran."""
        with self._cerrojo:
            cuantas = len(self._descripciones)
            self._descripciones.clear()
            self._guardar()
        return cuantas

    def __len__(self) -> int:
        """Número de descripciones guardadas de este libro."""
        with self._cerrojo:
            return len(self._descripciones)


def tamano_total() -> int:
    """Cuánto ocupan en disco las descripciones de todos los libros."""
    carpeta = rutas.subcarpeta("descripciones")
    total = 0
    for archivo in carpeta.glob("*.json"):
        try:
            total += archivo.stat().st_size
        except OSError:
            continue
    return total


def vaciar_todo() -> int:
    """Borra las descripciones de todos los libros.  Devuelve cuántos archivos."""
    carpeta = rutas.subcarpeta("descripciones")
    borrados = 0
    for archivo in carpeta.glob("*.json"):
        try:
            archivo.unlink()
            borrados += 1
        except OSError as error:
            log.warning("No se ha podido borrar %s: %s", archivo, error)
    log.info("Descripciones borradas: %d archivos", borrados)
    return borrados


def archivo_de(ruta_libro: str) -> Path:
    """Archivo donde viven las descripciones de un libro."""
    return _archivo_de(ruta_libro)


def datos_de(ruta_libro: str) -> tuple[int, int]:
    """Cuántas descripciones tiene guardadas un libro y cuánto ocupan."""
    archivo = _archivo_de(ruta_libro)
    if not archivo.exists():
        return 0, 0
    try:
        tamano = archivo.stat().st_size
        contenido = json.loads(archivo.read_text(encoding="utf-8"))
        cuantas = len(contenido.get("descripciones", contenido) or {})
        return cuantas, tamano
    except Exception as error:
        log.debug("No se han podido contar las descripciones de %s: %s", ruta_libro, error)
        return 0, 0


def olvidar_libro(ruta_libro: str) -> bool:
    """Borra las descripciones de un libro concreto.

    Hace falta poder hacerlo por separado: quien vuelve a analizar un libro no
    quiere perder por el camino las descripciones que le costaron una petición
    a la IA cada una.

    :return: Si había algo que borrar.
    """
    archivo = _archivo_de(ruta_libro)
    try:
        if archivo.exists():
            archivo.unlink()
            log.info("Descripciones de %s borradas", ruta_libro)
            return True
    except OSError as error:
        log.warning("No se ha podido borrar %s: %s", archivo, error)
    return False
