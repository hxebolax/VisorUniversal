# -*- coding: utf-8 -*-
"""Elección de una tecla global: se pulsa, no se escribe.

Pedirle a alguien que escriba «alt+win+space» es pedirle que acierte con una
sintaxis; pedirle que **pulse la combinación** no tiene pérdida y además
garantiza que la combinación existe en su teclado.  Este diálogo captura la
pulsación, la enseña escrita en español y solo la acepta si pasa las cuatro
comprobaciones de :mod:`interfaz.teclas_globales`.

Mientras está abierto, las teclas globales del programa están **soltadas**: si
no, al pulsar una de ellas la capturaría Windows y la reasignación nunca
llegaría aquí.  De eso se encarga quien abre el diálogo.
"""

from __future__ import annotations

import wx

from interfaz import teclas_globales
from interfaz.accesible import etiquetar
from interfaz.anuncios import Voz
from nucleo.idioma import _

MARGEN = 8


class DialogoCapturarTecla(wx.Dialog):
    """Captura la combinación que el usuario pulse y la comprueba.

    :param padre: Ventana desde la que se abre.
    :param accion: Acción a la que se le va a asignar la tecla.
    :param asignadas: ``{identificador: combinación}`` de todo lo asignado, para
                      detectar choques con las demás acciones del programa.
    :param ventana_principal: Ventana con la que se hace la prueba de registro
                              contra Windows.
    """

    def __init__(self, padre: wx.Window, accion, asignadas: dict,
                 ventana_principal: wx.Window) -> None:
        super().__init__(padre, title=_("Tecla global para «%s»") % accion.etiqueta)
        self.accion = accion
        self.asignadas = asignadas
        self.ventana_principal = ventana_principal
        self.combinacion = ""
        self._voz = Voz(self)

        contenedor = wx.BoxSizer(wx.VERTICAL)
        contenedor.Add(wx.StaticText(self, label=(
            _("Pulsa ahora la combinación que quieras para «%s».\n\n"
            "Tiene que llevar Windows, o Control y Alt juntos: así no se traga pulsaciones\n"
            "normales en los programas donde estés escribiendo. Escape cancela.")
            % accion.etiqueta)), 0, wx.ALL, MARGEN)

        contenedor.Add(wx.StaticText(self, label=_("Combinación &elegida:")), 0,
                       wx.LEFT | wx.RIGHT | wx.TOP, MARGEN)
        self.campo = etiquetar(wx.TextCtrl(
            self, value=teclas_globales.legible(asignadas.get(accion.identificador, "")),
            style=wx.TE_READONLY, size=(360, -1)), _("Combinación elegida"))
        contenedor.Add(self.campo, 0, wx.EXPAND | wx.ALL, MARGEN)

        self.aviso = wx.StaticText(self, label=_("Esperando a que pulses una combinación..."))
        contenedor.Add(self.aviso, 0, wx.ALL, MARGEN)

        fila = wx.StdDialogButtonSizer()
        self.aceptar = wx.Button(self, wx.ID_OK, _("&Asignar"))
        self.aceptar.Enable(False)
        fila.AddButton(self.aceptar)
        fila.AddButton(wx.Button(self, wx.ID_CANCEL, _("&Cancelar")))
        fila.Realize()
        contenedor.Add(fila, 0, wx.EXPAND | wx.ALL, MARGEN)
        self.SetSizerAndFit(contenedor)

        self.Bind(wx.EVT_CHAR_HOOK, self._al_pulsar)
        self.campo.SetFocus()

    def _al_pulsar(self, evento: wx.KeyEvent) -> None:
        """Recoge la pulsación y la somete a las comprobaciones."""
        if evento.GetKeyCode() == wx.WXK_ESCAPE and not evento.HasAnyModifiers():
            self.EndModal(wx.ID_CANCEL)
            return
        # Tabulador sin modificadores se deja pasar: es la forma de llegar a los
        # botones sin ratón.  Con modificadores sí es una combinación válida.
        if evento.GetKeyCode() == wx.WXK_TAB and not evento.HasAnyModifiers():
            evento.Skip()
            return
        combinacion = teclas_globales.desde_evento(evento)
        if not combinacion:
            return      # todavía solo hay modificadores pulsados
        self._probar(combinacion)

    def _probar(self, combinacion: str) -> None:
        """Comprueba la combinación y deja el diálogo listo o con el motivo."""
        self.campo.SetValue(teclas_globales.legible(combinacion))
        motivo = teclas_globales.revisar(self.ventana_principal, combinacion,
                                         self.asignadas, self.accion.identificador)
        if motivo:
            self.combinacion = ""
            self.aceptar.Enable(False)
            self.aviso.SetLabel(motivo)
            self._voz.decir(_("%s no vale. %s") % (teclas_globales.legible(combinacion), motivo))
            return
        self.combinacion = combinacion
        self.aceptar.Enable(True)
        self.aviso.SetLabel(_("Libre. Pulsa «Asignar» para dejarla puesta."))
        self._voz.decir(_("%s está libre. Pulsa Asignar.")
                        % teclas_globales.legible(combinacion))
