# -*- coding: utf-8 -*-
"""Caché de libros ya analizados.

Analizar un libro grande cuesta alrededor de un segundo.  Guardar el
resultado permite que la **segunda vez** que se abre ese mismo libro aparezca
de forma prácticamente instantánea.

Cómo funciona:

* La clave de la caché combina la ruta del archivo, su fecha de modificación,
  su tamaño, los ajustes de análisis y la versión del formato de caché.  Si
  cualquiera de esos datos cambia, la entrada deja de ser válida y el libro se
  vuelve a analizar: es imposible mostrar contenido desfasado.
* Se guarda solo información elemental (texto, tuplas y diccionarios), no los
  objetos de la aplicación.  Así una futura reorganización del código no
  invalida los archivos ya guardados, y leerlos es más rápido.
* La carpeta se limita en tamaño: cuando se supera, se borran las entradas
  que llevan más tiempo sin usarse.
"""

from __future__ import annotations

import hashlib
import os
import pickle
import threading
from pathlib import Path
from typing import Any

from . import rutas
from .documento import Documento, ElementoIndice, Metadatos, Seccion
from .marcas import Marca, TipoMarca
from .registro import cronometro, obtener_registro, registrar_excepcion

log = obtener_registro(__name__)

#: Versión del formato de la caché.  Al cambiarla se invalidan todas las
#: entradas anteriores, que es lo que hay que hacer si cambia el conversor.
#: La 5 llega con los libros DAISY: ahora el texto se monta siguiendo el orden
#: del SMIL y lleva las anclas que lo atan a la grabación, así que un documento
#: guardado por la versión anterior ya no vale.  La 6, con las fórmulas
#: matemáticas: un libro analizado antes las tiraba, y su caché las seguiría
#: escondiendo por buena que sea la conversión nueva.  La 7, con las llamadas
#: de nota al pie, que antes eran enlaces indistinguibles de los demás.  La 8,
#: con la estructura de los PDF etiquetados: un PDF accesible guardado por la
#: versión anterior está en la caché como un churro de líneas sin encabezados,
#: sin tablas y con el encabezado de página repetido en cada una.
VERSION_CACHE = 8

#: Tamaño máximo que puede ocupar la carpeta de caché, en bytes.
LIMITE_BYTES = 400 * 1024 * 1024

_cerrojo = threading.Lock()


def _clave(ruta: Path, firma_opciones: str) -> str:
    """Calcula el nombre del archivo de caché correspondiente a un libro."""
    try:
        estado = ruta.stat()
        huella = "%s|%d|%d|%s|%d" % (
            str(ruta.resolve()).lower(), estado.st_mtime_ns, estado.st_size,
            firma_opciones, VERSION_CACHE,
        )
    except OSError:
        huella = "%s|%s|%d" % (str(ruta).lower(), firma_opciones, VERSION_CACHE)
    return hashlib.sha1(huella.encode("utf-8")).hexdigest() + ".cache"


def _indice_a_datos(entradas: list[ElementoIndice]) -> list:
    """Convierte el árbol del índice en listas y tuplas simples."""
    return [
        (entrada.titulo, entrada.posicion, entrada.referencia, _indice_a_datos(entrada.hijos))
        for entrada in entradas
    ]


def _datos_a_indice(datos: list) -> list[ElementoIndice]:
    """Reconstruye el árbol del índice a partir de listas y tuplas simples."""
    return [
        ElementoIndice(titulo, posicion, referencia, _datos_a_indice(hijos))
        for titulo, posicion, referencia, hijos in datos
    ]


def guardar(documento: Documento, firma_opciones: str) -> None:
    """Guarda en la caché el resultado del análisis de un libro.

    Los fallos al escribir se registran pero no se propagan: la caché es una
    optimización, y que falle nunca debe impedir leer el libro.
    """
    ruta = Path(documento.ruta_archivo)
    if not ruta.exists():
        return
    destino = rutas.ruta_cache() / _clave(ruta, firma_opciones)
    contenido: dict[str, Any] = {
        "version": VERSION_CACHE,
        "origen": str(ruta),
        "texto": documento.texto,
        "marcas": [tuple(marca) for marca in documento.marcas.todas()],
        "indice": _indice_a_datos(documento.indice),
        "posiciones_id": documento.posiciones_id,
        "secciones": [
            (seccion.ruta, seccion.inicio, seccion.fin, seccion.titulo)
            for seccion in documento.secciones
        ],
        "metadatos": vars(documento.metadatos),
    }
    try:
        with cronometro(log, "guardado en cache"):
            temporal = destino.with_suffix(".tmp")
            with open(temporal, "wb") as archivo:
                pickle.dump(contenido, archivo, protocol=pickle.HIGHEST_PROTOCOL)
            os.replace(temporal, destino)
            # Al lado, la ruta del libro en texto plano.  Parece redundante
            # —ya va dentro— pero no lo es: sin esto, saber a qué libro
            # pertenece cada entrada obligaria a deserializar el documento
            # entero de cada una, y eso es justo lo que la caché evita.
            destino.with_suffix(".origen").write_text(str(ruta), encoding="utf-8")
        _limitar_tamano()
    except Exception as error:
        registrar_excepcion(log, "No se ha podido guardar la caché de %s" % ruta.name, error)


def cargar(ruta_libro: str | os.PathLike, firma_opciones: str) -> Documento | None:
    """Recupera de la caché un libro ya analizado, o ``None`` si no está.

    :param ruta_libro: Ruta del archivo original.
    :param firma_opciones: Firma de los ajustes de análisis en uso.
    """
    ruta = Path(ruta_libro)
    origen = rutas.ruta_cache() / _clave(ruta, firma_opciones)
    if not origen.exists():
        return None
    try:
        with cronometro(log, "lectura de la cache") as datos:
            with open(origen, "rb") as archivo:
                contenido = pickle.load(archivo)
            if contenido.get("version") != VERSION_CACHE:
                return None
            documento = Documento(
                texto=contenido["texto"],
                marcas=[Marca(TipoMarca(t[0]), *t[1:]) for t in contenido["marcas"]],
                indice=_datos_a_indice(contenido["indice"]),
                posiciones_id=contenido["posiciones_id"],
                secciones=[Seccion(*s) for s in contenido["secciones"]],
                metadatos=Metadatos(**contenido["metadatos"]),
                ruta_archivo=str(ruta),
            )
            datos["caracteres"] = len(documento.texto)
        # Marcar la entrada como usada para que la limpieza respete su orden.
        os.utime(origen, None)
        log.info("Libro recuperado de la caché: %s", ruta.name)
        return documento
    except Exception as error:
        registrar_excepcion(log, "Caché ilegible para %s; se volverá a analizar" % ruta.name, error)
        try:
            origen.unlink()
        except OSError:
            pass
        return None


def _limitar_tamano() -> None:
    """Borra las entradas más antiguas si la caché supera su límite."""
    with _cerrojo:
        carpeta = rutas.ruta_cache()
        archivos = []
        total = 0
        for elemento in carpeta.glob("*.cache"):
            try:
                estado = elemento.stat()
            except OSError:
                continue
            archivos.append((estado.st_atime, estado.st_size, elemento))
            total += estado.st_size
        if total <= LIMITE_BYTES:
            return
        archivos.sort()  # los de acceso más antiguo, primero
        for _, tamano, elemento in archivos:
            if total <= LIMITE_BYTES:
                break
            try:
                elemento.unlink()
                elemento.with_suffix(".origen").unlink(missing_ok=True)
                total -= tamano
                log.debug("Entrada de caché eliminada: %s", elemento.name)
            except OSError:
                continue


def vaciar() -> int:
    """Borra toda la caché.  Devuelve el número de archivos eliminados."""
    eliminados = 0
    for elemento in rutas.ruta_cache().glob("*.cache"):
        try:
            elemento.unlink()
            elemento.with_suffix(".origen").unlink(missing_ok=True)
            eliminados += 1
        except OSError:
            continue
    log.info("Caché vaciada: %d archivos eliminados", eliminados)
    return eliminados


def tamano_actual() -> int:
    """Espacio que ocupa la caché, en bytes."""
    total = 0
    for elemento in rutas.ruta_cache().glob("*.cache"):
        try:
            total += elemento.stat().st_size
        except OSError:
            continue
    return total


def entradas() -> list[tuple[str, Path, int]]:
    """Lista lo que hay guardado en la caché y de qué libro es cada cosa.

    Al lado de cada entrada hay un archivo ``.origen`` con la ruta del libro en
    texto plano.  Si falta —porque la entrada la escribió una versión anterior—
    se abre la entrada y se recupera de dentro, escribiendo el ``.origen`` para
    no tener que repetirlo.

    :return: Tripletas ``(ruta_del_libro, archivo, bytes)``.  La ruta va vacía
             si no se ha podido averiguar.
    """
    encontradas: list[tuple[str, Path, int]] = []
    for elemento in sorted(rutas.ruta_cache().glob("*.cache")):
        try:
            tamano = elemento.stat().st_size
        except OSError:
            continue
        nota = elemento.with_suffix(".origen")
        origen = ""
        try:
            if nota.exists():
                origen = nota.read_text(encoding="utf-8").strip()
            else:
                with open(elemento, "rb") as archivo:
                    origen = str(pickle.load(archivo).get("origen", ""))
                if origen:
                    nota.write_text(origen, encoding="utf-8")
        except Exception as error:
            log.debug("No se ha podido saber de qué libro es %s: %s", elemento.name, error)
        encontradas.append((origen, elemento, tamano))
    return encontradas


def datos_de(ruta_libro: str) -> tuple[int, int]:
    """Cuántas entradas de caché tiene un libro y cuánto ocupan.

    Un mismo libro puede tener varias: una por cada combinación de ajustes con
    la que se haya abierto.
    """
    buscada = str(ruta_libro).lower()
    cuantas = tamano = 0
    for origen, _archivo, bytes_ in entradas():
        if origen.lower() == buscada:
            cuantas += 1
            tamano += bytes_
    return cuantas, tamano


def olvidar(ruta_libro: str) -> int:
    """Borra de la caché lo guardado de un libro concreto.

    Es lo que permite decir «vuelve a analizar este libro desde cero» sin tirar
    el trabajo hecho con todos los demás, que es lo que hace vaciar la caché
    entera.

    :return: Cuántas entradas se han borrado.
    """
    buscada = str(ruta_libro).lower()
    borrados = 0
    for origen, archivo, _bytes in entradas():
        if origen.lower() != buscada:
            continue
        try:
            archivo.unlink()
            archivo.with_suffix(".origen").unlink(missing_ok=True)
            borrados += 1
        except OSError as error:
            log.warning("No se ha podido borrar %s: %s", archivo, error)
    if borrados:
        log.info("Caché de %s olvidada: %d entradas", ruta_libro, borrados)
    return borrados


def sobrantes() -> list[tuple[str, Path, int]]:
    """Entradas cuyo libro ya no está donde estaba.

    Se acumulan sin que nadie se dé cuenta: libros que se movieron, se
    renombraron o se borraron, y cuya caché se queda ocupando sitio para
    siempre porque ya nunca se va a pedir.
    """
    return [(origen, archivo, tamano) for origen, archivo, tamano in entradas()
            if not origen or not Path(origen).exists()]
