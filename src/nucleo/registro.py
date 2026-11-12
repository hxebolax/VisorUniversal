# -*- coding: utf-8 -*-
"""Sistema de registro (logging) avanzado.

Objetivo: que **cualquier problema** que tenga la aplicación quede reflejado
en los archivos de registro, sin necesidad de reproducirlo con un depurador.

Qué aporta este módulo sobre el ``logging`` estándar:

* **Un registro nuevo por cada sesión** en ``data/logs``, con la fecha y la
  hora en el nombre:

  - ``sesion_20260828-193045.log``: todo (según el nivel configurado).
  - ``errores_20260828-193045.log``: solo ``ERROR`` y ``CRITICAL``.

  Se conservan los **cinco más recientes** de cada clase y se borran los
  anteriores.  Así el registro de un problema no queda enterrado bajo el uso
  posterior, como pasaría con un único archivo que crece sin fin, y la carpeta
  tampoco se llena.

* **Cabecera de sesión** con la versión del programa, de Python, de wxPython,
  del sistema operativo, memoria y línea de órdenes.  Sin esto, un informe de
  fallo de un usuario es casi inútil.
* **Captura de excepciones no controladas** en el hilo principal
  (``sys.excepthook``), en hilos secundarios (``threading.excepthook``) y de
  los objetos que fallan al destruirse (``sys.unraisablehook``).
* **Redirección de los mensajes de wxWidgets** al registro, de modo que los
  avisos internos de la biblioteca gráfica también queden guardados.
* Utilidades de medición de tiempos (:func:`cronometro` y :func:`cronometrar`)
  para detectar cuellos de botella de rendimiento.

Uso normal desde cualquier módulo::

    from nucleo.registro import obtener_registro
    log = obtener_registro(__name__)
    log.info("Mensaje")
"""

from __future__ import annotations

import functools
import glob
import logging
import os
import platform
import sys
import threading
import time
import traceback
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

from . import rutas
from version import NOMBRE

#: Nombre del registrador raíz de la aplicación.  Todos los módulos cuelgan de él.
NOMBRE_RAIZ = "visor"

#: Formato detallado usado en los archivos.
FORMATO_ARCHIVO = (
    "%(asctime)s | %(levelname)-8s | %(name)-30s | "
    "%(threadName)-14s | %(funcName)s:%(lineno)d | %(message)s"
)

#: Formato compacto usado en la consola (solo en modo desarrollo).
FORMATO_CONSOLA = "%(levelname)-8s | %(name)-26s | %(message)s"

#: Número de registros de sesión que se conservan de cada clase.
SESIONES_CONSERVADAS = 5

#: Niveles admitidos, en el orden en que se ofrecen en el diálogo de opciones.
NIVELES = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")

_ruta_aplicacion: Path | None = None
_ruta_errores: Path | None = None


# ---------------------------------------------------------------------------
# Inicialización
# ---------------------------------------------------------------------------

#: Hilos que trabajan con miles de libros seguidos: buscar en todos, abrir los
#: libros incompletos de la bibliografía, palabras relacionadas...
HILOS_MASIVOS = frozenset(("biblioteca-tarea", "biblioteca"))

#: Módulos que cuentan con detalle cómo se analiza cada libro.
_DETALLE_DE_ANALISIS = (NOMBRE_RAIZ + ".formatos.", NOMBRE_RAIZ + ".nucleo.cache")


class _SinDetalleEnTrabajosMasivos(logging.Filter):
    """Calla el detalle de análisis de cada libro dentro de un trabajo masivo.

    Abrir un libro deja en la sesión unas siete líneas de información (qué se
    analiza, cuánto tarda cada paso, cuánto ocupa). Con uno es útil; con los
    miles que abre «Buscar en todos» o la bibliografía, son decenas de megas
    que esconden lo que de verdad importa. En esos hilos se deja pasar solo lo
    que es un aviso o un error. Con el nivel de registro en DEBUG no se aplica:
    quien lo pone es porque quiere verlo todo.
    """

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003 (nombre de logging)
        if record.levelno >= logging.WARNING or record.threadName not in HILOS_MASIVOS:
            return True
        return not record.name.startswith(_DETALLE_DE_ANALISIS)


def iniciar(nivel: str = "INFO", version: str = "?", consola: bool | None = None) -> logging.Logger:
    """Prepara el sistema de registro.  Debe llamarse una sola vez al arrancar.

    :param nivel: Nivel mínimo que se escribe en ``aplicacion.log``.
    :param version: Versión de la aplicación, para la cabecera de sesión.
    :param consola: Si se escribe también por consola.  Por omisión, solo
                    cuando la aplicación **no** está compilada.
    :return: El registrador raíz de la aplicación.
    """
    global _ruta_aplicacion, _ruta_errores

    carpeta = rutas.ruta_logs()
    _limpiar_registros_antiguos(carpeta)
    marca = time.strftime("%Y%m%d-%H%M%S")
    _ruta_aplicacion = carpeta / ("sesion_%s.log" % marca)
    _ruta_errores = carpeta / ("errores_%s.log" % marca)

    raiz = logging.getLogger(NOMBRE_RAIZ)
    raiz.setLevel(logging.DEBUG)  # los filtros reales están en cada manejador
    raiz.propagate = False

    # Al reiniciar el registro (por ejemplo al cambiar el nivel en Opciones)
    # se descartan los manejadores anteriores para no duplicar líneas.
    for manejador in list(raiz.handlers):
        raiz.removeHandler(manejador)
        try:
            manejador.close()
        except Exception:  # pragma: no cover - cierre defensivo
            pass

    formato_archivo = logging.Formatter(FORMATO_ARCHIVO, datefmt="%Y-%m-%d %H:%M:%S")

    manejador_general = logging.FileHandler(_ruta_aplicacion, encoding="utf-8")
    manejador_general.setLevel(_nivel_numerico(nivel))
    manejador_general.setFormatter(formato_archivo)
    if _nivel_numerico(nivel) > logging.DEBUG:
        manejador_general.addFilter(_SinDetalleEnTrabajosMasivos())
    raiz.addHandler(manejador_general)

    manejador_errores = logging.FileHandler(_ruta_errores, encoding="utf-8")
    manejador_errores.setLevel(logging.ERROR)
    manejador_errores.setFormatter(formato_archivo)
    raiz.addHandler(manejador_errores)

    if consola is None:
        consola = not rutas.esta_congelado()
    if consola and sys.stderr is not None:
        manejador_consola = logging.StreamHandler(sys.stderr)
        manejador_consola.setLevel(_nivel_numerico(nivel))
        manejador_consola.setFormatter(logging.Formatter(FORMATO_CONSOLA))
        if _nivel_numerico(nivel) > logging.DEBUG:
            manejador_consola.addFilter(_SinDetalleEnTrabajosMasivos())
        raiz.addHandler(manejador_consola)

    _instalar_capturas()
    _escribir_cabecera(raiz, version)
    return raiz


def _limpiar_registros_antiguos(carpeta: Path) -> None:
    """Deja solo los registros de sesión más recientes y borra los demás.

    Se ejecuta **antes** de crear los de esta sesión, así que en total quedan
    :data:`SESIONES_CONSERVADAS` contando el que está a punto de crearse.

    También borra los archivos del esquema anterior (``aplicacion.log`` y
    ``errores.log`` con sus copias numeradas), que ya no se usan.
    """
    for antiguo in ("aplicacion.log", "errores.log"):
        for sobrante in carpeta.glob(antiguo + "*"):
            try:
                sobrante.unlink()
            except OSError:
                pass
    for patron in ("sesion_*.log", "errores_*.log"):
        archivos = sorted(glob.glob(str(carpeta / patron)), key=os.path.getmtime)
        for sobrante in archivos[:-(SESIONES_CONSERVADAS - 1)] if SESIONES_CONSERVADAS > 1 else archivos:
            try:
                os.remove(sobrante)
            except OSError:
                pass


def _nivel_numerico(nivel: str) -> int:
    """Traduce el nombre de un nivel a su valor numérico, con respaldo ``INFO``."""
    return getattr(logging, str(nivel).upper(), logging.INFO)


def cambiar_nivel(nivel: str) -> None:
    """Cambia en caliente el nivel de detalle del registro general.

    El archivo ``errores.log`` no se ve afectado: siempre recoge los errores.
    """
    raiz = logging.getLogger(NOMBRE_RAIZ)
    numerico = _nivel_numerico(nivel)
    for manejador in raiz.handlers:
        if isinstance(manejador, logging.FileHandler):
            if _ruta_errores is not None and Path(manejador.baseFilename) == _ruta_errores:
                continue  # el registro de errores conserva su nivel propio
        manejador.setLevel(numerico)
    raiz.info("Nivel de registro cambiado a %s", nivel)


def obtener_registro(nombre: str) -> logging.Logger:
    """Devuelve el registrador de un módulo.

    :param nombre: Normalmente ``__name__``.
    """
    limpio = nombre.replace("__main__", "principal")
    return logging.getLogger(NOMBRE_RAIZ + "." + limpio)


def ruta_archivo_registro() -> Path | None:
    """Ruta del archivo de registro general (para el menú de ayuda)."""
    return _ruta_aplicacion


# ---------------------------------------------------------------------------
# Cabecera de sesión
# ---------------------------------------------------------------------------

def _escribir_cabecera(registro: logging.Logger, version: str) -> None:
    """Escribe en el registro los datos del entorno de ejecución.

    Esta información es lo primero que hay que mirar al diagnosticar un
    problema comunicado por un usuario.
    """
    registro.info("=" * 100)
    registro.info("INICIO DE SESION - %s version %s", NOMBRE, version)
    registro.info("Fecha de arranque .. %s", time.strftime("%Y-%m-%d %H:%M:%S"))
    registro.info("Ejecutable ......... %s", sys.executable)
    registro.info("Modo ............... %s", "compilado" if rutas.esta_congelado() else "codigo fuente")
    registro.info("Linea de ordenes ... %s", " ".join(sys.argv))
    registro.info("Carpeta base ....... %s", rutas.directorio_base())
    registro.info("Carpeta de datos ... %s", rutas.directorio_datos())
    registro.info("Python ............. %s (%s)", platform.python_version(), platform.architecture()[0])
    registro.info("Sistema ............ %s %s (%s)", platform.system(), platform.release(), platform.version())
    registro.info("Procesador ......... %s | nucleos: %s", platform.processor(), os.cpu_count())
    registro.info("Codificacion ....... sistema=%s consola=%s", sys.getfilesystemencoding(),
                  getattr(sys.stdout, "encoding", "?"))
    for nombre_modulo in ("wx", "lxml.etree"):
        registro.info("Modulo %-11s %s", nombre_modulo, _version_modulo(nombre_modulo))
    registro.info("Memoria ............ %s", _descripcion_memoria())
    registro.info("=" * 100)


def _version_modulo(nombre: str) -> str:
    """Versión de un módulo opcional, o el motivo por el que no está disponible."""
    try:
        modulo = __import__(nombre, fromlist=["__version__"])
    except Exception as error:  # pragma: no cover - depende del entorno
        return "no disponible (%s)" % error
    for atributo in ("version", "__version__", "VERSION"):
        valor = getattr(modulo, atributo, None)
        if callable(valor):
            try:
                return str(valor())
            except Exception:
                continue
        if valor is not None:
            return str(valor)
    return "version desconocida"


def _descripcion_memoria() -> str:
    """Memoria total y disponible del equipo, si el sistema lo permite."""
    try:
        if sys.platform == "win32":
            import ctypes

            class _Estado(ctypes.Structure):
                """Reflejo de la estructura MEMORYSTATUSEX de la API de Windows."""

                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            estado = _Estado()
            estado.dwLength = ctypes.sizeof(_Estado)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(estado))
            total = estado.ullTotalPhys / (1024 ** 3)
            libre = estado.ullAvailPhys / (1024 ** 3)
            return "%.1f GB totales, %.1f GB disponibles" % (total, libre)
    except Exception:  # pragma: no cover
        pass
    return "desconocida"


# ---------------------------------------------------------------------------
# Captura de excepciones no controladas
# ---------------------------------------------------------------------------

def _instalar_capturas() -> None:
    """Engancha los tres puntos por los que se escapa una excepción en Python."""

    def gancho_principal(tipo, valor, traza):
        """Excepciones que llegan sin capturar al hilo principal."""
        if issubclass(tipo, KeyboardInterrupt):
            sys.__excepthook__(tipo, valor, traza)
            return
        registro = logging.getLogger(NOMBRE_RAIZ + ".excepcion")
        registro.critical(
            "EXCEPCION NO CONTROLADA EN EL HILO PRINCIPAL\n%s",
            "".join(traceback.format_exception(tipo, valor, traza)),
        )

    def gancho_hilos(args):
        """Excepciones que terminan un hilo secundario."""
        registro = logging.getLogger(NOMBRE_RAIZ + ".excepcion")
        registro.critical(
            "EXCEPCION NO CONTROLADA EN EL HILO %s\n%s",
            getattr(args.thread, "name", "?"),
            "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)),
        )

    def gancho_irrecuperable(args):
        """Excepciones que Python ignora, típicamente en destructores."""
        registro = logging.getLogger(NOMBRE_RAIZ + ".excepcion")
        registro.error(
            "EXCEPCION IGNORADA AL DESTRUIR UN OBJETO (%s)\n%s",
            args.err_msg or "sin mensaje",
            "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)),
        )

    sys.excepthook = gancho_principal
    threading.excepthook = gancho_hilos
    sys.unraisablehook = gancho_irrecuperable


def conectar_registro_wx() -> None:
    """Redirige los mensajes internos de wxWidgets al registro.

    Debe llamarse **después** de crear el objeto ``wx.App``.  Sin esto, los
    avisos de la biblioteca gráfica aparecen en ventanas emergentes (o se
    pierden) en lugar de quedar guardados.
    """
    try:
        import wx
    except ImportError:  # pragma: no cover
        return

    registro = logging.getLogger(NOMBRE_RAIZ + ".wx")

    class _RegistroWx(wx.Log):
        """Adaptador entre el sistema de registro de wxWidgets y el nuestro."""

        _EQUIVALENCIAS = {
            wx.LOG_FatalError: logging.CRITICAL,
            wx.LOG_Error: logging.ERROR,
            wx.LOG_Warning: logging.WARNING,
            wx.LOG_Message: logging.INFO,
            wx.LOG_Status: logging.INFO,
            wx.LOG_Info: logging.INFO,
            wx.LOG_Debug: logging.DEBUG,
            wx.LOG_Trace: logging.DEBUG,
        }

        def DoLogRecord(self, nivel, mensaje, info):  # noqa: N802 (nombre impuesto por wx)
            registro.log(self._EQUIVALENCIAS.get(nivel, logging.INFO), "%s", mensaje)

    wx.Log.SetActiveTarget(_RegistroWx())
    registro.debug("Registro de wxWidgets conectado")


def conectar_registro_lxml() -> None:
    """Redirige al registro los mensajes internos de la biblioteca lxml.

    Muchos EPUB declaran una DTD alojada en Internet (``xhtml11.dtd``).  El
    analizador no la descarga, pero deja constancia del intento escribiendo en
    la salida de errores del proceso.  Sin esta redirección, esos avisos
    inundan la consola y, lo que es peor, no quedan registrados en ninguna
    parte.  Con ella se guardan como mensajes de depuración.
    """
    try:
        from lxml import etree
    except ImportError:  # pragma: no cover
        return

    registro_lxml = etree.PyErrorLog(NOMBRE_RAIZ + ".lxml")
    # Por omisión lxml manda sus avisos como ERROR y CRITICAL, y aquí no lo
    # son: el analizador trabaja en modo de recuperación, así que una etiqueta
    # sin cerrar se corrige sola y el libro se lee entero.  Dejarlos en esos
    # niveles llenaba el registro de errores —un mega en una sola sesión con
    # una biblioteca grande— con cosas que no son errores del programa.
    niveles = etree.ErrorLevels
    registro_lxml.level_map.update({niveles.WARNING: logging.DEBUG,
                                    niveles.ERROR: logging.DEBUG,
                                    niveles.FATAL: logging.DEBUG})
    etree.use_global_python_log(registro_lxml)
    logging.getLogger(NOMBRE_RAIZ + ".lxml").debug("Registro de lxml conectado")


# ---------------------------------------------------------------------------
# Medición de tiempos
# ---------------------------------------------------------------------------

@contextmanager
def cronometro(registro: logging.Logger, descripcion: str, nivel: int = logging.INFO) -> Iterator[dict]:
    """Mide cuánto tarda un bloque de código y lo anota en el registro.

    Ejemplo::

        with cronometro(log, "analisis del EPUB") as datos:
            documento = analizador.analizar(ruta)
            datos["secciones"] = len(documento.secciones)

    El diccionario obtenido con ``as`` permite añadir datos que se muestran
    junto al tiempo, para poder relacionar duración y volumen de trabajo.
    """
    datos: dict[str, Any] = {}
    inicio = time.perf_counter()
    try:
        yield datos
    finally:
        transcurrido = (time.perf_counter() - inicio) * 1000.0
        extra = " | ".join("%s=%s" % (clave, valor) for clave, valor in datos.items())
        if extra:
            registro.log(nivel, "[tiempo] %s: %.1f ms | %s", descripcion, transcurrido, extra)
        else:
            registro.log(nivel, "[tiempo] %s: %.1f ms", descripcion, transcurrido)


def cronometrar(descripcion: str | None = None) -> Callable:
    """Decorador que mide el tiempo de una función completa.

    :param descripcion: Texto a mostrar; por omisión, el nombre de la función.
    """

    def decorador(funcion: Callable) -> Callable:
        etiqueta = descripcion or funcion.__qualname__

        @functools.wraps(funcion)
        def envoltura(*args, **kwargs):
            registro = logging.getLogger(NOMBRE_RAIZ + "." + funcion.__module__)
            with cronometro(registro, etiqueta, logging.DEBUG):
                return funcion(*args, **kwargs)

        return envoltura

    return decorador


def registrar_excepcion(registro: logging.Logger, descripcion: str, error: BaseException) -> None:
    """Anota una excepción capturada, con toda su traza.

    Se usa en los puntos donde la aplicación decide continuar pese al fallo
    (por ejemplo, una sección de un libro que no se puede convertir).
    """
    registro.error(
        "%s: %s: %s\n%s",
        descripcion,
        type(error).__name__,
        error,
        "".join(traceback.format_exception(type(error), error, error.__traceback__)),
    )
