# -*- coding: utf-8 -*-
"""Temporizadores de wxPython que se paran solos al destruirse su ventana.

Un ``wx.Timer(ventana)`` entrega sus avisos a esa ventana.  Si la ventana se
destruye y el temporizador sigue en marcha, el siguiente aviso va a parar a
memoria que ya se ha liberado: wxWidgets no lo comprueba.  Lo que pasa
después depende de la suerte —a veces nada, a veces una violación de acceso,
a veces el montón de memoria corrompido y el programa cerrado de golpe con el
código ``0xc0000374``—, y por eso costó tanto dar con ello.

Era la causa de los cierres de golpe al salir del programa con documentos
abiertos: cada panel de lectura vigila el cursor con un temporizador que
arranca al cargar un documento, y al cerrar la ventana nadie lo paraba.  Se
confirmó con el depurador: la caída estaba en ``wxTimerImpl::SendEvent``
mandando el aviso a un objeto ya liberado.

Por eso todo temporizador con dueño pasa por :func:`parar_al_destruir`, que lo
para en cuanto la ventana empieza a destruirse, venga de donde venga el
cierre.
"""

from __future__ import annotations

import wx


def parar_al_destruir(dueno: wx.Window, *temporizadores: wx.Timer) -> None:
    """Para los temporizadores cuando se destruya la ventana que los recibe.

    :param dueno: Ventana a la que el temporizador manda sus avisos.
    :param temporizadores: Uno o varios ``wx.Timer`` (o ``wx.CallLater``).
    """

    # Se compara también por identificador: al destruir una ventana de primer
    # nivel, wxPython entrega el aviso con un envoltorio nuevo de la clase base
    # (``TopLevelWindow``), que ya no es el mismo objeto que ``dueno``.
    identificador = dueno.GetId()

    def al_destruir(evento: wx.WindowDestroyEvent) -> None:
        # El aviso puede venir de una ventana hija: solo cuenta el del dueño.
        if evento.GetEventObject() is dueno or evento.GetId() == identificador:
            for temporizador in temporizadores:
                try:
                    temporizador.Stop()
                except (RuntimeError, AttributeError):
                    pass
        evento.Skip()

    dueno.Bind(wx.EVT_WINDOW_DESTROY, al_destruir)
