# -*- coding: utf-8 -*-
"""Revisión de la estructura deducida, con la ayuda de la IA.

La ventana hace tres cosas y ninguna más: pide la revisión, enseña lo que el
modelo sospecha, y deja **marcar una a una** las que se aceptan.  Lo aceptado se
guarda por el mismo camino que la corrección a mano (``Control+Alt+C``), así que
se aplica al volver a abrir el documento y se puede deshacer igual.

Nada se aplica solo.  Una corrección equivocada esconde texto del libro —eso es
lo que hace «artefacto»—, y eso no se puede hacer sin que alguien lo mire.  Por
eso las casillas vienen todas desmarcadas: aceptar es un acto, no un descuido.
"""

from __future__ import annotations

import threading

import wx

from interfaz.temporizadores import parar_al_destruir
from interfaz.dialogos import ayuda_opcion
from interfaz.accesible import etiquetar, fila_etiquetada
from interfaz.anuncios import Voz
from nucleo.ia import estructura as revisor
from nucleo.ia.servicio import ErrorIA, Servicio
from nucleo.idioma import _, _n
from nucleo.registro import obtener_registro, registrar_excepcion

log = obtener_registro(__name__)

MARGEN = 8


class DialogoEstructura(wx.Dialog):
    """Pide a la IA que revise la estructura y deja aceptar lo que proponga.

    :param padre: Ventana principal.
    :param documento: Documento abierto.
    :param correcciones: Correcciones del documento, donde se anota lo aceptado.
    :param configuracion: Preferencias.
    """

    def __init__(self, padre: wx.Window, documento, correcciones,
                 configuracion) -> None:
        super().__init__(padre, title=_("Revisar la estructura con IA"),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.documento = documento
        self.correcciones = correcciones
        self.configuracion = configuracion
        self.servicio = Servicio(configuracion)
        self._voz = Voz(self)
        self._trabajando = False
        self.sospechas: list = []
        #: Cuántas correcciones se han anotado.  Lo mira la ventana para saber
        #: si hay que volver a abrir el documento.
        self.aplicadas = 0

        self.SetSize((900, 600))
        contenedor = wx.BoxSizer(wx.VERTICAL)

        entradas = revisor.esqueleto(documento)
        contenedor.Add(wx.StaticText(self, label=_(
            "Se le manda a la inteligencia artificial el **esqueleto** del documento: "
            "sus %d bloques con su tipo y su título, sin el texto del libro.\n"
            "Con eso puede señalar lo que está mal etiquetado —un índice tomado por "
            "capítulos, un pie de página tomado por un título— sin que el contenido "
            "salga de aquí.").replace("**", "") % len(entradas)),
            0, wx.ALL, MARGEN)

        self.lista = fila_etiquetada(
            self, contenedor, _("&Lo que se propone corregir:"),
            lambda p: wx.CheckListBox(p, choices=[], size=(860, 300)),
            margen=MARGEN, proporcion=1)

        self.estado = wx.StaticText(self, label=_("Pulsa «Revisar» para empezar."))
        contenedor.Add(self.estado, 0, wx.ALL, MARGEN)

        self.barra = etiquetar(wx.Gauge(self, range=100, size=(-1, 16)), _("Revisando"))
        contenedor.Add(self.barra, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, MARGEN)
        self.barra.Hide()
        self._latido = wx.Timer(self)
        parar_al_destruir(self, self._latido)
        self.Bind(wx.EVT_TIMER, lambda evento: self.barra.Pulse(), self._latido)

        fila = wx.StdDialogButtonSizer()
        self.boton_revisar = wx.Button(self, label=_("&Revisar"))
        self.boton_revisar.SetDefault()
        self.boton_todas = wx.Button(self, label=_("Marcar &todas"))
        self.boton_ninguna = wx.Button(self, label=_("Desmarcar t&odas"))
        self.boton_aplicar = wx.Button(self, wx.ID_OK, _("&Aplicar las marcadas"))
        for boton in (self.boton_revisar, self.boton_todas, self.boton_ninguna):
            fila.Add(boton, 0, wx.RIGHT, MARGEN)
        fila.AddButton(self.boton_aplicar)
        fila.AddButton(wx.Button(self, wx.ID_CANCEL, _("&Cerrar")))
        fila.Realize()
        contenedor.Add(fila, 0, wx.EXPAND | wx.ALL, MARGEN)
        self.SetSizer(contenedor)
        self.Layout()

        self.boton_revisar.Bind(wx.EVT_BUTTON, self._al_revisar)
        self.boton_todas.Bind(wx.EVT_BUTTON, lambda evento: self._marcar(True))
        self.boton_ninguna.Bind(wx.EVT_BUTTON, lambda evento: self._marcar(False))
        self.Bind(wx.EVT_BUTTON, self._al_aplicar, id=wx.ID_OK)
        self._habilitar()
        self.boton_revisar.SetFocus()
        # Control+F1 explica el control que tenga el foco.
        ayuda_opcion.enganchar(self)

    # -- estado --------------------------------------------------------------

    def _habilitar(self) -> None:
        """Deja activo solo lo que tiene sentido en cada momento."""
        hay = bool(self.sospechas)
        self.boton_revisar.Enable(not self._trabajando)
        for boton in (self.boton_todas, self.boton_ninguna, self.boton_aplicar):
            boton.Enable(hay and not self._trabajando)

    def _actividad(self, encendida: bool) -> None:
        """Enciende o apaga la barra que late mientras se revisa."""
        if not self:
            return
        self.barra.Show(encendida)
        if encendida:
            self._latido.Start(120)
        else:
            self._latido.Stop()
        self.Layout()

    def _marcar(self, todas: bool) -> None:
        """Marca o desmarca todas las casillas de una vez."""
        for numero in range(self.lista.GetCount()):
            self.lista.Check(numero, todas)
        self._voz.decir(_("Todas marcadas.") if todas else _("Todas desmarcadas."))

    # -- revisión ------------------------------------------------------------

    def _al_revisar(self, evento) -> None:
        """Manda el esqueleto a la IA en un hilo aparte."""
        del evento
        if self._trabajando:
            return
        motivo = self.servicio.motivo_no_disponible()
        if motivo:
            wx.MessageBox(motivo, _("Inteligencia artificial"),
                          wx.OK | wx.ICON_INFORMATION, self)
            return
        self._trabajando = True
        self._habilitar()
        self._actividad(True)
        aviso = _("Revisando la estructura con %s...") % self.servicio.descripcion_del_modelo()
        self.estado.SetLabel(aviso)
        self._voz.decir(aviso)
        documento = self.documento

        def trabajo() -> None:
            try:
                sospechas, _entradas = revisor.revisar(self.servicio, documento)
            except ErrorIA as error:
                wx.CallAfter(self._fallo, str(error))
            except Exception as error:               # pragma: no cover
                registrar_excepcion(log, "Fallo al revisar la estructura", error)
                wx.CallAfter(self._fallo, str(error))
            else:
                wx.CallAfter(self._listo, sospechas)

        threading.Thread(target=trabajo, name="revisar-estructura", daemon=True).start()

    def _listo(self, sospechas) -> None:
        """Enseña lo que ha devuelto el modelo."""
        if not self:
            return
        self._trabajando = False
        self._actividad(False)
        self.sospechas = list(sospechas)
        self.lista.Set([sospecha.descripcion() for sospecha in self.sospechas])
        if not self.sospechas:
            self.estado.SetLabel(
                _("La revisión no ha encontrado nada claramente mal etiquetado."))
            self._voz.decir(_("Todo parece correcto."))
        else:
            mensaje = _n("Hay %d cosa que revisar. Marca las que quieras aplicar.",
                         "Hay %d cosas que revisar. Marca las que quieras aplicar.",
                         len(self.sospechas)) % len(self.sospechas)
            self.estado.SetLabel(mensaje)
            self._voz.decir(mensaje)
            self.lista.SetFocus()
        self._habilitar()

    def _fallo(self, mensaje: str) -> None:
        """Avisa de que no se ha podido revisar."""
        if not self:
            return
        self._trabajando = False
        self._actividad(False)
        self.estado.SetLabel(_("No se ha podido revisar la estructura."))
        self._habilitar()
        wx.MessageBox(_("No se ha podido revisar la estructura:\n\n%s") % mensaje,
                      _("Inteligencia artificial"), wx.OK | wx.ICON_ERROR, self)

    # -- aplicar -------------------------------------------------------------

    def _al_aplicar(self, evento) -> None:
        """Anota como correcciones las sospechas marcadas."""
        del evento
        self.aplicadas = 0
        for numero, sospecha in enumerate(self.sospechas):
            if not self.lista.IsChecked(numero):
                continue
            if self.correcciones.marcar(sospecha.entrada.pagina, sospecha.entrada.texto,
                                        sospecha.tipo, sospecha.nivel):
                self.aplicadas += 1
        if self.aplicadas:
            self.correcciones.guardar(forzar=True)
            log.info("Revisión de estructura: %d correcciones anotadas", self.aplicadas)
        self.EndModal(wx.ID_OK)
