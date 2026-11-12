# -*- coding: utf-8 -*-
"""Seguir donde lo dejaste, en otro equipo.

Quien lee en el ordenador de casa y en el del trabajo pierde cada día lo mismo:
por dónde iba, los marcadores que puso y las notas que escribió.  Y quien lleva
el programa en un pendrive lo tiene resuelto por accidente —los datos van en el
propio pendrive—, pero solo mientras no use el programa instalado en otro sitio.

**No hace falta una nube propia.**  Basta con guardar esos datos en una carpeta
que el usuario ya sincronice por su cuenta: Dropbox, OneDrive, Drive, Nextcloud,
un pendrive o una carpeta de red.  El programa deja ahí una copia, la lee al
arrancar y junta lo que haya llegado de otro equipo.  Eso encaja con que el
programa sea portátil y no obliga a montar ningún servicio, a crear ninguna
cuenta ni a mandar nada a ningún sitio.

Qué se sincroniza
-----------------

Lo que duele perder y solo eso:

* **Por dónde va cada libro**, sus marcadores, sus notas y sus resaltados
  (``documentos.json``).
* **Las descripciones de imágenes** hechas con inteligencia artificial, que
  cuestan tiempo y a veces cuota.
* **Las correcciones** que se hayan hecho sobre la estructura de un documento.

No se sincronizan las preferencias.  Es deliberado: la voz, la velocidad y los
atajos son **de cada equipo**, y llevárselos de uno a otro suele estropear más
que arreglar —la voz que hay en casa no está instalada en el trabajo—.

Cómo se juntan dos versiones
----------------------------

Sin preguntar nada y sin perder nada, con dos reglas:

1. **Libro por libro, gana el más reciente.**  Cada libro guarda cuándo se tocó
   por última vez; al juntar, de cada libro se conserva la versión más nueva.
   Así, leer por la mañana en un equipo y por la tarde en otro deja bien los
   dos, en vez de que el último en cerrarse borre lo del otro.
2. **Los marcadores se suman.**  Si un libro se ha tocado en los dos sitios, se
   quedan los marcadores de ambos: perder un marcador que costó poner es peor
   que tener uno repetido, y los repetidos se reconocen porque ocupan el mismo
   sitio y se quitan solos.

Los archivos de descripciones y de correcciones se copian en la dirección en
que sean más nuevos, que para un archivo por libro es exactamente lo mismo.

Si algo va mal —la carpeta no está, el pendrive no está enchufado, no hay
permiso— **no pasa nada**: se anota en el registro y el programa sigue con sus
datos locales, que es lo que hay que hacer.
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path

from . import rutas
from .configuracion import DatosDocumento, escribir_json, leer_json
from .idioma import _
from .registro import obtener_registro

log = obtener_registro(__name__)

#: Nombre de la subcarpeta que el programa crea dentro de la que elija el
#: usuario.  Se crea una propia para no mezclarse con lo que ya haya ahí.
CARPETA = "VisorUniversal"

#: Nombre del archivo con la posición, los marcadores y las notas.
DOCUMENTOS = "documentos.json"

#: Subcarpetas que se copian entera a entera, archivo por archivo.
COPIADAS = ("descripciones", "correcciones")


def carpeta_de(configuracion) -> Path | None:
    """La carpeta de sincronización, o ``None`` si no hay ninguna puesta."""
    valor = str(configuracion.obtener("sincronizacion_carpeta", "") or "").strip()
    if not valor:
        return None
    return Path(valor) / CARPETA


def activa(configuracion) -> bool:
    """Indica si la sincronización está puesta y se puede usar."""
    destino = carpeta_de(configuracion)
    if destino is None:
        return False
    try:
        destino.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        log.warning("No se puede usar la carpeta de sincronización: %s", error)
        return False
    return True


# ---------------------------------------------------------------------------
# Juntar los datos de los libros
# ---------------------------------------------------------------------------

def _cuando(datos: dict) -> float:
    """Cuándo se tocó por última vez lo guardado de un libro."""
    try:
        return float(datos.get("actualizado", 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def _juntar_marcadores(unos: list, otros: list) -> list:
    """Suma dos listas de marcadores quitando los que son el mismo.

    Dos marcadores son el mismo si señalan el mismo tramo.  Cuando uno de los
    dos lleva nota y el otro no, se queda el que la lleva: la nota es trabajo
    del usuario y el marcador vacío no es nada.
    """
    por_sitio: dict = {}
    for marcador in list(unos) + list(otros):
        clave = (int(marcador.get("inicio", 0)), int(marcador.get("fin", 0)),
                 bool(marcador.get("resaltado", False)))
        anterior = por_sitio.get(clave)
        if anterior is None or (not str(anterior.get("nota", "")).strip()
                                and str(marcador.get("nota", "")).strip()):
            por_sitio[clave] = marcador
    return [por_sitio[clave] for clave in sorted(por_sitio)]


def juntar(local: dict, remoto: dict) -> dict:
    """Junta dos ``documentos.json`` y devuelve el resultado.

    Es una función pura para poder probarla sola: recibe dos diccionarios y
    devuelve uno, sin tocar el disco.
    """
    salida = dict(remoto)
    for ruta, datos in local.items():
        otro = remoto.get(ruta)
        if otro is None:
            salida[ruta] = datos
            continue
        # El más reciente manda en la posición y en los datos sueltos; los
        # marcadores se suman siempre, vengan de donde vengan.
        gana = datos if _cuando(datos) >= _cuando(otro) else otro
        pierde = otro if gana is datos else datos
        juntado = dict(gana)
        juntado["marcadores"] = _juntar_marcadores(
            gana.get("marcadores") or [], pierde.get("marcadores") or [])
        # De la pronunciación se queda la del más reciente, salvo que no tenga
        # ninguna: una lista vacía no debe borrar el diccionario del otro.
        if not juntado.get("pronunciacion") and pierde.get("pronunciacion"):
            juntado["pronunciacion"] = pierde["pronunciacion"]
        salida[ruta] = juntado
    return salida


def _copiar_si_es_mas_nuevo(origen: Path, destino: Path) -> bool:
    """Copia un archivo solo si el de origen es más reciente."""
    try:
        if not origen.is_file():
            return False
        if destino.exists() and destino.stat().st_mtime >= origen.stat().st_mtime:
            return False
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origen, destino)
        return True
    except OSError as error:
        log.debug("No se ha podido copiar %s: %s", origen.name, error)
        return False


def _sincronizar_carpeta(local: Path, remota: Path) -> tuple[int, int]:
    """Deja las dos carpetas con lo más nuevo de cada archivo.

    :return: ``(traídos, llevados)``.
    """
    traidos = llevados = 0
    try:
        remota.mkdir(parents=True, exist_ok=True)
        local.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        log.warning("No se ha podido preparar %s: %s", remota, error)
        return 0, 0
    for archivo in list(remota.glob("*.json")):
        if _copiar_si_es_mas_nuevo(archivo, local / archivo.name):
            traidos += 1
    for archivo in list(local.glob("*.json")):
        if _copiar_si_es_mas_nuevo(archivo, remota / archivo.name):
            llevados += 1
    return traidos, llevados


# ---------------------------------------------------------------------------
# Las dos operaciones que ve el resto del programa
# ---------------------------------------------------------------------------

class Resultado:
    """Lo que ha pasado al sincronizar, para poder contarlo."""

    __slots__ = ("libros", "traidos", "llevados", "error")

    def __init__(self, libros: int = 0, traidos: int = 0, llevados: int = 0,
                 error: str = "") -> None:
        self.libros = libros
        self.traidos = traidos
        self.llevados = llevados
        self.error = error

    def __bool__(self) -> bool:
        """Cierto si ha ido bien."""
        return not self.error

    def frase(self) -> str:
        """Cómo se cuenta en voz alta lo que ha ocurrido."""
        if self.error:
            return _("No se ha podido sincronizar: %s") % self.error
        if not (self.libros or self.traidos or self.llevados):
            return _("Sincronización al día: no había nada nuevo.")
        return _("Sincronizado: %(libros)d libros, %(traidos)d archivos traídos y "
                 "%(llevados)d llevados.") % {
            "libros": self.libros, "traidos": self.traidos, "llevados": self.llevados}


def sincronizar(configuracion) -> Resultado:
    """Junta los datos locales con los de la carpeta compartida.

    Se llama al arrancar y al cerrar, y también a mano desde las opciones.
    Después de esta llamada, **las dos partes tienen lo mismo**.
    """
    destino = carpeta_de(configuracion)
    if destino is None:
        return Resultado()
    try:
        destino.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        return Resultado(error=str(error))

    local = rutas.ruta_config() / DOCUMENTOS
    remoto = destino / DOCUMENTOS
    datos_local = leer_json(local, {})
    datos_remoto = leer_json(remoto, {})
    if not isinstance(datos_local, dict):
        datos_local = {}
    if not isinstance(datos_remoto, dict):
        datos_remoto = {}

    juntado = juntar(datos_local, datos_remoto)
    cambiados = sum(1 for ruta in juntado
                    if juntado[ruta] != datos_local.get(ruta))
    try:
        if juntado != datos_local:
            escribir_json(local, juntado)
        if juntado != datos_remoto:
            escribir_json(remoto, juntado)
    except OSError as error:
        return Resultado(error=str(error))

    traidos = llevados = 0
    for nombre in COPIADAS:
        unos, otros = _sincronizar_carpeta(rutas.subcarpeta(nombre), destino / nombre)
        traidos += unos
        llevados += otros

    # Lo que se acaba de traer de fuera hay que releerlo: la configuración se
    # cargó al arrancar y no sabe nada de esto.
    configuracion.recargar_documentos()
    log.info("Sincronización con %s: %d libros, %d traídos, %d llevados",
             destino, cambiados, traidos, llevados)
    return Resultado(cambiados, traidos, llevados)


def marcar_ahora(datos: DatosDocumento) -> None:
    """Anota que lo guardado de un libro se acaba de tocar.

    Sin esta marca no habría forma de saber cuál de dos versiones es la buena,
    y juntar dos equipos se convertiría en «gana el último que cierre».
    """
    datos.actualizado = time.time()
