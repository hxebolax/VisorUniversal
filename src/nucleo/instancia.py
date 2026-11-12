# -*- coding: utf-8 -*-
"""Instancia única: una sola ventana del programa a la vez.

Si se abre un segundo libro desde el explorador de archivos mientras el
programa ya está en marcha, lo esperable no es que aparezca otra ventana con
sus propios ajustes y su propia posición de lectura, sino que el libro se abra
en la ventana que ya está abierta.

Cómo funciona, en tres piezas:

1. ``wx.SingleInstanceChecker`` detecta que ya hay otra copia en marcha.
2. La primera copia deja escrito en ``data/config`` el identificador de su
   ventana; la segunda lo lee y la trae al frente con la API de Windows.
3. La segunda copia deja además un **encargo** con el archivo que se quería
   abrir.  La primera revisa ese encargo con un temporizador y abre el libro
   con su propio código, que es el que sabe hacerlo bien.

El paso 3 hace falta porque forzar la ventana desde fuera la pone en pantalla,
pero no puede pedirle que cargue un libro: eso solo puede hacerlo ella misma.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from . import rutas
from .registro import obtener_registro

log = obtener_registro(__name__)

#: Un encargo más antiguo que esto se considera basura de un cierre brusco y
#: se descarta, para que no se abra un libro «de la nada» mucho después.
CADUCIDAD_ENCARGO = 60.0


def _ruta_ventana() -> Path:
    """Archivo donde la primera copia anota el identificador de su ventana."""
    return rutas.ruta_config() / "ventana_activa.txt"


def _ruta_encargo() -> Path:
    """Archivo donde una segunda copia deja el libro que hay que abrir."""
    return rutas.ruta_config() / "encargo_abrir.txt"


# ---------------------------------------------------------------------------
# Lado de la copia que ya estaba en marcha
# ---------------------------------------------------------------------------

def anotar_ventana(identificador: int) -> None:
    """Guarda el identificador de la ventana principal."""
    try:
        _ruta_ventana().write_text(str(int(identificador)), encoding="utf-8")
    except Exception as error:
        log.debug("No se ha podido anotar la ventana activa: %s", error)


def olvidar_ventana() -> None:
    """Borra el identificador al cerrar, para no dejar uno obsoleto."""
    try:
        destino = _ruta_ventana()
        if destino.exists():
            destino.unlink()
    except OSError:
        pass


def recoger_encargo() -> str | None:
    """Comprueba (y consume) si otra copia ha pedido abrir un libro.

    :return: La ruta del libro, o ``None`` si no había ningún encargo válido.
    """
    destino = _ruta_encargo()
    try:
        if not destino.exists():
            return None
        contenido = destino.read_text(encoding="utf-8")
        destino.unlink()
    except OSError as error:
        log.debug("No se ha podido leer el encargo: %s", error)
        return None
    marca, _, ruta = contenido.partition("\n")
    try:
        momento = float(marca.strip() or "0")
    except ValueError:
        return None
    if time.time() - momento > CADUCIDAD_ENCARGO:
        log.debug("Encargo caducado, se descarta")
        return None
    ruta = ruta.strip()
    return ruta or None


# ---------------------------------------------------------------------------
# Lado de la copia que acaba de arrancar y sobra
# ---------------------------------------------------------------------------

def dejar_encargo(archivo: str | None) -> None:
    """Deja constancia de que hay que abrir un libro (o solo mostrar la ventana)."""
    try:
        _ruta_encargo().write_text(
            "%f\n%s" % (time.time(), archivo or ""), encoding="utf-8"
        )
    except Exception as error:
        log.debug("No se ha podido dejar el encargo: %s", error)


def traer_al_frente() -> bool:
    """Trae al frente la ventana de la copia que ya estaba en marcha.

    :return: ``True`` si la ventana ha quedado realmente en primer plano.
    """
    if sys.platform != "win32":
        return False
    try:
        origen = _ruta_ventana()
        if not origen.exists():
            return False
        identificador = int((origen.read_text(encoding="utf-8") or "0").strip() or "0")
    except (OSError, ValueError) as error:
        log.debug("No se ha podido leer la ventana activa: %s", error)
        return False
    return forzar_al_frente(identificador)


def forzar_al_frente(identificador: int) -> bool:
    """Pone una ventana en primer plano, sorteando la protección de Windows.

    Windows solo deja cambiar la ventana en primer plano a los programas que
    han recibido una pulsación reciente.  Simular una pulsación de Alt
    desbloquea esa protección; sin ella, la barra de tareas solo parpadea y la
    ventana no llega a mostrarse.
    """
    if sys.platform != "win32" or not identificador:
        return False
    try:
        import ctypes
        from ctypes import wintypes

        usuario = ctypes.windll.user32
        # Fijar los tipos importa: en 64 bits los identificadores de ventana
        # son punteros y, sin declararlos, ctypes los truncaría a 32 bits.
        usuario.IsWindow.argtypes = [wintypes.HWND]
        usuario.IsIconic.argtypes = [wintypes.HWND]
        usuario.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        usuario.SetForegroundWindow.argtypes = [wintypes.HWND]
        usuario.BringWindowToTop.argtypes = [wintypes.HWND]
        usuario.GetForegroundWindow.restype = wintypes.HWND
        usuario.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                         ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                         wintypes.UINT]

        ventana = wintypes.HWND(identificador)
        if not usuario.IsWindow(ventana):
            log.debug("La ventana anotada ya no existe")
            return False
        SW_SHOW, SW_RESTORE = 5, 9
        usuario.ShowWindow(ventana, SW_SHOW)
        if usuario.IsIconic(ventana):
            usuario.ShowWindow(ventana, SW_RESTORE)
        VK_MENU, KEYEVENTF_KEYUP = 0x12, 0x0002
        try:
            usuario.keybd_event(VK_MENU, 0, 0, 0)
            usuario.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
        except Exception:
            pass
        usuario.SetForegroundWindow(ventana)
        usuario.BringWindowToTop(ventana)

        # Refuerzo: subir la ventana del todo un instante y quitarle enseguida
        # el «siempre encima».  Sin esto, cuando la ventana que tiene el foco
        # pertenece a otro proceso, Windows se limita a parpadear el botón de
        # la barra de tareas y la ventana no llega a verse.
        HWND_TOPMOST, HWND_NOTOPMOST = -1, -2
        SWP_NOMOVE, SWP_NOSIZE, SWP_SHOWWINDOW = 0x0002, 0x0001, 0x0040
        banderas = SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW
        usuario.SetWindowPos(ventana, wintypes.HWND(HWND_TOPMOST), 0, 0, 0, 0, banderas)
        usuario.SetWindowPos(ventana, wintypes.HWND(HWND_NOTOPMOST), 0, 0, 0, 0, banderas)

        conseguido = usuario.GetForegroundWindow() == identificador
        log.info("Ventana existente traída al frente: %s", conseguido)
        return bool(conseguido)
    except Exception as error:
        log.debug("No se ha podido traer la ventana al frente: %s", error)
        return False
