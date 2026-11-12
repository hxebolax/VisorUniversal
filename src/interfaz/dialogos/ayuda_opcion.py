# -*- coding: utf-8 -*-
"""Ventana que explica el ajuste sobre el que se está.

Se abre con :kbd:`Control+F1` desde cualquier control de las opciones y cuenta
qué es ese ajuste, qué consigue y qué conviene poner.  El texto va en un cuadro
de solo lectura y no en un aviso corriente porque así **se puede recorrer**: con
las flechas, línea a línea, volviendo atrás sobre lo que no se ha entendido, y
copiándolo si hace falta.  Un cuadro de mensaje se lee de una tirada y se cierra.

Debajo está la lista completa de ajustes, de modo que la ventana sirve también
para leerse las opciones enteras de corrido sin ir control por control.
"""

from __future__ import annotations

import wx

from interfaz.accesible import etiquetar
from interfaz.ventanas_win32 import suprimir_menu_contextual
from interfaz.anuncios import Voz
from interfaz.ayuda_control import ayudas
from nucleo.idioma import _
from nucleo.registro import obtener_registro

log = obtener_registro(__name__)

MARGEN = 8


class DialogoAyudaOpcion(wx.Dialog):
    """Explica un ajuste y deja consultar los demás.

    :param padre: Ventana desde la que se abre.
    :param clave: Ajuste sobre el que se estaba, o cadena vacía.
    """

    def __init__(self, padre: wx.Window, clave: str = "") -> None:
        super().__init__(padre, title=_("Qué es esta opción"),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self._voz = Voz(self)
        self._catalogo = ayudas()
        # Ordenados por su título, que es como los busca quien lee la lista.
        self._claves = sorted(self._catalogo, key=lambda c: self._catalogo[c][0].lower())

        contenedor = wx.BoxSizer(wx.VERTICAL)
        contenedor.Add(wx.StaticText(self, label=_(
            "Explicación del ajuste. Con la lista de abajo puedes consultar los demás."
        )), 0, wx.ALL, MARGEN)

        self.titulo = wx.StaticText(self, label="")
        fuente = self.titulo.GetFont()
        fuente.MakeBold()
        self.titulo.SetFont(fuente)
        contenedor.Add(self.titulo, 0, wx.LEFT | wx.RIGHT, MARGEN)

        self.texto = etiquetar(wx.TextCtrl(
            self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_NOHIDESEL,
            size=(560, 260)), _("Explicación del ajuste"))
        self._sin_menu = [suprimir_menu_contextual(self.texto)]
        contenedor.Add(self.texto, 1, wx.EXPAND | wx.ALL, MARGEN)

        contenedor.Add(wx.StaticText(self, label=_("&Otros ajustes:")), 0,
                       wx.LEFT | wx.RIGHT, MARGEN)
        self.lista = etiquetar(wx.ListBox(
            self, choices=[self._catalogo[c][0] for c in self._claves], size=(-1, 150)),
            _("Lista de ajustes"))
        contenedor.Add(self.lista, 0, wx.EXPAND | wx.ALL, MARGEN)

        pie = wx.StdDialogButtonSizer()
        cerrar = wx.Button(self, wx.ID_OK, _("&Cerrar"))
        cerrar.SetDefault()
        pie.AddButton(cerrar)
        pie.Realize()
        contenedor.Add(pie, 0, wx.EXPAND | wx.ALL, MARGEN)
        self.SetSizerAndFit(contenedor)
        self.CentreOnParent()

        self.lista.Bind(wx.EVT_LISTBOX, self._al_elegir)
        self.Bind(wx.EVT_CHAR_HOOK, self._al_pulsar_tecla)
        self.mostrar(clave)
        # El foco va al texto y no a la lista: lo que se ha pedido es leer esta
        # explicación, no buscar otra.
        self.texto.SetFocus()
        self.texto.SetInsertionPoint(0)

    def mostrar(self, clave: str) -> None:
        """Enseña la explicación de un ajuste."""
        if clave not in self._catalogo:
            self.titulo.SetLabel(_("Este control no tiene explicación propia"))
            self.texto.SetValue(_(
                "Todavía no hay una explicación escrita para este control.\n\n"
                "En la lista de abajo están todos los ajustes que sí la tienen."))
            if self._claves:
                self.lista.SetSelection(0)
            return
        titulo, explicacion = self._catalogo[clave]
        self.titulo.SetLabel(titulo)
        self.texto.SetValue(explicacion)
        self.texto.SetInsertionPoint(0)
        if clave in self._claves:
            self.lista.SetSelection(self._claves.index(clave))
        self._voz.decir("%s. %s" % (titulo, explicacion.split("\n")[0]))

    def _al_elegir(self, evento) -> None:
        """Cambia la explicación al elegir otro ajuste en la lista."""
        indice = self.lista.GetSelection()
        if 0 <= indice < len(self._claves):
            clave = self._claves[indice]
            titulo, explicacion = self._catalogo[clave]
            self.titulo.SetLabel(titulo)
            self.texto.SetValue(explicacion)
            self.texto.SetInsertionPoint(0)

    def _al_pulsar_tecla(self, evento: wx.KeyEvent) -> None:
        """Escape cierra la ventana."""
        if evento.GetKeyCode() == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_OK)
            return
        evento.Skip()


def enganchar(dialogo: wx.Window) -> None:
    """Hace que Control+F1 explique el control que tenga el foco.

    Se engancha una sola vez sobre el diálogo entero, con ``EVT_CHAR_HOOK``,
    que recibe las teclas antes que el control que tiene el foco.  Así funciona
    en todos —también en los cuadros de texto, que si no se quedarían la
    pulsación— sin tener que acordarse de engancharlo control por control.
    """

    def al_pulsar(evento: wx.KeyEvent) -> None:
        """Atiende Control+F1 y deja pasar todo lo demás."""
        if evento.GetKeyCode() != wx.WXK_F1 or not evento.ControlDown():
            evento.Skip()
            return
        from interfaz.ayuda_control import ayuda_de

        foco = wx.Window.FindFocus()
        clave = ""
        if foco is not None:
            clave = _clave_de(foco, dialogo)
        log.debug("Ayuda de la opción pedida para %r", clave or "(ninguna)")
        with DialogoAyudaOpcion(dialogo, clave) as ventana:
            ventana.ShowModal()
        if foco is not None:
            try:
                foco.SetFocus()
            except RuntimeError:
                pass

    dialogo.Bind(wx.EVT_CHAR_HOOK, al_pulsar)


def _clave_de(control: wx.Window, dialogo: wx.Window) -> str:
    """Nombre del atributo con el que ese control vive en su diálogo.

    Si el foco está en una pieza interna de un control compuesto se sube al
    padre, que es el que figura en el catálogo.
    """
    from interfaz.ayuda_control import claves_de

    catalogo = ayudas()
    actual = control
    for _vuelta in range(4):
        if actual is None or actual is dialogo:
            break
        for atributo, valor in vars(dialogo).items():
            if valor is not actual:
                continue
            for clave in claves_de(dialogo, atributo):
                if clave in catalogo:
                    return clave
        actual = actual.GetParent()
    return ""
