# -*- coding: utf-8 -*-
"""El visor de notas al pie: todas las notas del libro, para leerlas de seguido.

En un libro muy anotado las notas son la mitad del contenido, y hasta ahora solo
se podían ver de una en una: ir a la llamada, oírla y volver.  Quien quiere
enterarse de verdad acaba haciendo eso quinientas veces.

Esta ventana las pone todas juntas y deja hacer las tres cosas que se hacen con
una nota: leerla entera, ver **dónde se cita** y **saltar a ella** en el libro.

Va rápido porque se hace el trabajo una sola vez: las notas se sacan del
documento al abrir —quinientas tardan centésimas— y el filtro trabaja sobre esa
lista en memoria, sin volver a tocar el texto.  Recorrerla con las flechas no
tiene que esperar a nada.
"""

from __future__ import annotations

import unicodedata

import wx

from interfaz.accesible import etiquetar, fila_etiquetada
from interfaz.dialogos import ayuda_opcion
from nucleo import notas as nucleo_notas
from nucleo.idioma import _
from nucleo.registro import obtener_registro

log = obtener_registro(__name__)

#: Separación estándar entre los elementos de un diálogo, en píxeles.
MARGEN = 8

#: Cuánto de la nota se enseña en la lista.  Lo que no quepa está debajo, en el
#: cuadro de lectura: la lista es para encontrar, no para leer.
RESUMEN = 120


def _sin_tildes(texto: str) -> str:
    """El texto en minúsculas y sin tildes, para buscar sin pelearse.

    Quien busca «eudaimonia» tiene que encontrar «eudaimonía», y quien busca
    «Isocrates» tiene que encontrar «Isócrates».  En un libro clásico eso no es
    una comodidad: es la diferencia entre encontrar y no encontrar.
    """
    return "".join(letra for letra in unicodedata.normalize("NFD", texto.lower())
                   if unicodedata.category(letra) != "Mn")


class DialogoNotas(wx.Dialog):
    """Todas las notas al pie del documento, con su texto y sus dos destinos.

    Devuelve en :attr:`posicion_elegida` a dónde hay que ir, o ``None`` si se
    cierra sin elegir.  Hay dos destinos posibles y los dos hacen falta: la
    **llamada** es el pasaje que cita la nota —a donde se vuelve para seguir
    leyendo— y la **nota** es su texto al final del libro.
    """

    def __init__(self, padre: wx.Window, documento, posicion: int = 0) -> None:
        super().__init__(padre, title=_("Notas al pie"),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.documento = documento
        self.posicion_actual = posicion
        self.posicion_elegida: int | None = None

        self._todas = nucleo_notas.todas(documento)
        self._visibles = list(self._todas)

        contenedor = wx.BoxSizer(wx.VERTICAL)

        self.buscar = fila_etiquetada(
            self, contenedor, _("&Buscar en las notas:"),
            lambda p: wx.TextCtrl(p, style=wx.TE_PROCESS_ENTER))
        self.buscar.Bind(wx.EVT_TEXT, self._al_buscar)
        self.buscar.Bind(wx.EVT_TEXT_ENTER, lambda evento: self.lista.SetFocus())

        self.lista = fila_etiquetada(
            self, contenedor, _("&Notas del documento:"),
            lambda p: wx.ListBox(p, size=(680, 220)), proporcion=1)
        self.lista.Bind(wx.EVT_LISTBOX, self._al_elegir)
        self.lista.Bind(wx.EVT_LISTBOX_DCLICK, self._al_ir_a_la_nota)

        self.texto = fila_etiquetada(
            self, contenedor, _("&Texto de la nota:"),
            lambda p: wx.TextCtrl(p, size=(680, 140),
                                  style=wx.TE_MULTILINE | wx.TE_READONLY
                                  | wx.TE_RICH2),
            proporcion=1)

        fila = wx.BoxSizer(wx.HORIZONTAL)
        self.boton_llamada = etiquetar(
            wx.Button(self, label=_("Ir a donde se &cita")),
            _("Ir a donde se cita"))
        self.boton_llamada.Bind(wx.EVT_BUTTON, self._al_ir_a_la_llamada)
        self.boton_nota = etiquetar(
            wx.Button(self, label=_("Ir a la &nota")), _("Ir a la nota"))
        self.boton_nota.Bind(wx.EVT_BUTTON, self._al_ir_a_la_nota)
        self.boton_copiar = etiquetar(
            wx.Button(self, label=_("C&opiar")), _("Copiar la nota"))
        self.boton_copiar.Bind(wx.EVT_BUTTON, self._al_copiar)
        for boton in (self.boton_llamada, self.boton_nota, self.boton_copiar):
            fila.Add(boton, 0, wx.RIGHT, MARGEN)
        fila.AddStretchSpacer()
        cerrar = wx.Button(self, wx.ID_CANCEL, _("Ce&rrar"))
        fila.Add(cerrar, 0)
        contenedor.Add(fila, 0, wx.EXPAND | wx.ALL, MARGEN)

        self.SetSizerAndFit(contenedor)
        self.CenterOnParent()
        ayuda_opcion.enganchar(self)
        self._rellenar()
        # El foco a la lista y no al buscador: casi siempre se viene a mirar
        # las notas de por donde se iba leyendo, no a buscar una concreta.
        self.lista.SetFocus()

    # -- la lista ------------------------------------------------------------

    def _resumen(self, nota) -> str:
        """Una línea por nota: su número y el principio de lo que dice."""
        dice = nota.texto
        # El número ya va delante en casi todas las ediciones; si va, no se
        # repite, que leer «[18] [18] Igual que...» es ruido.
        if nota.rotulo and dice.startswith(nota.rotulo):
            dice = dice[len(nota.rotulo):].lstrip()
        if len(dice) > RESUMEN:
            dice = dice[:RESUMEN].rstrip() + "…"
        return "%s  %s" % (nota.rotulo or _("(sin número)"),
                           dice or _("(sin texto)"))

    def _rellenar(self) -> None:
        """Vuelca las notas visibles y deja elegida la más cercana."""
        if not self._visibles:
            self.lista.Set([_("(Ninguna nota coincide con lo que buscas)")
                            if self._todas
                            else _("(Este documento no tiene notas al pie)")])
            self.lista.Enable(False)
            self._al_elegir(None)
            return
        self.lista.Enable(True)
        self.lista.Set([self._resumen(uno) for uno in self._visibles])
        cercana = min(range(len(self._visibles)),
                      key=lambda numero: abs(self._visibles[numero].llamada
                                             - self.posicion_actual))
        self.lista.SetSelection(cercana)
        self.lista.EnsureVisible(cercana)
        self._al_elegir(None)

    def _elegida(self):
        """La nota seleccionada, o ``None``."""
        if not self._visibles:
            return None
        cual = self.lista.GetSelection()
        if cual < 0 or cual >= len(self._visibles):
            return None
        return self._visibles[cual]

    def _al_elegir(self, evento) -> None:
        """Enseña abajo el texto entero de la nota elegida."""
        nota = self._elegida()
        self.texto.SetValue(nota.texto if nota is not None else "")
        for boton in (self.boton_llamada, self.boton_nota, self.boton_copiar):
            boton.Enable(nota is not None)

    def _al_buscar(self, evento) -> None:
        """Filtra según lo escrito, sin tildes y sin distinguir mayúsculas."""
        buscado = _sin_tildes(self.buscar.GetValue().strip())
        if not buscado:
            self._visibles = list(self._todas)
        else:
            self._visibles = [uno for uno in self._todas
                              if buscado in _sin_tildes(uno.rotulo + " "
                                                        + uno.texto)]
        self._rellenar()

    # -- lo que se hace con una nota -----------------------------------------

    def _salir_hacia(self, posicion: int) -> None:
        self.posicion_elegida = posicion
        self.EndModal(wx.ID_OK)

    def _al_ir_a_la_llamada(self, evento) -> None:
        """Va al pasaje que cita la nota, que es por donde se seguía leyendo."""
        nota = self._elegida()
        if nota is not None:
            self._salir_hacia(nota.llamada)

    def _al_ir_a_la_nota(self, evento) -> None:
        """Va al texto de la nota, al final del libro."""
        nota = self._elegida()
        if nota is not None:
            self._salir_hacia(nota.destino)

    def _al_copiar(self, evento) -> None:
        """Copia la nota entera al portapapeles."""
        nota = self._elegida()
        if nota is None:
            return
        if not wx.TheClipboard.Open():
            log.warning("No se ha podido abrir el portapapeles")
            return
        try:
            wx.TheClipboard.SetData(wx.TextDataObject(nota.texto))
        finally:
            wx.TheClipboard.Close()
