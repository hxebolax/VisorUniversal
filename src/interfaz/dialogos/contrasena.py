# -*- coding: utf-8 -*-
"""Pedir la contraseña de un documento cifrado.

Un PDF puede llevar dos contraseñas y solo una impide leerlo (véase
:class:`formatos.pdf_diagnostico.Cifrado`).  La de propietario, que solo limita
imprimir o copiar, la salta el programa solo.  La de usuario hay que pedirla, y
hasta ahora no se pedía: el documento sencillamente no se abría.

La ventana es deliberadamente escueta —una caja y dos botones— porque aparece
en mitad de la apertura de un libro y lo único que hace falta es escribir y
seguir.

Cómo se pide desde el hilo del análisis
---------------------------------------

El análisis corre en un hilo aparte para que la aplicación no se quede
congelada mientras convierte un PDF de mil páginas.  Pero una ventana solo se
puede crear desde el hilo de la interfaz, así que aquí hay que hacer las dos
cosas a la vez: **crear la ventana en el hilo de la interfaz** y **parar el
hilo del análisis** hasta que el usuario conteste.

Eso es lo que hace :func:`solicitar`: manda la ventana al hilo de la interfaz
con ``wx.CallAfter``, se queda esperando en un ``Event`` y devuelve lo que el
usuario haya escrito.  Sin esa espera, el análisis seguiría adelante sin
contraseña y fallaría antes de que a nadie le diera tiempo a escribirla.
"""

from __future__ import annotations

import threading

import wx

from interfaz.dialogos import ayuda_opcion
from interfaz.accesible import fila_etiquetada
from nucleo.idioma import _
from nucleo.registro import obtener_registro

log = obtener_registro(__name__)

MARGEN = 8

#: Cuánto se espera como mucho a que alguien conteste, en segundos.  El tope no
#: es por prisa: es para que un fallo de la interfaz no deje el hilo del
#: análisis esperando para siempre y con él el libro a medio abrir.
ESPERA_MAXIMA = 600


class DialogoContrasena(wx.Dialog):
    """Caja para escribir la contraseña de un documento.

    :param padre: Ventana principal.
    :param nombre: Nombre del archivo, para que se sepa de cuál se habla
                   cuando se abren varios seguidos.
    :param reintento: Si la contraseña anterior no ha valido.
    """

    def __init__(self, padre: wx.Window, nombre: str, reintento: bool = False) -> None:
        super().__init__(padre, title=_("Documento protegido"),
                         style=wx.DEFAULT_DIALOG_STYLE)
        contenedor = wx.BoxSizer(wx.VERTICAL)
        mensaje = (_("La contraseña no es correcta. Vuelve a escribirla.")
                   if reintento else
                   _("«%s» está cifrado. Escribe la contraseña para leerlo.") % nombre)
        contenedor.Add(wx.StaticText(self, label=mensaje), 0, wx.ALL, MARGEN)
        self.campo = fila_etiquetada(
            self, contenedor, _("&Contraseña:"),
            lambda p: wx.TextCtrl(p, size=(320, -1), style=wx.TE_PASSWORD | wx.TE_PROCESS_ENTER))
        self.campo.Bind(wx.EVT_TEXT_ENTER, lambda _evento: self.EndModal(wx.ID_OK))
        botones = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)
        if botones is not None:
            contenedor.Add(botones, 0, wx.EXPAND | wx.ALL, MARGEN)
        self.SetSizerAndFit(contenedor)
        self.CentreOnParent()
        self.campo.SetFocus()
        # Control+F1 explica el control que tenga el foco.
        ayuda_opcion.enganchar(self)

    @property
    def contrasena(self) -> str:
        """Lo que se ha escrito, sin los espacios de los lados."""
        return self.campo.GetValue().strip()


def solicitar(ventana: wx.Window, ruta, intento: int = 0) -> str:
    """Pide la contraseña desde el hilo del análisis y espera la respuesta.

    Se le pasa al analizador de PDF como ``pedir_contrasena``.

    :param ruta: Archivo que se está abriendo.
    :param intento: Cuántas veces se ha pedido ya.  A partir de la primera se
                    avisa de que la anterior no valía, que es la diferencia
                    entre «vuelve a escribirla» y quedarse sin saber si se ha
                    escrito mal o si el archivo está roto.
    :return: La contraseña, o cadena vacía si se ha cancelado.
    """
    from pathlib import Path

    respuesta: list[str] = [""]
    terminado = threading.Event()

    def preguntar() -> None:
        """Abre la ventana.  Se ejecuta siempre en el hilo de la interfaz."""
        try:
            dialogo = DialogoContrasena(ventana, Path(ruta).name, intento > 0)
            try:
                if dialogo.ShowModal() == wx.ID_OK:
                    respuesta[0] = dialogo.contrasena
            finally:
                dialogo.Destroy()
        finally:
            # Pase lo que pase hay que despertar al hilo del análisis: si esto
            # no se ejecutara, el libro se quedaría abriéndose para siempre.
            terminado.set()

    wx.CallAfter(preguntar)
    if not terminado.wait(ESPERA_MAXIMA):
        log.warning("Nadie ha contestado a la petición de contraseña.")
        return ""
    return respuesta[0]
