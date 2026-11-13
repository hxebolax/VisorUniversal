# -*- coding: utf-8 -*-
"""Diálogo de espera para las operaciones que tardan.

Consultar los modelos de un proveedor de IA o probar la conexión son
operaciones de red: pueden tardar unos segundos o quedarse esperando hasta que
venza el plazo.  Hacerlas sin más deja la ventana congelada y, sobre todo,
**muda**: sin ver la pantalla no hay forma de saber si el programa está
trabajando o se ha quedado colgado.

Este diálogo resuelve las dos cosas a la vez.  Anuncia lo que está haciendo,
muestra una barra de progreso indeterminada y ejecuta el trabajo en otro hilo,
de modo que la aplicación sigue viva.  Al terminar se cierra solo y quien lo
llamó recibe el resultado, o el error, para enseñarlo en un cuadro de mensaje
—que es lo que el lector de pantalla lee sin falta—.

Uso típico::

    ok, resultado = ejecutar_esperando(self, "Consultando los modelos...",
                                       lambda: servicio.listar_modelos())
    if ok:
        ...
"""

from __future__ import annotations

import threading

import wx

from interfaz.temporizadores import parar_al_destruir
from interfaz.dialogos import ayuda_opcion
from interfaz.anuncios import Voz
from nucleo.idioma import _
from nucleo.registro import obtener_registro, registrar_excepcion

log = obtener_registro(__name__)

MARGEN = 12


class DialogoEspera(wx.Dialog):
    """Ventana de «espera un momento» que ejecuta un trabajo en otro hilo.

    :param padre: Ventana desde la que se abre.
    :param mensaje: Qué se está haciendo, en una frase.
    :param trabajo: Función sin argumentos que se ejecuta en el otro hilo.
    :param titulo: Título de la ventana.
    """

    def __init__(self, padre: wx.Window, mensaje: str, trabajo,
                 titulo: str = _("Un momento")) -> None:
        # Sin botón de cerrar: la operación tiene su propio plazo de espera y
        # dejar cerrar a medias obligaría a vigilar un hilo que ya no le
        # interesa a nadie.  Nunca se queda colgado más de lo que dure ese
        # plazo, que el usuario fija en las opciones.
        super().__init__(padre, title=titulo, style=wx.CAPTION)
        self._trabajo = trabajo
        self.resultado = None
        self.error: str = ""
        self.terminado = False

        contenedor = wx.BoxSizer(wx.VERTICAL)
        contenedor.Add(wx.StaticText(self, label=mensaje), 0, wx.ALL, MARGEN)
        self.barra = wx.Gauge(self, range=100, size=(320, 20), style=wx.GA_HORIZONTAL)
        contenedor.Add(self.barra, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, MARGEN)
        self.SetSizerAndFit(contenedor)
        self.CentreOnParent()

        Voz(self).decir(mensaje)
        # La barra en modo indeterminado necesita que alguien la mueva.
        self._latido = wx.Timer(self)
        parar_al_destruir(self, self._latido)
        self.Bind(wx.EVT_TIMER, lambda evento: self.barra.Pulse(), self._latido)
        self._latido.Start(120)
        # Control+F1 explica el control que tenga el foco.
        ayuda_opcion.enganchar(self)

    def _lanzar(self) -> None:
        """Arranca el hilo que hace el trabajo."""

        def envoltorio():
            """Ejecuta el trabajo y devuelve el control al hilo de la interfaz."""
            try:
                resultado = self._trabajo()
            except Exception as error:
                registrar_excepcion(log, "Fallo en la operación en espera", error)
                wx.CallAfter(self._terminar, None, str(error))
            else:
                wx.CallAfter(self._terminar, resultado, "")

        threading.Thread(target=envoltorio, name="espera", daemon=True).start()

    def _terminar(self, resultado, error: str) -> None:
        """Recoge el resultado y cierra el diálogo."""
        self.resultado = resultado
        self.error = error
        self.terminado = True
        self._latido.Stop()
        if self.IsModal():
            self.EndModal(wx.ID_OK if not error else wx.ID_CANCEL)


def ejecutar_esperando(padre: wx.Window, mensaje: str, trabajo,
                       titulo: str = _("Un momento")) -> tuple[bool, object]:
    """Ejecuta un trabajo lento mostrando el diálogo de espera.

    :param padre: Ventana desde la que se abre.
    :param mensaje: Qué se está haciendo.
    :param trabajo: Función sin argumentos, la que tarda.
    :param titulo: Título de la ventana de espera.
    :return: ``(True, resultado)`` si ha ido bien, o ``(False, mensaje)`` con
             el texto del error si ha fallado.
    """
    dialogo = DialogoEspera(padre, mensaje, trabajo, titulo)
    try:
        # El hilo se lanza con el diálogo ya creado pero antes de mostrarlo;
        # si el trabajo fuera instantáneo, ``_terminar`` llegaría por
        # ``CallAfter`` y por tanto después de que empiece el bucle modal.
        dialogo._lanzar()
        dialogo.ShowModal()
        return (not dialogo.error), (dialogo.resultado if not dialogo.error else dialogo.error)
    finally:
        dialogo.Destroy()
