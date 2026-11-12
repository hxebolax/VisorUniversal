# -*- coding: utf-8 -*-
"""Icono en la bandeja del sistema.

Escuchar un libro entero son horas.  Con esto, la ventana se puede minimizar a
la bandeja y quitarse de en medio —de la barra de tareas y del Alt+Tab— sin
parar la lectura, que sigue sonando y se maneja con las teclas globales.

El icono es la vuelta atrás: hace de puerta de entrada para quien no se acuerde
de las teclas globales, con un menú que repite las órdenes del lector.

**Hay que destruirlo antes de cerrar el programa.**  Mientras exista un icono
de bandeja, wxPython considera que la aplicación tiene una ventana viva y no
termina el bucle de eventos: el proceso se quedaría en memoria sin nada que
mostrar.
"""

from __future__ import annotations

import wx
import wx.adv

from nucleo.idioma import _
from nucleo.registro import obtener_registro
from version import NOMBRE

log = obtener_registro(__name__)


class IconoBandeja(wx.adv.TaskBarIcon):
    """Icono del programa en la bandeja, con el menú del lector.

    :param ventana: Ventana principal, a la que se devuelve el control.
    """

    def __init__(self, ventana) -> None:
        super().__init__()
        self.ventana = ventana
        icono = wx.ArtProvider.GetIcon(wx.ART_HELP_BOOK, wx.ART_OTHER, (16, 16))
        self.SetIcon(icono, NOMBRE)
        # Un solo clic izquierdo abre el menú: muchos programas no hacen nada
        # con ese clic y el icono parece estropeado.  El doble clic restaura,
        # que es lo que se espera de un icono de bandeja.
        self.Bind(wx.adv.EVT_TASKBAR_LEFT_UP, self._al_clic)
        self.Bind(wx.adv.EVT_TASKBAR_LEFT_DCLICK, lambda evento: self.ventana.restaurar_desde_bandeja())

    def CreatePopupMenu(self):  # noqa: N802 (nombre impuesto por wxPython)
        """wxPython llama a esto con el clic derecho sobre el icono."""
        return self._menu()

    def _al_clic(self, evento) -> None:
        """Abre el menú también con el clic izquierdo."""
        self.PopupMenu(self._menu())

    def _menu(self) -> wx.Menu:
        """Construye el menú del icono."""
        menu = wx.Menu()
        restaurar = menu.Append(wx.ID_ANY, _("&Restaurar %s") % NOMBRE)
        letra = restaurar.GetFont()
        try:
            letra.SetWeight(wx.FONTWEIGHT_BOLD)
            restaurar.SetFont(letra)
        except Exception:     # pragma: no cover - algunos temas no lo admiten
            pass
        self.Bind(wx.EVT_MENU, lambda evento: self.ventana.restaurar_desde_bandeja(), restaurar)
        menu.AppendSeparator()

        lector = self.ventana.lectura_voz
        leer = menu.Append(wx.ID_ANY,
                           _("&Pausar la lectura") if lector.leyendo and not lector.sintetizador.pausada
                           else _("&Leer en voz alta"))
        self.Bind(wx.EVT_MENU, lambda evento: lector.alternar(), leer)
        detener = menu.Append(wx.ID_ANY, _("&Detener la lectura"))
        self.Bind(wx.EVT_MENU, lambda evento: lector.detener(anunciar=True), detener)
        detener.Enable(lector.leyendo)
        anterior = menu.Append(wx.ID_ANY, _("Frase &anterior"))
        self.Bind(wx.EVT_MENU, lambda evento: lector.saltar_frase(False), anterior)
        siguiente = menu.Append(wx.ID_ANY, _("Frase &siguiente"))
        self.Bind(wx.EVT_MENU, lambda evento: lector.saltar_frase(True), siguiente)

        menu.AppendSeparator()
        salir = menu.Append(wx.ID_ANY, _("&Salir"))
        self.Bind(wx.EVT_MENU, lambda evento: self.ventana.Close(), salir)
        return menu
