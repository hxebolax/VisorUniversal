# -*- coding: utf-8 -*-
"""Ajustes que solo se pueden hacer hablando directamente con Windows.

Aquí vive el único trozo de la aplicación que baja al nivel de la API del
sistema.  Está aislado a propósito: en cualquier otra plataforma las
funciones de este módulo no hacen nada y el programa sigue funcionando.

De momento contiene una sola cosa: impedir que el control de texto muestre su
propio menú contextual.  Se intentó primero por la vía de wxPython
(descartar el evento ``EVT_CONTEXT_MENU``) y se comprobó, midiendo si llegaba
a aparecer una ventana de menú, que **no basta**: el control de texto
enriquecido de Windows muestra ese menú por su cuenta, sin pasar por el
sistema de eventos de wxPython.  La única forma segura de evitarlo es
interceptar el mensaje ``WM_CONTEXTMENU`` en el procedimiento de ventana.
"""

from __future__ import annotations

import ctypes
import os
import sys
from ctypes import wintypes

from nucleo.registro import obtener_registro

log = obtener_registro(__name__)

#: Mensaje que Windows envía al pulsar Mayús+F10 o el botón derecho del ratón
#: sobre una ventana.
_WM_CONTEXTMENU = 0x007B

#: Mensajes de pulsación y suelta de tecla.
_WM_KEYDOWN = 0x0100
_WM_KEYUP = 0x0101

#: Código de la tecla Aplicaciones (la que hay junto a Control, a la derecha).
#: Se filtra aparte porque el control de texto enriquecido de Windows abre su
#: menú al recibirla **sin** enviar antes ``WM_CONTEXTMENU``, de modo que
#: bloquear solo ese mensaje no basta.  Se comprobó midiendo: con la tecla
#: pulsada de verdad aparecía el menú «Deshacer, Rehacer, Cortar, Copiar…» y
#: la tecla ni siquiera llegaba al sistema de eventos de wxPython.
_VK_APPS = 0x5D

#: Código de F10, que con Mayús es la otra forma de pedir el menú contextual.
_VK_F10 = 0x79

#: Código de la tecla Mayús, para saber si está pulsada.
_VK_SHIFT = 0x10

#: Índice del procedimiento de ventana dentro de los datos de una ventana.
_GWLP_WNDPROC = -4

if sys.platform == "win32":
    # En Windows de 64 bits estos tipos son de 64 bits; usar los de ctypes
    # que dependen del tamaño del puntero hace que el módulo funcione igual
    # en 32 y en 64 bits.
    _LRESULT = ctypes.c_ssize_t
    _WPARAM = ctypes.c_size_t
    _LPARAM = ctypes.c_ssize_t
    _WNDPROC = ctypes.WINFUNCTYPE(_LRESULT, wintypes.HWND, ctypes.c_uint, _WPARAM, _LPARAM)

    _user32 = ctypes.windll.user32
    _user32.CallWindowProcW.restype = _LRESULT
    _user32.CallWindowProcW.argtypes = [_WNDPROC, wintypes.HWND, ctypes.c_uint,
                                        _WPARAM, _LPARAM]
    # SetWindowLongPtrW solo existe en 64 bits; en 32 bits el equivalente es
    # SetWindowLongW.
    _establecer = getattr(_user32, "SetWindowLongPtrW", None) or _user32.SetWindowLongW
    _establecer.restype = _LRESULT
    _establecer.argtypes = [wintypes.HWND, ctypes.c_int, _WNDPROC]
else:  # pragma: no cover - la aplicación está pensada para Windows
    _WNDPROC = None


#: Filtros ya instalados, por identificador de ventana.  Evita encadenar dos
#: filtros sobre el mismo control: si el primero se dejara de referenciar,
#: Python liberaría su función y el segundo llamaría a memoria ya liberada.
_INSTALADOS: dict[int, "_MenuSuprimido"] = {}


class _MenuSuprimido:
    """Mantiene vivos los objetos que Windows necesita mientras exista la ventana.

    Windows guarda un puntero a la función que se le pasa.  Si Python
    liberase ese objeto, el puntero quedaría colgando y el programa se
    cerraría de golpe la próxima vez que llegase un mensaje.  Por eso hay que
    conservar una referencia mientras el control siga existiendo.
    """

    __slots__ = ("procedimiento_nuevo", "procedimiento_anterior")

    def __init__(self, procedimiento_nuevo, procedimiento_anterior) -> None:
        self.procedimiento_nuevo = procedimiento_nuevo
        self.procedimiento_anterior = procedimiento_anterior


def suprimir_menu_contextual(control) -> _MenuSuprimido | None:
    """Impide que un control muestre el menú contextual propio de Windows.

    :param control: Control de wxPython cuyo menú hay que suprimir.
    :return: Un objeto que hay que **guardar** mientras el control exista, o
             ``None`` si no se ha podido hacer (otra plataforma, o el control
             todavía no tiene ventana nativa).
    """
    if sys.platform != "win32" or _WNDPROC is None:
        return None
    if os.environ.get("VISOR_SIN_SUPRIMIR_MENU"):
        # Salida de emergencia para descartar este procedimiento cuando algo se
        # cae y no está claro quién tiene la culpa.  Un procedimiento de ventana
        # escrito en Python se mete en medio de **todos** los mensajes del
        # control, incluidos los que le manda el lector de pantalla, así que es
        # el primer sospechoso cuando el programa se cierra sin explicación.
        # Con esto puesto vuelve el menú contextual de Windows, que es un mal
        # menor mientras se averigua.
        log.warning("VISOR_SIN_SUPRIMIR_MENU: no se instala el procedimiento "
                    "de ventana y el menú contextual de Windows vuelve")
        return None
    identificador = control.GetHandle()
    if not identificador:
        log.debug("El control aún no tiene ventana nativa: no se suprime el menú")
        return None
    ya_puesto = _INSTALADOS.get(identificador)
    if ya_puesto is not None:
        log.debug("El control ya tenía el menú suprimido; no se instala otra vez")
        return ya_puesto

    anterior = _WNDPROC()

    def procedimiento(ventana, mensaje, wparam, lparam):
        """Filtra los mensajes que llegan al control.

        Se descartan las tres formas de pedir el menú contextual: el mensaje
        que envía Windows (botón derecho y Mayús+F10) y la tecla Aplicaciones,
        que el control atiende por su cuenta sin enviar ese mensaje.
        """
        if mensaje == _WM_CONTEXTMENU:
            return 0  # mensaje atendido: el menú no llega a mostrarse
        if mensaje in (_WM_KEYDOWN, _WM_KEYUP):
            if wparam == _VK_APPS:
                return 0
            # GetKeyState devuelve un valor con el bit alto activado mientras
            # la tecla está pulsada.
            if wparam == _VK_F10 and (_user32.GetKeyState(_VK_SHIFT) & 0x8000):
                return 0
        return _user32.CallWindowProcW(anterior, ventana, mensaje, wparam, lparam)

    puente = _WNDPROC(procedimiento)
    try:
        direccion = _establecer(wintypes.HWND(identificador), _GWLP_WNDPROC, puente)
    except Exception as error:  # pragma: no cover - defensivo
        log.warning("No se ha podido suprimir el menú contextual: %s", error)
        return None
    if not direccion:
        log.warning("No se ha podido suprimir el menú contextual (sin procedimiento anterior)")
        return None
    # La dirección devuelta es el procedimiento anterior; se copia dentro del
    # objeto de función para poder invocarlo con CallWindowProcW.
    ctypes.memmove(ctypes.byref(anterior), ctypes.byref(_LRESULT(direccion)),
                   ctypes.sizeof(_LRESULT))
    log.debug("Menú contextual suprimido en el control de texto")
    guardado = _MenuSuprimido(puente, anterior)
    _INSTALADOS[identificador] = guardado
    return guardado
